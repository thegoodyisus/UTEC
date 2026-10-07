#la coleccion de thunder client cubre el contrato y sus peticiones funcionan en orden contra aws simulado
import json
import re
import uuid

import coleccion

USUARIOS = {
    "tokenAgricultor": {"x-prueba-sub": "agri-col", "x-prueba-rol": "agricultor", "x-prueba-doc": "12345678"},
    "tokenComprador": {"x-prueba-sub": "comp-col", "x-prueba-rol": "comprador", "x-prueba-doc": "20123456789"},
}


def test_cubre_todas_las_apis_del_contrato():
    archivos = coleccion.generar()
    rutas = {r["method"] + " " + r["url"] for r in archivos["thunder-collection_AgroCredit.json"]["requests"]}
    assert len(rutas) >= len(coleccion.DESTINOS)
    assert set(archivos["api-tablas.json"]) == set(coleccion.DESTINOS)


def test_es_determinista():
    assert json.dumps(coleccion.generar(), sort_keys=True) == json.dumps(coleccion.generar(), sort_keys=True)


def test_secuencia_completa_contra_la_api(entorno):
    #la cuenta de cargo del ejemplo del contrato debe existir como en semillas.py
    entorno.tabla.put_item(Item={"PK": "CUENTA_DEMO", "SK": "CUENTA#cc-8830", "id": "cc-8830", "orden": 0,
                                 "titulo": "Cuenta", "descripcion": "Cuenta ficticia"})
    variables = {v[0]: v[1] for v in coleccion.ENTORNO}
    variables["baseUrl"] = "/api/v1"

    def sustituir(texto):
        texto = texto.replace("{{#guid}}", str(uuid.uuid4()))
        return re.sub(r"\{\{(\w+)\}\}", lambda m: variables[m.group(1)], texto)

    for r in coleccion.generar()["thunder-collection_AgroCredit.json"]["requests"]:
        cabeceras = {}
        if "auth" in r:
            cabeceras.update(USUARIOS[r["auth"]["bearer"].strip("{}")])
        cuerpo = json.loads(sustituir(r["body"]["raw"])) if "body" in r else None
        resp = entorno.cliente.request(r["method"], sustituir(r["url"]), json=cuerpo, headers=cabeceras)
        esperado = int(r["tests"][0]["value"])
        assert resp.status_code == esperado, (r["name"], resp.status_code, resp.text)
        for t in r["tests"][1:]:
            variables[t["value"].strip("{}")] = resp.json()[t["custom"].split(".", 1)[1]]
        #el worker escribe lo encolado (su logica se prueba en pruebas_lambdas)
        if esperado == 202:
            for m in entorno.sqs.receive_message(QueueUrl=entorno.cola, MaxNumberOfMessages=10).get("Messages", []):
                msg = json.loads(m["Body"])
                entorno.tabla.put_item(Item=msg["item"])
                if msg["tipo"] == "oferta":
                    entorno.tabla.update_item(Key={"PK": msg["item"]["PK"], "SK": "META"},
                                              UpdateExpression="ADD numeroOfertas :uno", ExpressionAttributeValues={":uno": 1})
                entorno.sqs.delete_message(QueueUrl=entorno.cola, ReceiptHandle=m["ReceiptHandle"])
    final = entorno.cliente.get("/api/v1/campanas/" + variables["campaniaId"], headers=USUARIOS["tokenAgricultor"]).json()
    assert final["numeroOfertas"] == 1
