#entorno de pruebas: aws simulado con moto y usuario falso por cabeceras (sin cognito)
import os
from types import SimpleNamespace

import boto3
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from moto import mock_aws

os.environ.update({
    "TABLA": "agro-datos", "TABLA_PADRON_PERSONAS": "agro-padron-personas", "TABLA_PADRON_EMPRESAS": "agro-padron-empresas",
    "COLA_INSERCION_URL": "pendiente", "BUCKET_FOTOS": "agro-fotos-prueba",
    "REGION_AWS": "us-east-1", "USER_POOL_ID": "us-east-1_prueba", "CLIENT_ID": "cliente-prueba",
    "AWS_ACCESS_KEY_ID": "prueba", "AWS_SECRET_ACCESS_KEY": "prueba", "AWS_DEFAULT_REGION": "us-east-1",
})

CATALOGO = [
    {"PK": "CATALOGO", "SK": "CULTIVO#papa", "slug": "papa", "nombre": "Papa", "orden": 1, "referenciaMercadoCentimosPorKg": 120, "etiquetasRekognition": ["Potato"]},
    {"PK": "CATALOGO", "SK": "CULTIVO#maiz", "slug": "maiz", "nombre": "Maíz", "orden": 2, "referenciaMercadoCentimosPorKg": 110, "etiquetasRekognition": ["Corn"]},
]
#padron en tablas propias con clave simple id (decision 58)
PERSONAS = [
    {"id": "p01", "entidad": "PADRON_PERSONA", "nombres": "Ana", "apellidos": "Prueba Uno", "celular": "900000001", "correo": "ana@correo.example"},
    {"id": "p02", "entidad": "PADRON_PERSONA", "nombres": "Beto", "apellidos": "Prueba Dos", "celular": "900000002", "correo": "beto@correo.example"},
]
EMPRESAS = [
    {"id": "e01", "entidad": "PADRON_EMPRESA", "razonSocial": "Empresa Prueba SAC", "direccionFiscal": "Calle 1", "actividad": "Acopio", "estado": "Activo · Habido"},
    {"id": "e02", "entidad": "PADRON_EMPRESA", "razonSocial": "Otra Empresa SAC", "direccionFiscal": "Calle 2", "actividad": "Molino", "estado": "Activo · Habido"},
]
CUENTAS = [
    {"PK": "CUENTA_DEMO", "SK": "CUENTA#c2", "id": "c2", "orden": 2, "titulo": "Cuenta 2", "descripcion": "Cuenta ficticia"},
    {"PK": "CUENTA_DEMO", "SK": "CUENTA#c1", "id": "c1", "orden": 1, "titulo": "Cuenta 1", "descripcion": "Cuenta ficticia"},
]


#mismos nombres que terraform/dynamodb.tf
INDICES = {"por-usuario": ("usuarioClave", "usuarioOrden"), "publicadas-por-cultivo": ("publicadaClave", "publicadaOrden")}


def crear_tablas(ddb):
    gsi = lambda n, pk, sk: {"IndexName": n, "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}, {"AttributeName": sk, "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}}
    ddb.create_table(
        TableName="agro-datos", BillingMode="PAY_PER_REQUEST",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("PK", "SK") + sum(INDICES.values(), ())],
        GlobalSecondaryIndexes=[gsi(n, pk, sk) for n, (pk, sk) in INDICES.items()],
    )
    for nombre in ("agro-padron-personas", "agro-padron-empresas"):
        ddb.create_table(TableName=nombre, BillingMode="PAY_PER_REQUEST",
                         KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                         AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}])


def usuario_falso(request: Request):
    from app.errores import Problema
    from app.seguridad import Usuario
    sub = request.headers.get("x-prueba-sub")
    if not sub:
        raise Problema(401, "falta el token bearer")
    return Usuario(sub=sub, rol=request.headers.get("x-prueba-rol", "agricultor"), documento=request.headers.get("x-prueba-doc", ""))


@pytest.fixture
def entorno():
    with mock_aws():
        crear_tablas(boto3.client("dynamodb", region_name="us-east-1"))
        recurso = boto3.resource("dynamodb", region_name="us-east-1")
        tabla = recurso.Table("agro-datos")
        for item in CATALOGO + CUENTAS:
            tabla.put_item(Item=item)
        personas, empresas = recurso.Table("agro-padron-personas"), recurso.Table("agro-padron-empresas")
        for t, items in ((personas, PERSONAS), (empresas, EMPRESAS)):
            for item in items:
                t.put_item(Item=item)
        sqs = boto3.client("sqs", region_name="us-east-1")
        os.environ["COLA_INSERCION_URL"] = sqs.create_queue(QueueName="agro-insercion")["QueueUrl"]
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="agro-fotos-prueba")
        from app import datos as modulo_datos
        from app.main import app
        from app.seguridad import usuario_actual
        modulo_datos.datos.cache_clear()
        app.dependency_overrides[usuario_actual] = usuario_falso
        yield SimpleNamespace(cliente=TestClient(app), tabla=tabla, personas=personas, empresas=empresas, sqs=sqs, cola=os.environ["COLA_INSERCION_URL"])
        app.dependency_overrides.clear()
        modulo_datos.datos.cache_clear()


def quien(sub, rol):
    return {"x-prueba-sub": sub, "x-prueba-rol": rol}
