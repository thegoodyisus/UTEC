#acceso a dynamodb, sqs y s3 segun docs/modelo-datos.md
import base64
import binascii
import json
import os
import random
import time
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config
from botocore.exceptions import ClientError

from .errores import Problema

CATALOGO_TTL_S = 60
#indices de agro-datos (decision 58): nombre -> (atributo de particion, atributo de orden)
INDICES = {
    "por-usuario": ("usuarioClave", "usuarioOrden"),
    "publicadas-por-cultivo": ("publicadaClave", "publicadaOrden"),
}


def ahora_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def limpio(valor):
    #dynamodb devuelve decimal: se pasa a int para json
    if isinstance(valor, list):
        return [limpio(v) for v in valor]
    if isinstance(valor, dict):
        return {k: limpio(v) for k, v in valor.items()}
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    return valor


def cursor_a_clave(cursor):
    if not cursor:
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode() + b"==").decode())
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise Problema(422, "cursor invalido")


def clave_a_cursor(clave):
    if not clave:
        return None
    return base64.urlsafe_b64encode(json.dumps(clave, default=str).encode()).decode().rstrip("=")


class Datos:
    def __init__(self):
        region = os.environ.get("REGION_AWS", "us-east-1")
        self.ddb = boto3.resource("dynamodb", region_name=region)
        self.nombre_tabla = os.environ["TABLA"]
        self.tabla = self.ddb.Table(self.nombre_tabla)
        #padron en tablas propias: tipoDoc -> (tabla, prefijo de origen)
        self.padron = {
            "RUC": (os.environ["TABLA_PADRON_EMPRESAS"], "EMPRESA#"),
            "DNI": (os.environ["TABLA_PADRON_PERSONAS"], "PERSONA#"),
        }
        self.cliente = self.ddb.meta.client
        self.sqs = boto3.client("sqs", region_name=region)
        self.s3 = boto3.client("s3", region_name=region, config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
        self.cola = os.environ["COLA_INSERCION_URL"]
        self.bucket = os.environ["BUCKET_FOTOS"]
        self._catalogo = None
        self._catalogo_hasta = 0

    def obtener(self, pk, sk, consistente=False):
        r = self.tabla.get_item(Key={"PK": pk, "SK": sk}, ConsistentRead=consistente)
        return limpio(r["Item"]) if "Item" in r else None

    def crear(self, item):
        try:
            self.tabla.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def actualizar_campana(self, campania_id, dueno, cambios):
        #update directo y condicional: existe, es del dueno y no tiene ofertas (decision 66)
        nombres = {"#" + k: k for k in cambios}
        valores = {":" + k: v for k, v in cambios.items()}
        valores.update({":dueno": dueno, ":cero": 0, ":ahora": ahora_iso()})
        try:
            r = self.tabla.update_item(
                Key={"PK": "CAMP#" + campania_id, "SK": "META"},
                UpdateExpression="SET " + ", ".join("#%s = :%s" % (k, k) for k in cambios) + ", actualizadoEn = :ahora",
                ConditionExpression="attribute_exists(PK) AND propietarioSub = :dueno AND numeroOfertas = :cero",
                ExpressionAttributeNames=nombres, ExpressionAttributeValues=valores, ReturnValues="ALL_NEW")
            return limpio(r["Attributes"])
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return None
            raise

    def condicion(self, pk_valor, prefijo, indice=None):
        #dynamodb no acepta begins_with con texto vacio: sin prefijo se consulta solo por la particion
        pk, sk = INDICES[indice] if indice else ("PK", "SK")
        condicion = Key(pk).eq(pk_valor)
        return condicion & Key(sk).begins_with(prefijo) if prefijo else condicion

    def consultar(self, pk_valor, prefijo, limite=50, cursor=None, adelante=True, indice=None):
        condicion = self.condicion(pk_valor, prefijo, indice)
        kw = {"KeyConditionExpression": condicion, "Limit": limite, "ScanIndexForward": adelante}
        if indice:
            kw["IndexName"] = indice
        inicio = cursor_a_clave(cursor)
        if inicio:
            kw["ExclusiveStartKey"] = inicio
        r = self.tabla.query(**kw)
        return limpio(r.get("Items", [])), clave_a_cursor(r.get("LastEvaluatedKey"))

    def todos(self, pk_valor, prefijo, consistente=False):
        items, inicio = [], None
        while True:
            kw = {"KeyConditionExpression": self.condicion(pk_valor, prefijo), "ConsistentRead": consistente}
            if inicio:
                kw["ExclusiveStartKey"] = inicio
            r = self.tabla.query(**kw)
            items += limpio(r.get("Items", []))
            inicio = r.get("LastEvaluatedKey")
            if not inicio:
                return items

    def catalogo(self):
        if self._catalogo is None or time.time() > self._catalogo_hasta:
            cultivos = self.todos("CATALOGO", "CULTIVO#")
            self._catalogo = {c["slug"]: c for c in sorted(cultivos, key=lambda c: c.get("orden", 99))}
            self._catalogo_hasta = time.time() + CATALOGO_TTL_S
        return self._catalogo

    def encolar(self, tipo, item):
        #el worker escribe con attribute_not_exists(PK): reenviar no duplica
        self.sqs.send_message(QueueUrl=self.cola, MessageBody=json.dumps({"tipo": tipo, "item": item}, ensure_ascii=False))

    def url_subida(self, clave, tipo_contenido, segundos=300):
        return self.s3.generate_presigned_post(
            Bucket=self.bucket, Key=clave, Fields={"Content-Type": tipo_contenido},
            Conditions=[{"Content-Type": tipo_contenido}, ["content-length-range", 1, 5242880]], ExpiresIn=segundos)

    def url_lectura(self, clave, segundos=300):
        return self.s3.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": clave}, ExpiresIn=segundos)

    def tomar_padron(self, sub, uso, tipo_doc):
        #una asignacion por usuario, uso y tipo; el registro se borra de su tabla de padron al asignarse (no se repite)
        asignacion = {"PK": "USER#" + sub, "SK": "PADRON#" + uso + "#" + tipo_doc}
        previo = self.obtener(asignacion["PK"], asignacion["SK"], consistente=True)
        if previo:
            return previo["datos"]
        tabla_padron, prefijo = self.padron["RUC" if tipo_doc == "RUC" else "DNI"]
        candidatos = self.leer_padron(tabla_padron)
        random.shuffle(candidatos)
        for c in candidatos:
            datos = {k: v for k, v in c.items() if k not in ("id", "entidad")}
            try:
                self.cliente.transact_write_items(TransactItems=[
                    {"Delete": {"TableName": tabla_padron, "Key": {"id": c["id"]},
                                "ConditionExpression": "attribute_exists(id)"}},
                    {"Put": {"TableName": self.nombre_tabla,
                             "Item": dict(asignacion, entidad="PADRON_ASIGNADO", datos=datos, origen=prefijo + c["id"], creadoEn=ahora_iso()),
                             "ConditionExpression": "attribute_not_exists(PK)"}},
                ])
                return datos
            except ClientError as e:
                if e.response["Error"]["Code"] != "TransactionCanceledException":
                    raise
                #otro usuario tomo ese registro o esta misma persona ya tiene asignacion
                previo = self.obtener(asignacion["PK"], asignacion["SK"], consistente=True)
                if previo:
                    return previo["datos"]
        return None

    def leer_padron(self, tabla_padron):
        #a lo mas 10 registros por tabla: scan consistente es suficiente
        tabla, items, inicio = self.ddb.Table(tabla_padron), [], None
        while True:
            kw = {"ConsistentRead": True}
            if inicio:
                kw["ExclusiveStartKey"] = inicio
            r = tabla.scan(**kw)
            items += limpio(r.get("Items", []))
            inicio = r.get("LastEvaluatedKey")
            if not inicio:
                return items


@lru_cache(maxsize=1)
def datos():
    if not all(os.environ.get(v) for v in ("TABLA", "TABLA_PADRON_PERSONAS", "TABLA_PADRON_EMPRESAS")):
        raise Problema(503, "configuracion de datos incompleta")
    return Datos()
