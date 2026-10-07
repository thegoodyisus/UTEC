#reglas de negocio de la api contra aws simulado
import json
import uuid
from datetime import datetime, timedelta, timezone

from boto3.dynamodb.conditions import Key

from .conftest import quien

AGRI = quien("agri-1", "agricultor")
AGRI2 = quien("agri-2", "agricultor")
COMP = quien("comp-1", "comprador")
COMP2 = quien("comp-2", "comprador")
#la api usa la fecha de lima (utc-5); el contenedor esta en utc y entre 19:00 y 24:00 de lima ya es el dia siguiente
HOY_LIMA = datetime.now(timezone(timedelta(hours=-5))).date()
FUTURO = (HOY_LIMA + timedelta(days=90)).isoformat()


def perfil_agricultor(e, h=AGRI):
    cuerpo = {"rol": "agricultor", "nombres": "Rosa", "apellidos": "Prueba", "tipoDoc": "DNI", "documento": "12345678",
              "celular": "987654321", "cultivos": ["papa"], "departamento": "Cusco", "provincia": "Cusco", "distrito": "Wanchaq"}
    return e.cliente.post("/api/v1/perfil", json=cuerpo, headers=h)


def perfil_comprador(e, h=COMP, nombre="Compras SAC"):
    cuerpo = {"rol": "comprador", "tipoDoc": "RUC", "documento": "20123456789", "razonSocial": nombre, "contactoNombre": "Ana",
              "contactoCelular": "912345678", "contactoCargo": "Gerente de compras", "cuentaCargoId": "c1", "modalidadPago": "recibir"}
    return e.cliente.post("/api/v1/perfil", json=cuerpo, headers=h)


def campana(cid=None, **cambios):
    c = {"campaniaId": cid or str(uuid.uuid4()), "cultivo": "papa", "departamento": "Cusco", "provincia": "Cusco", "distrito": "Wanchaq",
         "cosecha": FUTURO, "volumenKg": 2000, "logistica": "Recojo", "capital": "5000.00", "precioAhoraPorKg": "1.80",
         "precioContraentregaPorKg": "2.10"}
    c.update(cambios)
    return c


def mensajes(e):
    r = e.sqs.receive_message(QueueUrl=e.cola, MaxNumberOfMessages=10)
    return [json.loads(m["Body"]) for m in r.get("Messages", [])]


def guardar_campana(e, cid, dueno="agri-1", estado="PUBLICADA", volumen=2000):
    e.tabla.put_item(Item={
        "PK": "CAMP#" + cid, "SK": "META", "entidad": "CAMPANA", "campaniaId": cid, "propietarioSub": dueno,
        "productorNombre": "Rosa Prueba", "cultivo": "papa", "departamento": "Cusco", "provincia": "Cusco", "distrito": "Wanchaq",
        "cosecha": FUTURO, "volumenKg": volumen, "logistica": "Recojo", "capitalCentimos": 500000, "precioAhoraCentimosPorKg": 180,
        "precioContraentregaCentimosPorKg": 210, "referenciaMercadoCentimosPorKg": 120, "estado": estado, "numeroOfertas": 0,
        "creadoEn": "2026-10-04T05:00:00Z", "usuarioClave": "USER#" + dueno, "usuarioOrden": "CAMP#2026-10-04T05:00:00Z#" + cid,
        "publicadaClave": "PUB#papa#Cusco", "publicadaOrden": FUTURO + "#" + cid})


def test_salud_sin_token(entorno):
    r = entorno.cliente.get("/api/v1/salud")
    assert r.status_code == 200 and r.json()["estado"] == "ok"


def test_sin_token_responde_401_problem_json(entorno):
    r = entorno.cliente.get("/api/v1/perfil")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["requestId"]


def test_perfil_crear_obtener_y_duplicado(entorno):
    assert perfil_agricultor(entorno).status_code == 201
    r = entorno.cliente.get("/api/v1/perfil", headers=AGRI)
    assert r.status_code == 200 and r.json()["nombres"] == "Rosa" and "PK" not in r.json()
    assert perfil_agricultor(entorno).status_code == 409


def test_perfil_con_rol_distinto_al_token(entorno):
    assert perfil_comprador(entorno, h=AGRI).status_code == 403


def test_perfil_cultivo_fuera_de_catalogo(entorno):
    cuerpo = {"rol": "agricultor", "nombres": "R", "apellidos": "P", "tipoDoc": "DNI", "documento": "12345678",
              "celular": "987654321", "cultivos": ["yuca"], "departamento": "C", "provincia": "C", "distrito": "C"}
    assert entorno.cliente.post("/api/v1/perfil", json=cuerpo, headers=AGRI).status_code == 422


def test_catalogo_desde_la_base(entorno):
    r = entorno.cliente.get("/api/v1/catalogo/cultivos", headers=COMP)
    assert r.json() == [{"slug": "papa", "nombre": "Papa", "referenciaMercadoPorKg": "1.20"},
                        {"slug": "maiz", "nombre": "Maíz", "referenciaMercadoPorKg": "1.10"}]


def test_crear_campana_encola_item_completo(entorno):
    perfil_agricultor(entorno)
    c = campana()
    r = entorno.cliente.post("/api/v1/campanas", json=c, headers=AGRI)
    assert r.status_code == 202 and r.json()["recursoId"] == c["campaniaId"]
    m = mensajes(entorno)
    assert len(m) == 1 and m[0]["tipo"] == "campana"
    item = m[0]["item"]
    assert item["precioAhoraCentimosPorKg"] == 180 and item["capitalCentimos"] == 500000
    assert item["referenciaMercadoCentimosPorKg"] == 120 and item["productorNombre"] == "Rosa Prueba"
    assert item["publicadaClave"] == "PUB#papa#Cusco" and item["usuarioClave"] == "USER#agri-1"


def test_campana_reglas(entorno):
    perfil_agricultor(entorno)
    assert entorno.cliente.post("/api/v1/campanas", json=campana(cosecha=HOY_LIMA.isoformat()), headers=AGRI).status_code == 422
    assert entorno.cliente.post("/api/v1/campanas", json=campana(cultivo="yuca"), headers=AGRI).status_code == 422
    assert entorno.cliente.post("/api/v1/campanas", json=campana(capital="5000"), headers=AGRI).status_code == 422
    assert entorno.cliente.post("/api/v1/campanas", json=campana(), headers=COMP).status_code == 403
    assert entorno.cliente.post("/api/v1/campanas", json=campana(), headers=AGRI2).status_code == 403


def test_campana_idempotente_y_conflicto(entorno):
    cid = str(uuid.uuid4())
    guardar_campana(entorno, cid)
    perfil_agricultor(entorno)
    assert entorno.cliente.post("/api/v1/campanas", json=campana(cid), headers=AGRI).status_code == 202
    assert mensajes(entorno) == []
    assert entorno.cliente.post("/api/v1/campanas", json=campana(cid), headers=AGRI2).status_code == 409


def test_vistas_de_campana_por_rol(entorno):
    cid = str(uuid.uuid4())
    guardar_campana(entorno, cid)
    propia = entorno.cliente.get("/api/v1/campanas/" + cid, headers=AGRI).json()
    assert propia["capital"] == "5000.00" and propia["numeroOfertas"] == 0
    publica = entorno.cliente.get("/api/v1/campanas/" + cid, headers=COMP).json()
    assert "capital" not in publica and "propietarioSub" not in publica
    assert entorno.cliente.get("/api/v1/campanas/" + cid, headers=AGRI2).status_code == 404
    lista = entorno.cliente.get("/api/v1/campanas/publicadas?cultivo=papa&departamento=Cusco", headers=COMP).json()
    assert [x["campaniaId"] for x in lista["items"]] == [cid] and "capital" not in lista["items"][0]
    assert entorno.cliente.get("/api/v1/campanas/publicadas?cultivo=papa&departamento=Cusco", headers=AGRI).status_code == 403


def test_mis_campanas_una_debajo_de_otra(entorno):
    for _ in range(3):
        guardar_campana(entorno, str(uuid.uuid4()))
    r = entorno.cliente.get("/api/v1/campanas?limite=2", headers=AGRI).json()
    assert len(r["items"]) == 2 and r["siguienteCursor"]
    r2 = entorno.cliente.get("/api/v1/campanas?limite=2&cursor=" + r["siguienteCursor"], headers=AGRI).json()
    assert len(r2["items"]) == 1


def test_cursor_invalido(entorno):
    assert entorno.cliente.get("/api/v1/campanas?cursor=@@@", headers=AGRI).status_code == 422


def test_oferta_reglas_y_total(entorno):
    cid = str(uuid.uuid4())
    guardar_campana(entorno, cid, volumen=1000)
    perfil_comprador(entorno)
    base = {"ofertaId": str(uuid.uuid4()), "volumenKg": 500, "precioPorKg": "1.85", "modalidad": "Pago ahora",
            "logistica": "Recojo", "fechaEntrega": FUTURO}
    assert entorno.cliente.post("/api/v1/campanas/" + cid + "/ofertas", json=dict(base, volumenKg=1001), headers=COMP).status_code == 422
    assert entorno.cliente.post("/api/v1/campanas/" + str(uuid.uuid4()) + "/ofertas", json=base, headers=COMP).status_code == 404
    assert entorno.cliente.post("/api/v1/campanas/" + cid + "/ofertas", json=base, headers=AGRI).status_code == 403
    assert entorno.cliente.post("/api/v1/campanas/" + cid + "/ofertas", json=base, headers=COMP2).status_code == 403
    r = entorno.cliente.post("/api/v1/campanas/" + cid + "/ofertas", json=base, headers=COMP)
    assert r.status_code == 202
    item = mensajes(entorno)[0]["item"]
    assert item["totalCentimos"] == 92500 and item["compradorNombre"] == "Compras SAC" and item["cultivo"] == "papa"


def test_cada_comprador_ve_solo_sus_ofertas(entorno):
    cid = str(uuid.uuid4())
    guardar_campana(entorno, cid)
    for sub in ("comp-1", "comp-2"):
        oid = str(uuid.uuid4())
        entorno.tabla.put_item(Item={"PK": "CAMP#" + cid, "SK": "OFFER#" + oid, "entidad": "OFERTA", "ofertaId": oid, "campaniaId": cid,
                                     "compradorSub": sub, "compradorNombre": sub, "volumenKg": 10, "precioCentimosPorKg": 100,
                                     "modalidad": "Pago ahora", "logistica": "Recojo", "fechaEntrega": FUTURO, "totalCentimos": 1000,
                                     "estado": "PENDIENTE", "creadoEn": "2026-10-04T05:00:00Z",
                                     "usuarioClave": "USER#" + sub, "usuarioOrden": "OFFER#2026-10-04T05:00:00Z#" + oid})
    assert len(entorno.cliente.get("/api/v1/campanas/" + cid + "/ofertas", headers=AGRI).json()["items"]) == 2
    propias = entorno.cliente.get("/api/v1/campanas/" + cid + "/ofertas", headers=COMP).json()["items"]
    assert [o["compradorNombre"] for o in propias] == ["comp-1"] and propias[0]["total"] == "10.00"
    assert len(entorno.cliente.get("/api/v1/ofertas", headers=COMP2).json()["items"]) == 1


def test_padron_asigna_una_vez_y_se_agota(entorno):
    dni = {"tipoDoc": "DNI", "documento": "87654321", "uso": "representante"}
    a = entorno.cliente.post("/api/v1/padron/consulta", json=dni, headers=COMP)
    assert a.status_code == 200 and a.json()["demo"] is True and a.json()["documento"] == "87654321"
    #repetir la consulta devuelve lo mismo y no gasta otro registro
    assert entorno.cliente.post("/api/v1/padron/consulta", json=dni, headers=COMP).json()["nombres"] == a.json()["nombres"]
    b = entorno.cliente.post("/api/v1/padron/consulta", json=dni, headers=COMP2)
    assert b.status_code == 200 and b.json()["nombres"] != a.json()["nombres"]
    c = entorno.cliente.post("/api/v1/padron/consulta", json=dni, headers=quien("comp-3", "comprador"))
    assert c.status_code == 503 and "no disponible" in c.json()["detail"]
    ruc = {"tipoDoc": "RUC", "documento": "20123456789", "uso": "comprador"}
    assert entorno.cliente.post("/api/v1/padron/consulta", json=ruc, headers=COMP).json()["razonSocial"] in ("Empresa Prueba SAC", "Otra Empresa SAC")


def test_padron_consume_de_su_tabla_y_registra_asignacion(entorno):
    #decision 58: delete en agro-padron-empresas + put de la asignacion en agro-datos, en una transaccion
    ruc = {"tipoDoc": "RUC", "documento": "20123456789", "uso": "comprador"}
    a = entorno.cliente.post("/api/v1/padron/consulta", json=ruc, headers=COMP).json()
    b = entorno.cliente.post("/api/v1/padron/consulta", json=ruc, headers=COMP2).json()
    assert a["razonSocial"] != b["razonSocial"] and "id" not in a and "entidad" not in a
    assert entorno.empresas.scan()["Items"] == []
    asignacion = entorno.tabla.get_item(Key={"PK": "USER#comp-1", "SK": "PADRON#comprador#RUC"})["Item"]
    assert asignacion["entidad"] == "PADRON_ASIGNADO" and asignacion["origen"] in ("EMPRESA#e01", "EMPRESA#e02")
    assert asignacion["datos"]["razonSocial"] == a["razonSocial"]
    #las personas no se tocan al consumir empresas
    assert len(entorno.personas.scan()["Items"]) == 2
    c = entorno.cliente.post("/api/v1/padron/consulta", json=ruc, headers=quien("comp-3", "comprador"))
    assert c.status_code == 503


def test_padron_no_queda_en_agro_datos(entorno):
    assert entorno.tabla.query(KeyConditionExpression=Key("PK").eq("PADRON#EMPRESA"))["Items"] == []


def test_padron_validaciones(entorno):
    assert entorno.cliente.post("/api/v1/padron/consulta", json={"tipoDoc": "RUC", "documento": "12345678", "uso": "comprador"}, headers=COMP).status_code == 422
    assert entorno.cliente.post("/api/v1/padron/consulta", json={"tipoDoc": "DNI", "documento": "12345678", "uso": "comprador"}, headers=AGRI).status_code == 403


def test_cuentas_demo_ordenadas(entorno):
    r = entorno.cliente.get("/api/v1/cuentas-demo", headers=COMP).json()
    assert [c["id"] for c in r] == ["c1", "c2"]


def test_url_de_foto(entorno):
    cid, fid = str(uuid.uuid4()), str(uuid.uuid4())
    r = entorno.cliente.post("/api/v1/campanas/" + cid + "/fotos/url", json={"fotoId": fid, "tipoContenido": "image/png", "tamanoBytes": 1000}, headers=AGRI)
    assert r.status_code == 200
    assert r.json()["campos"]["key"] == "entrada/agri-1/" + cid + "/" + fid + ".png"
    grande = {"fotoId": fid, "tipoContenido": "image/png", "tamanoBytes": 6000000}
    assert entorno.cliente.post("/api/v1/campanas/" + cid + "/fotos/url", json=grande, headers=AGRI).status_code == 422
    guardar_campana(entorno, cid, dueno="agri-2")
    assert entorno.cliente.post("/api/v1/campanas/" + cid + "/fotos/url", json=dict(grande, tamanoBytes=10), headers=AGRI).status_code == 403


def test_perfil_comprador_con_dni_y_reglas(entorno):
    base = {"rol": "comprador", "tipoDoc": "DNI", "documento": "45678912", "razonSocial": "Ana Prueba", "contactoNombre": "Ana Prueba", "contactoCelular": "912345678"}
    #el documento debe ser el usuario de la cuenta
    h = dict(quien("comp-9", "comprador"), **{"x-prueba-doc": "45678912"})
    assert entorno.cliente.post("/api/v1/perfil", json=dict(base, documento="11111111"), headers=h).status_code == 403
    assert entorno.cliente.post("/api/v1/perfil", json=dict(base, tipoDoc="RUC"), headers=h).status_code == 422
    assert entorno.cliente.post("/api/v1/perfil", json=dict(base, cuentaCargoId="no-existe"), headers=h).status_code == 422
    r = entorno.cliente.post("/api/v1/perfil", json=base, headers=h)
    assert r.status_code == 201 and r.json()["tipoDoc"] == "DNI"


#decision 66: update directo y condicional de la campana
def test_actualizar_campana_sin_ofertas(entorno):
    cid = str(uuid.uuid4())
    guardar_campana(entorno, cid)
    r = entorno.cliente.patch("/api/v1/campanas/" + cid, json={"volumenKg": 1500, "precioAhoraPorKg": "1.95"}, headers=AGRI)
    assert r.status_code == 200, r.text
    assert r.json()["volumenKg"] == 1500 and r.json()["precioAhoraPorKg"] == "1.95" and r.json()["precioContraentregaPorKg"] == "2.10"
    item = entorno.tabla.get_item(Key={"PK": "CAMP#" + cid, "SK": "META"})["Item"]
    assert item["precioAhoraCentimosPorKg"] == 195 and "actualizadoEn" in item
    #los indices no cambian
    assert item["publicadaClave"] == "PUB#papa#Cusco"


def test_actualizar_campana_reglas(entorno):
    cid = str(uuid.uuid4())
    guardar_campana(entorno, cid)
    ruta = "/api/v1/campanas/" + cid
    assert entorno.cliente.patch(ruta, json={"volumenKg": 10}, headers=AGRI2).status_code == 403
    assert entorno.cliente.patch(ruta, json={"volumenKg": 10}, headers=COMP).status_code == 403
    assert entorno.cliente.patch(ruta, json={}, headers=AGRI).status_code == 422
    assert entorno.cliente.patch(ruta, json={"cultivo": "maiz"}, headers=AGRI).status_code == 422
    assert entorno.cliente.patch(ruta, json={"precioAhoraPorKg": "0.00"}, headers=AGRI).status_code == 422
    assert entorno.cliente.patch("/api/v1/campanas/" + str(uuid.uuid4()), json={"volumenKg": 10}, headers=AGRI).status_code == 404
    assert entorno.cliente.patch(ruta, json={"volumenKg": 10}).status_code == 401


def test_actualizar_campana_con_ofertas_da_409(entorno):
    cid = str(uuid.uuid4())
    guardar_campana(entorno, cid)
    entorno.tabla.update_item(Key={"PK": "CAMP#" + cid, "SK": "META"}, UpdateExpression="SET numeroOfertas = :n",
                              ExpressionAttributeValues={":n": 1})
    r = entorno.cliente.patch("/api/v1/campanas/" + cid, json={"volumenKg": 100}, headers=AGRI)
    assert r.status_code == 409 and r.headers["content-type"].startswith("application/problem+json")


def test_condicion_de_dynamodb_detiene_la_carrera(entorno):
    #si llega una oferta entre la lectura y el update, la condicion numeroOfertas = 0 lo rechaza
    from app.datos import datos as fabrica
    cid = str(uuid.uuid4())
    guardar_campana(entorno, cid)
    entorno.tabla.update_item(Key={"PK": "CAMP#" + cid, "SK": "META"}, UpdateExpression="SET numeroOfertas = :n",
                              ExpressionAttributeValues={":n": 1})
    assert fabrica().actualizar_campana(cid, "agri-1", {"volumenKg": 5}) is None
