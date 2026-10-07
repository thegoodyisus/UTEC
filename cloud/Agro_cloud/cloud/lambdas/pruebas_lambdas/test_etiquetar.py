#etiquetar: mapeo contra el catalogo de la base, copia renombrada, borrado del original y registro
import importlib.util
import json
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

os.environ.update({"AWS_ACCESS_KEY_ID": "prueba", "AWS_SECRET_ACCESS_KEY": "prueba", "AWS_DEFAULT_REGION": "us-east-1", "TABLA": "agro-datos"})
RUTA = Path(__file__).resolve().parents[1] / "etiquetar" / "app.py"
BUCKET = "agro-fotos-prueba"
SUB, CAMP, FOTO = "sub-1", "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
CLAVE = "entrada/%s/%s/%s.jpg" % (SUB, CAMP, FOTO)


class RekFalso:
    def __init__(self, etiquetas):
        self.etiquetas = etiquetas

    def detect_labels(self, **kw):
        return {"Labels": self.etiquetas}


@pytest.fixture
def entorno():
    with mock_aws():
        boto3.client("dynamodb").create_table(
            TableName="agro-datos", BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"}, {"AttributeName": "SK", "AttributeType": "S"}])
        tabla = boto3.resource("dynamodb").Table("agro-datos")
        tabla.put_item(Item={"PK": "CATALOGO", "SK": "CULTIVO#papa", "slug": "papa", "etiquetasRekognition": ["Potato"]})
        tabla.put_item(Item={"PK": "CATALOGO", "SK": "CULTIVO#maiz", "slug": "maiz", "etiquetasRekognition": ["Corn", "Maize"]})
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket=BUCKET)
        s3.put_object(Bucket=BUCKET, Key=CLAVE, Body=b"imagen")
        spec = importlib.util.spec_from_file_location("etiquetar_app", RUTA)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        yield modulo, tabla, s3


def evento_s3(clave=CLAVE):
    cuerpo = {"Records": [{"s3": {"bucket": {"name": BUCKET}, "object": {"key": clave}}}]}
    return {"Records": [{"messageId": "m0", "body": json.dumps(cuerpo)}]}


def claves(s3):
    return sorted(o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET).get("Contents", []))


def test_papa_se_etiqueta_y_mueve(entorno):
    m, tabla, s3 = entorno
    m.rek = RekFalso([{"Name": "Food", "Confidence": 99.9}, {"Name": "Potato", "Confidence": 98.6}, {"Name": "Egg", "Confidence": 93}])
    assert m.handler(evento_s3(), None) == {"batchItemFailures": []}
    finales = claves(s3)
    assert len(finales) == 1 and finales[0].startswith(SUB + "/papa_") and finales[0].endswith(".jpg")
    foto = tabla.get_item(Key={"PK": "CAMP#" + CAMP, "SK": "FOTO#" + FOTO})["Item"]
    assert foto["estado"] == "ETIQUETADA" and foto["label"] == "papa" and foto["labelConfianza"] == 99 and foto["s3Key"] == finales[0]
    assert foto["propietarioSub"] == SUB


def test_alias_y_sin_coincidencia(entorno):
    m, tabla, s3 = entorno
    m.rek = RekFalso([{"Name": "Vegetable", "Confidence": 99}, {"Name": "Cob", "Confidence": 90, "Aliases": [{"Name": "Maize"}]}])
    m.handler(evento_s3(), None)
    assert tabla.get_item(Key={"PK": "CAMP#" + CAMP, "SK": "FOTO#" + FOTO})["Item"]["label"] == "maiz"
    s3.put_object(Bucket=BUCKET, Key=CLAVE.replace(FOTO, FOTO[:-1] + "3"), Body=b"x")
    m.rek = RekFalso([{"Name": "Car", "Confidence": 99}])
    m.handler(evento_s3(CLAVE.replace(FOTO, FOTO[:-1] + "3")), None)
    otra = tabla.get_item(Key={"PK": "CAMP#" + CAMP, "SK": "FOTO#" + FOTO[:-1] + "3"})["Item"]
    assert otra["estado"] == "SIN_ETIQUETA" and otra["s3Key"].startswith(SUB + "/sin-etiqueta_")


def test_reproceso_y_evento_de_prueba(entorno):
    m, tabla, s3 = entorno
    m.rek = RekFalso([{"Name": "Potato", "Confidence": 95}])
    m.handler(evento_s3(), None)
    #el mismo mensaje otra vez: el original ya no existe y no debe fallar ni duplicar
    assert m.handler(evento_s3(), None) == {"batchItemFailures": []}
    assert len(claves(s3)) == 1
    prueba = {"Records": [{"messageId": "t", "body": json.dumps({"Event": "s3:TestEvent"})}]}
    assert m.handler(prueba, None) == {"batchItemFailures": []}


def test_clave_fuera_de_formato_se_ignora(entorno):
    m, _, s3 = entorno
    m.rek = RekFalso([])
    assert m.handler(evento_s3("entrada/otra/cosa.gif"), None) == {"batchItemFailures": []}
