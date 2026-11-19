"""API Solicitudes (HTTP API) y las mismas operaciones por invoke para Bart.

- HTTP: el evento de API Gateway trae routeKey; responde statusCode/headers/body.
- Invoke: {"operacion": "...", "datos": {...}}; responde {"status": ..., "cuerpo": ...}.
Nunca devuelve el texto de una excepcion. Logs sin DNI ni montos.
"""
import base64
import binascii
import hashlib
import json
import os
import time
import uuid

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from comun import (DNI_RE, ESTADOS, ESTADOS_ACTIVOS, VERSION_CONTRATO, ErrorApi, a_dynamo, ahora_iso, de_dynamo,
                   hoy_lima, log, tabla, texto_condiciones, texto_resultado)

s3 = boto3.client("s3")
sfn = boto3.client("stepfunctions")
MAX_PDF = 2 * 1024 * 1024  # tope de la boleta: 2 MB
CAMPOS_OFERTA = ["oferta_id", "producto_id", "producto_nombre", "moneda", "monto_minimo", "monto_maximo", "tea",
                 "tcea_referencial", "plazo_meses", "cuota_mensual_referencial", "ahorro_mensual_estimado",
                 "fecha_fin_vigencia", "condiciones"]
ORDEN_SALIDA = ["version_contrato", "solicitud_id", "estado", "motivo", "documento", "es_sintetico", "producto",
                "oferta", "monto_solicitado", "evaluacion", "compra_deuda", "boleta", "explicacion", "historial",
                "cierre", "sesion_id", "execution_arn", "creado_en", "actualizado_en", "version"]


def _dni(valor):
    if not isinstance(valor, str) or not DNI_RE.match(valor):
        raise ErrorApi(400, "DNI_INVALIDO", "El DNI debe tener 8 digitos")
    return "DNI#" + valor


def _texto(d, campo, maximo):
    v = d.get(campo)
    if not isinstance(v, str) or not 1 <= len(v.strip()) <= maximo:
        raise ErrorApi(400, "CUERPO_INVALIDO", "%s es obligatorio (1 a %d caracteres)" % (campo, maximo))
    return v.strip()


def _leer(solicitud_id):
    if not isinstance(solicitud_id, str) or not solicitud_id:
        raise ErrorApi(400, "CUERPO_INVALIDO", "solicitud_id es obligatorio")
    item = tabla("SOLICITUDES_TABLE").get_item(Key={"solicitud_id": solicitud_id}).get("Item")
    if not item:
        raise ErrorApi(404, "SOLICITUD_NO_ENCONTRADA", "No existe la solicitud")
    return de_dynamo(item)


def _ofertas(documento):
    todas = de_dynamo(tabla("OFERTAS_TABLE").query(KeyConditionExpression=Key("documento").eq(documento))["Items"])
    hoy = hoy_lima()
    vigentes = [o for o in todas if o.get("estado") == "VIGENTE"
                and o.get("fecha_inicio_vigencia", "9999") <= hoy <= o.get("fecha_fin_vigencia", "0000")]
    return todas, sorted(vigentes, key=lambda o: o.get("prioridad", 99))


# ---------- GET /clientes/{dni}/ofertas ----------
def listar_ofertas(d):
    documento = _dni(d.get("dni"))
    _, vigentes = _ofertas(documento)
    return 200, {"documento": documento, "fecha_consulta": hoy_lima(),
                 "ofertas": [{k: o.get(k) for k in CAMPOS_OFERTA} for o in vigentes], "es_sintetico": True}


# ---------- POST /solicitudes ----------
def crear_solicitud(d):
    monto = d.get("monto_solicitado")
    boleta = d.get("boleta")
    if (not isinstance(d.get("oferta_id"), str) or isinstance(monto, bool) or not isinstance(monto, (int, float))
            or monto <= 0 or not isinstance(boleta, dict) or not isinstance(boleta.get("contenido_base64"), str)):
        raise ErrorApi(400, "CUERPO_INVALIDO", "Se requieren dni, oferta_id, monto_solicitado (numero) y boleta.contenido_base64")
    documento = _dni(d.get("dni"))
    todas, vigentes = _ofertas(documento)
    oferta = next((o for o in todas if o["oferta_id"] == d["oferta_id"]), None)
    if not oferta:
        raise ErrorApi(404, "OFERTA_NO_ENCONTRADA", "La oferta no existe para ese DNI")
    if oferta not in vigentes:
        raise ErrorApi(409, "OFERTA_NO_VIGENTE", "La oferta no esta vigente")
    if not oferta["monto_minimo"] <= monto <= oferta["monto_maximo"]:
        raise ErrorApi(422, "MONTO_FUERA_DE_OFERTA",
                       "El monto debe estar entre %s y %s" % (oferta["monto_minimo"], oferta["monto_maximo"]),
                       {"monto_minimo": oferta["monto_minimo"], "monto_maximo": oferta["monto_maximo"]})
    try:
        pdf = base64.b64decode(boleta["contenido_base64"], validate=True)
    except (binascii.Error, ValueError):
        pdf = b""
    if not pdf.startswith(b"%PDF-"):
        raise ErrorApi(400, "BOLETA_NO_PDF", "La boleta debe ser un PDF en base64")
    if len(pdf) > MAX_PDF:
        raise ErrorApi(413, "BOLETA_MUY_GRANDE", "La boleta supera 2 MB")
    activas = tabla("SOLICITUDES_TABLE").query(IndexName="gsi_documento",
                                               KeyConditionExpression=Key("documento").eq(documento),
                                               FilterExpression=Attr("estado").is_in(ESTADOS_ACTIVOS))["Items"]
    if activas:  # una sola solicitud activa por documento (la validacion no es atomica; alcanza para este alcance)
        raise ErrorApi(409, "SOLICITUD_ACTIVA", "Ya hay una solicitud en curso para este DNI",
                       {"solicitud_id": activas[0]["solicitud_id"]})

    sid = str(uuid.uuid4())
    s3_key = "boletas/%s/boleta.pdf" % sid
    s3.put_object(Bucket=os.environ["BOLETAS_BUCKET"], Key=s3_key, Body=pdf, ContentType="application/pdf",
                  ServerSideEncryption="AES256", Metadata={"es-sintetico": "true"})
    sha = hashlib.sha256(pdf).hexdigest()
    ahora = ahora_iso()
    canal = d.get("canal") if d.get("canal") in ("BART", "WEB", "API") else "API"
    item = {
        "version_contrato": VERSION_CONTRATO, "solicitud_id": sid, "estado": "EN_PROCESO", "motivo": None,
        "documento": documento, "es_sintetico": True,
        "producto": {"producto_id": oferta["producto_id"], "nombre": oferta["producto_nombre"]},
        "oferta": {k: oferta.get(k) for k in ("oferta_id", "campana", "moneda", "monto_minimo", "monto_maximo", "tea",
                                              "tcea_referencial", "plazo_meses", "fecha_fin_vigencia")},
        "monto_solicitado": monto, "evaluacion": None, "compra_deuda": None,
        "boleta": {"periodo": None, "score_consistencia": None, "banderas": [], "sha256": sha},
        "explicacion": None,
        "historial": [{"estado": "EN_PROCESO", "motivo": None, "fecha": ahora, "origen": "API_SOLICITUDES"}],
        "cierre": None, "sesion_id": d.get("sesion_id") if isinstance(d.get("sesion_id"), str) else None,
        "canal": canal, "execution_arn": None, "s3_key": s3_key, "creado_en": ahora, "actualizado_en": ahora, "version": 1,
    }
    t = tabla("SOLICITUDES_TABLE")
    t.put_item(Item=a_dynamo(item), ConditionExpression="attribute_not_exists(solicitud_id)")
    entrada = {"solicitud_id": sid, "documento": documento, "dni": documento[4:], "oferta_id": oferta["oferta_id"],
               "producto_id": oferta["producto_id"], "monto_solicitado": monto, "s3_key": s3_key, "sha256": sha}
    try:
        arn = sfn.start_execution(stateMachineArn=os.environ["STATE_MACHINE_ARN"], name=sid,
                                  input=json.dumps(entrada))["executionArn"]
    except ClientError as err:
        log("crear_solicitud", solicitud_id=sid, error=err.response["Error"]["Code"])
        t.update_item(Key={"solicitud_id": sid},
                      UpdateExpression="SET estado = :e, motivo = :m, actualizado_en = :t, historial = list_append(historial, :h), version = version + :uno",
                      ExpressionAttributeValues={":e": "ERROR", ":m": "ERROR_TECNICO", ":t": ahora_iso(), ":uno": 1,
                                                 ":h": [{"estado": "ERROR", "motivo": "ERROR_TECNICO", "fecha": ahora_iso(), "origen": "API_SOLICITUDES"}]})
        raise ErrorApi(502, "DEPENDENCIA_NO_DISPONIBLE", "No se pudo iniciar la evaluacion")
    t.update_item(Key={"solicitud_id": sid}, UpdateExpression="SET execution_arn = :a", ExpressionAttributeValues={":a": arn})
    log("crear_solicitud", solicitud_id=sid, producto=oferta["producto_id"], canal=canal)
    return 202, {"solicitud_id": sid, "estado": "EN_PROCESO", "creado_en": ahora, "consultar": "/solicitudes/" + sid}


# ---------- GET /solicitudes/{solicitud_id} ----------
def leer_solicitud(d):
    item = _leer(d.get("solicitud_id"))
    return 200, {k: item.get(k) for k in ORDEN_SALIDA}


# ---------- GET /solicitudes ----------
def listar_solicitudes(q):
    estado = q.get("estado")
    if estado is not None and estado not in ESTADOS:
        raise ErrorApi(400, "PARAMETRO_INVALIDO", "estado no valido", {"estados": ESTADOS})
    try:
        limite = int(q.get("limite", "20"))
        assert 1 <= limite <= 100
        inicio = json.loads(base64.urlsafe_b64decode(q["cursor"].encode())) if q.get("cursor") else None
    except (ValueError, AssertionError, binascii.Error):
        raise ErrorApi(400, "PARAMETRO_INVALIDO", "limite (1 a 100) o cursor no validos")
    kwargs = {"ScanIndexForward": False, "Limit": limite}
    if inicio:
        kwargs["ExclusiveStartKey"] = inicio
    if q.get("dni") is not None:
        kwargs.update(IndexName="gsi_documento", KeyConditionExpression=Key("documento").eq(_dni(q.get("dni"))))
        if estado:
            kwargs["FilterExpression"] = Attr("estado").eq(estado)
    else:
        kwargs.update(IndexName="gsi_estado", KeyConditionExpression=Key("estado").eq(estado or "PRE_APROBADA"))
    r = tabla("SOLICITUDES_TABLE").query(**kwargs)
    items = [{"solicitud_id": i["solicitud_id"], "estado": i["estado"], "motivo": i.get("motivo"),
              "documento": i["documento"], "producto_id": i["producto"]["producto_id"],
              "monto_solicitado": i["monto_solicitado"],
              "monto_preaprobado": (i.get("evaluacion") or {}).get("monto_preaprobado"),
              "creado_en": i["creado_en"], "actualizado_en": i["actualizado_en"]} for i in de_dynamo(r["Items"])]
    cursor = (base64.urlsafe_b64encode(json.dumps(r["LastEvaluatedKey"]).encode()).decode()
              if "LastEvaluatedKey" in r else None)
    return 200, {"items": items, "siguiente_cursor": cursor}


def _actualizar(sid, version, estado_requerido, cambios, historial):
    sets = ", ".join("%s = :%s" % (k, k) for k in cambios)
    valores = {":" + k: v for k, v in cambios.items()}
    valores.update({":req": estado_requerido, ":v": version, ":uno": 1, ":h": [historial]})
    try:
        tabla("SOLICITUDES_TABLE").update_item(
            Key={"solicitud_id": sid},
            UpdateExpression="SET %s, historial = list_append(historial, :h), version = version + :uno" % sets,
            ConditionExpression="estado = :req AND version = :v", ExpressionAttributeValues=a_dynamo(valores))
    except ClientError as err:
        if err.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        actual = _leer(sid)["estado"]
        raise ErrorApi(409, "ESTADO_NO_PERMITE", "La solicitud cambio de estado", {"estado_actual": actual})


# ---------- POST /solicitudes/{solicitud_id}/contraoferta ----------
def decidir_contraoferta(d):
    decision = d.get("decision")
    if decision not in ("ACEPTA", "RECHAZA"):
        raise ErrorApi(400, "DECISION_INVALIDA", "decision debe ser ACEPTA o RECHAZA")
    item = _leer(d.get("solicitud_id"))
    if item["estado"] != "CONTRAOFERTA":
        raise ErrorApi(409, "ESTADO_NO_PERMITE", "La solicitud no esta en CONTRAOFERTA", {"estado_actual": item["estado"]})
    ev, plazo, ahora = item["evaluacion"], item["oferta"].get("plazo_meses"), ahora_iso()
    if decision == "ACEPTA":
        ev["monto_preaprobado"] = ev["monto_aprobable"]
        estado, motivo = "PRE_APROBADA", "CONTRAOFERTA_ACEPTADA"
        texto = texto_resultado("PRE_APROBADA", item["producto"]["producto_id"], ev["monto_aprobable"], plazo,
                                ev["cuota_mensual_estimada"])
    else:
        estado, motivo = "DESISTIDA", "CONTRAOFERTA_RECHAZADA"
        texto = texto_condiciones(ev["monto_aprobable"], plazo)
    _actualizar(item["solicitud_id"], item["version"], "CONTRAOFERTA",
                {"estado": estado, "motivo": motivo, "evaluacion": ev, "explicacion": texto, "actualizado_en": ahora},
                {"estado": estado, "motivo": motivo, "fecha": ahora, "origen": "CLIENTE"})
    return 200, {"solicitud_id": item["solicitud_id"], "estado": estado, "motivo": motivo,
                 "monto_preaprobado": ev["monto_preaprobado"], "cuota_mensual_estimada": ev["cuota_mensual_estimada"]}


# ---------- POST /solicitudes/{solicitud_id}/cierre ----------
def cerrar_solicitud(d):
    usuario, producto_final = _texto(d, "usuario_banco", 50), _texto(d, "producto_final", 50)
    item = _leer(d.get("solicitud_id"))
    if item["estado"] != "PRE_APROBADA":
        raise ErrorApi(409, "ESTADO_NO_PERMITE", "Solo se cierra una solicitud PRE_APROBADA", {"estado_actual": item["estado"]})
    ahora = ahora_iso()
    cierre = {"usuario_banco": usuario, "fecha": ahora, "producto_final": producto_final}
    _actualizar(item["solicitud_id"], item["version"], "PRE_APROBADA",
                {"estado": "CERRADA", "motivo": "CERRADA_POR_BANCO", "cierre": cierre, "actualizado_en": ahora},
                {"estado": "CERRADA", "motivo": "CERRADA_POR_BANCO", "fecha": ahora, "origen": "BANCO"})
    return 200, {"solicitud_id": item["solicitud_id"], "estado": "CERRADA", "motivo": "CERRADA_POR_BANCO", "cierre": cierre}


RUTAS = {
    "GET /clientes/{dni}/ofertas": ("LISTAR_OFERTAS", listar_ofertas),
    "POST /solicitudes": ("CREAR_SOLICITUD", crear_solicitud),
    "GET /solicitudes": (None, listar_solicitudes),
    "GET /solicitudes/{solicitud_id}": ("LEER_SOLICITUD", leer_solicitud),
    "POST /solicitudes/{solicitud_id}/contraoferta": ("DECIDIR_CONTRAOFERTA", decidir_contraoferta),
    "POST /solicitudes/{solicitud_id}/cierre": (None, cerrar_solicitud),
}
OPERACIONES = {op: fn for op, fn in RUTAS.values() if op}


def _ejecutar(nombre, fn, datos):
    inicio = time.time()
    try:
        status, cuerpo = fn(datos)
    except ErrorApi as e:
        status, cuerpo = e.status, e.cuerpo()
    except Exception as e:  # nunca se devuelve el detalle
        log("api", ruta=nombre, status=500, error=type(e).__name__)
        status, cuerpo = 500, {"error": {"codigo": "ERROR_INTERNO", "mensaje": "Error interno"}}
    log("api", ruta=nombre, status=status, ms=int((time.time() - inicio) * 1000),
        codigo=(cuerpo.get("error") or {}).get("codigo"))
    return status, cuerpo


def handler(event, context):
    if "operacion" in event:  # invoke desde Bart
        fn = OPERACIONES.get(event["operacion"])
        if not fn:
            return {"status": 400, "cuerpo": {"error": {"codigo": "OPERACION_INVALIDA", "mensaje": "Operacion no soportada"}}}
        status, cuerpo = _ejecutar(event["operacion"], fn, event.get("datos") or {})
        return {"status": status, "cuerpo": cuerpo}

    ruta = event.get("routeKey", "")
    _, fn = RUTAS.get(ruta, (None, None))
    datos = {}
    if ruta == "GET /solicitudes":
        datos = dict(event.get("queryStringParameters") or {})
    elif event.get("body"):
        try:
            cuerpo = base64.b64decode(event["body"]) if event.get("isBase64Encoded") else event["body"]
            datos = json.loads(cuerpo)
            assert isinstance(datos, dict)
        except (ValueError, AssertionError, binascii.Error):
            fn = lambda _d: (400, {"error": {"codigo": "CUERPO_INVALIDO", "mensaje": "El cuerpo debe ser un objeto JSON"}})
    datos.update(event.get("pathParameters") or {})
    if fn is None:
        status, cuerpo = 404, {"error": {"codigo": "RUTA_NO_ENCONTRADA", "mensaje": "Ruta no soportada"}}
    else:
        status, cuerpo = _ejecutar(ruta, fn, datos)
    return {"statusCode": status, "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps(cuerpo, ensure_ascii=False)}
