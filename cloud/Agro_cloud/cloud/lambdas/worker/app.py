#lambda worker: cola agro-insercion -> dynamodb (decision 5)
#idempotente: escritura condicional attribute_not_exists(PK); un duplicado se da por procesado
#oferta: misma transaccion registra la oferta e incrementa numeroOfertas de la campana (sin doble conteo)
import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)
TABLA = os.environ["TABLA"]
cliente = boto3.resource("dynamodb").meta.client


class MensajeInvalido(Exception):
    pass


def guardar_campana(item):
    if not (item.get("PK", "").startswith("CAMP#") and item.get("SK") == "META"):
        raise MensajeInvalido("claves de campana invalidas")
    try:
        cliente.put_item(TableName=TABLA, Item=item, ConditionExpression="attribute_not_exists(PK)")
        log.info("campana registrada %s", item["PK"])
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        log.info("campana ya existia %s (duplicado ignorado)", item["PK"])


def guardar_oferta(item):
    if not (item.get("PK", "").startswith("CAMP#") and item.get("SK", "").startswith("OFFER#")):
        raise MensajeInvalido("claves de oferta invalidas")
    try:
        cliente.transact_write_items(TransactItems=[
            {"Put": {"TableName": TABLA, "Item": item, "ConditionExpression": "attribute_not_exists(PK)"}},
            {"Update": {"TableName": TABLA, "Key": {"PK": item["PK"], "SK": "META"},
                        "UpdateExpression": "SET numeroOfertas = if_not_exists(numeroOfertas, :cero) + :uno",
                        "ConditionExpression": "attribute_exists(PK)",
                        "ExpressionAttributeValues": {":cero": 0, ":uno": 1}}},
        ])
        log.info("oferta registrada %s %s", item["PK"], item["SK"])
    except ClientError as e:
        if e.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        razones = [r.get("Code") for r in e.response.get("CancellationReasons", [])]
        if razones and razones[0] == "ConditionalCheckFailed":
            log.info("oferta ya existia %s (duplicado ignorado)", item["SK"])
            return
        #la campana aun no existe: se reintenta (si nunca aparece, el mensaje termina en la dlq)
        raise


def procesar(cuerpo):
    tipo, item = cuerpo.get("tipo"), cuerpo.get("item")
    if not isinstance(item, dict):
        raise MensajeInvalido("mensaje sin item")
    if tipo == "campana":
        guardar_campana(item)
    elif tipo == "oferta":
        guardar_oferta(item)
    else:
        raise MensajeInvalido("tipo desconocido: " + str(tipo))


def handler(event, context):
    fallos = []
    for registro in event.get("Records", []):
        try:
            procesar(json.loads(registro["body"]))
        except Exception:
            log.exception("fallo el mensaje %s", registro.get("messageId"))
            fallos.append({"itemIdentifier": registro["messageId"]})
    return {"batchItemFailures": fallos}
