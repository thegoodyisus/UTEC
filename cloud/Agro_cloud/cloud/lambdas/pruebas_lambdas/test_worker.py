#worker: idempotencia y contador de ofertas contra dynamodb simulado
import importlib.util
import json
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

os.environ.update({"AWS_ACCESS_KEY_ID": "prueba", "AWS_SECRET_ACCESS_KEY": "prueba", "AWS_DEFAULT_REGION": "us-east-1", "TABLA": "agro-datos"})
RUTA = Path(__file__).resolve().parents[1] / "worker" / "app.py"


def crear_tabla():
    boto3.client("dynamodb").create_table(
        TableName="agro-datos", BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"}, {"AttributeName": "SK", "AttributeType": "S"}])
    return boto3.resource("dynamodb").Table("agro-datos")


@pytest.fixture
def entorno():
    with mock_aws():
        tabla = crear_tabla()
        spec = importlib.util.spec_from_file_location("worker_app", RUTA)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        yield modulo, tabla


def evento(*cuerpos):
    return {"Records": [{"messageId": "m%d" % i, "body": c if isinstance(c, str) else json.dumps(c)} for i, c in enumerate(cuerpos)]}


CAMP = {"PK": "CAMP#c1", "SK": "META", "entidad": "CAMPANA", "volumenKg": 100, "numeroOfertas": 0}
OFERTA = {"PK": "CAMP#c1", "SK": "OFFER#o1", "entidad": "OFERTA", "totalCentimos": 1000}


def test_campana_duplicada_no_falla_ni_duplica(entorno):
    w, tabla = entorno
    r = w.handler(evento({"tipo": "campana", "item": CAMP}, {"tipo": "campana", "item": dict(CAMP, volumenKg=999)}), None)
    assert r == {"batchItemFailures": []}
    assert tabla.get_item(Key={"PK": "CAMP#c1", "SK": "META"})["Item"]["volumenKg"] == 100


def test_oferta_incrementa_contador_una_sola_vez(entorno):
    w, tabla = entorno
    w.handler(evento({"tipo": "campana", "item": CAMP}), None)
    r = w.handler(evento({"tipo": "oferta", "item": OFERTA}, {"tipo": "oferta", "item": OFERTA}), None)
    assert r == {"batchItemFailures": []}
    assert tabla.get_item(Key={"PK": "CAMP#c1", "SK": "META"})["Item"]["numeroOfertas"] == 1
    assert "Item" in tabla.get_item(Key={"PK": "CAMP#c1", "SK": "OFFER#o1"})


def test_oferta_sin_campana_se_reintenta(entorno):
    w, _ = entorno
    assert w.handler(evento({"tipo": "oferta", "item": OFERTA}), None) == {"batchItemFailures": [{"itemIdentifier": "m0"}]}


def test_mensajes_invalidos_fallan_solos(entorno):
    w, _ = entorno
    r = w.handler(evento("no es json", {"tipo": "otro", "item": {}}, {"tipo": "campana", "item": {"PK": "USER#x", "SK": "META"}}, {"tipo": "campana", "item": CAMP}), None)
    assert [f["itemIdentifier"] for f in r["batchItemFailures"]] == ["m0", "m1", "m2"]


def test_campana_y_oferta_quedan_en_los_indices_con_nombres_funcionales(entorno):
    #decision 58: el worker escribe el item tal cual lo arma la api; los indices lo ven por usuarioClave y publicadaClave
    w, _ = entorno
    ddb = boto3.client("dynamodb")
    ddb.delete_table(TableName="agro-datos")
    gsi = lambda n, pk, sk: {"IndexName": n, "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}, {"AttributeName": sk, "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}}
    ddb.create_table(
        TableName="agro-datos", BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK", "usuarioClave", "usuarioOrden", "publicadaClave", "publicadaOrden")],
        GlobalSecondaryIndexes=[gsi("por-usuario", "usuarioClave", "usuarioOrden"), gsi("publicadas-por-cultivo", "publicadaClave", "publicadaOrden")])
    camp = dict(CAMP, usuarioClave="USER#a1", usuarioOrden="CAMP#2026-10-05T00:00:00Z#c1",
                publicadaClave="PUB#papa#Cusco", publicadaOrden="2027-01-01#c1")
    oferta = dict(OFERTA, usuarioClave="USER#b1", usuarioOrden="OFFER#2026-10-05T00:00:00Z#o1")
    assert w.handler(evento({"tipo": "campana", "item": camp}, {"tipo": "oferta", "item": oferta}), None) == {"batchItemFailures": []}
    q = lambda indice, atributo, valor: ddb.query(TableName="agro-datos", IndexName=indice, KeyConditionExpression="#a = :v",
                                                   ExpressionAttributeNames={"#a": atributo}, ExpressionAttributeValues={":v": {"S": valor}})["Items"]
    assert [i["SK"]["S"] for i in q("por-usuario", "usuarioClave", "USER#a1")] == ["META"]
    assert [i["PK"]["S"] for i in q("publicadas-por-cultivo", "publicadaClave", "PUB#papa#Cusco")] == ["CAMP#c1"]
    assert [i["SK"]["S"] for i in q("por-usuario", "usuarioClave", "USER#b1")] == ["OFFER#o1"]
