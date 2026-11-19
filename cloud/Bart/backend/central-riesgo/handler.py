"""Central de riesgo simulada (Bart).

GET /rcc/{dni}?periodo=YYYY-MM
- dni: 8 digitos. La clave en DynamoDB es documento = "DNI#" + dni.
- Sin periodo: devuelve el periodo mas reciente (Query con SK descendente y limite 1). Nunca usa Scan.
- Errores con la forma {"error": {"codigo", "mensaje"}}; nunca se devuelve el texto de la excepcion.
- Logs: solo evento, status, codigo y milisegundos (sin DNI ni datos del cliente).
"""
import json
import os
import re
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

TABLA = boto3.resource("dynamodb").Table(os.environ["RCC_TABLE"])
DNI_RE = re.compile(r"^[0-9]{8}$")
PERIODO_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
ORDEN = ["documento", "periodo", "sbs_customer_id", "clasificacion_sbs", "pct_normal", "max_dias_atraso",
         "n_entidades", "n_creditos", "deuda_total", "deuda_directa", "deuda_con_atraso", "deuda_consumo",
         "deuda_tarjeta", "deuda_vehicular", "deuda_hipotecario", "cuota_mensual_estimada",
         "banda_endeudamiento", "lineas", "es_sintetico"]


def _num(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(type(o).__name__)


def _respuesta(status, cuerpo):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(cuerpo, default=_num, ensure_ascii=False),
    }


def _error(status, codigo, mensaje):
    return _respuesta(status, {"error": {"codigo": codigo, "mensaje": mensaje}})


def _log(**campos):
    print(json.dumps({"evento": "consultar_rcc", **campos}))


def consultar_rcc(event, context):
    inicio = time.time()
    dni = (event.get("pathParameters") or {}).get("dni", "")
    periodo = (event.get("queryStringParameters") or {}).get("periodo")

    if not DNI_RE.match(dni):
        _log(status=400, codigo="DNI_INVALIDO")
        return _error(400, "DNI_INVALIDO", "El DNI debe tener 8 digitos")
    if periodo is not None and not PERIODO_RE.match(periodo):
        _log(status=400, codigo="PARAMETRO_INVALIDO")
        return _error(400, "PARAMETRO_INVALIDO", "periodo debe tener el formato YYYY-MM")

    documento = "DNI#" + dni
    try:
        if periodo:
            item = TABLA.get_item(Key={"documento": documento, "periodo": periodo}).get("Item")
        else:
            items = TABLA.query(KeyConditionExpression=Key("documento").eq(documento),
                                ScanIndexForward=False, Limit=1).get("Items", [])
            item = items[0] if items else None
    except ClientError as e:
        _log(status=500, codigo="ERROR_INTERNO", aws=e.response.get("Error", {}).get("Code"))
        return _error(500, "ERROR_INTERNO", "No se pudo consultar la central de riesgo")

    ms = int((time.time() - inicio) * 1000)
    if not item:
        _log(status=404, codigo="RCC_NO_ENCONTRADO", ms=ms)
        return _error(404, "RCC_NO_ENCONTRADO", "No hay informacion de la central de riesgo para ese DNI")

    cuerpo = {k: item[k] for k in ORDEN if k in item}
    cuerpo.update({k: v for k, v in item.items() if k not in cuerpo})
    _log(status=200, ms=ms)
    return _respuesta(200, cuerpo)
