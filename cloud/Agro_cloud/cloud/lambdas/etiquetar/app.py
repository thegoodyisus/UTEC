#lambda etiquetar: s3 entrada/<sub>/<campania>/<foto>.<ext> -> sqs -> rekognition -> catalogo en dynamodb
#copia a <sub>/<cultivo>_<yyyymmdd>_<hhmmss>.<ext> (hora de lima), borra el original y registra la foto (decision 6)
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote_plus

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)
TABLA = os.environ["TABLA"]
MIN_CONFIANZA = float(os.environ.get("MIN_CONFIANZA", "70"))
LIMA = timezone(timedelta(hours=-5))
#etiquetas demasiado generales que no identifican un cultivo
GENERICAS = {"food", "produce", "vegetable", "plant", "fruit", "grain", "seed", "nut", "bean", "market", "agriculture"}
CLAVE = re.compile(r"^entrada/([^/]+)/([0-9a-f-]{36})/([0-9a-f-]{36})\.(jpg|png)$")
CATALOGO_TTL_S = 60

tabla = boto3.resource("dynamodb").Table(TABLA)
s3 = boto3.client("s3")
rek = boto3.client("rekognition")
_catalogo = {"datos": None, "hasta": 0}


def catalogo():
    if _catalogo["datos"] is None or time.time() > _catalogo["hasta"]:
        r = tabla.query(KeyConditionExpression=Key("PK").eq("CATALOGO") & Key("SK").begins_with("CULTIVO#"))
        _catalogo["datos"] = r.get("Items", [])
        _catalogo["hasta"] = time.time() + CATALOGO_TTL_S
    return _catalogo["datos"]


def elegir_cultivo(etiquetas):
    #la etiqueta mas confiable que coincide con el catalogo (nombre o alias); si ninguna, sin-etiqueta
    mapa = {}
    for c in catalogo():
        for nombre in c.get("etiquetasRekognition", []):
            mapa[nombre.lower()] = c["slug"]
    for e in sorted(etiquetas, key=lambda x: -x.get("Confidence", 0)):
        nombres = [e.get("Name", "")] + [a.get("Name", "") for a in e.get("Aliases", [])]
        for n in nombres:
            if n.lower() in GENERICAS:
                continue
            if n.lower() in mapa:
                return mapa[n.lower()], int(round(e.get("Confidence", 0)))
    return "sin-etiqueta", 0


def existe(bucket, clave):
    try:
        s3.head_object(Bucket=bucket, Key=clave)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def registrar(sub, campania, foto, **campos):
    item = {"PK": "CAMP#" + campania, "SK": "FOTO#" + foto, "entidad": "FOTO", "fotoId": foto, "campaniaId": campania,
            "propietarioSub": sub, "creadoEn": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    item.update(campos)
    tabla.put_item(Item=item)


def procesar_objeto(bucket, clave):
    m = CLAVE.match(clave)
    if not m:
        log.warning("clave fuera de formato, se ignora: %s", clave)
        return
    sub, campania, foto, ext = m.groups()
    if not existe(bucket, clave):
        #reintento de un mensaje ya procesado: el original ya se movio
        log.info("el original ya no existe (ya procesado): %s", clave)
        return
    previo = tabla.get_item(Key={"PK": "CAMP#" + campania, "SK": "FOTO#" + foto}).get("Item")
    if previo and previo.get("s3Key"):
        #ya se copio y registro antes; solo faltaba borrar el original
        s3.delete_object(Bucket=bucket, Key=clave)
        return
    try:
        r = rek.detect_labels(Image={"S3Object": {"Bucket": bucket, "Name": clave}}, MaxLabels=20, MinConfidence=MIN_CONFIANZA)
    except ClientError as e:
        codigo = e.response["Error"]["Code"]
        if codigo in ("InvalidImageFormatException", "ImageTooLargeException", "InvalidS3ObjectException"):
            log.warning("rekognition no pudo leer la imagen %s: %s", clave, codigo)
            registrar(sub, campania, foto, estado="ERROR", label="sin-etiqueta", labelConfianza=0, etiquetasCrudas=[])
            return
        raise
    etiquetas = r.get("Labels", [])
    slug, confianza = elegir_cultivo(etiquetas)
    marca = datetime.now(LIMA).strftime("%Y%m%d_%H%M%S")
    destino = sub + "/" + slug + "_" + marca + "." + ext
    if existe(bucket, destino):
        destino = sub + "/" + slug + "_" + marca + "_" + foto[:8] + "." + ext
    s3.copy_object(Bucket=bucket, Key=destino, CopySource={"Bucket": bucket, "Key": clave}, MetadataDirective="COPY")
    crudas = [{"nombre": e.get("Name", ""), "confianza": int(round(e.get("Confidence", 0)))} for e in etiquetas[:10]]
    registrar(sub, campania, foto, estado="SIN_ETIQUETA" if slug == "sin-etiqueta" else "ETIQUETADA",
              label=slug, labelConfianza=confianza, etiquetasCrudas=crudas, s3Key=destino)
    s3.delete_object(Bucket=bucket, Key=clave)
    log.info("foto %s -> %s (%s %s%%)", clave, destino, slug, confianza)


def handler(event, context):
    fallos = []
    for registro in event.get("Records", []):
        try:
            evento = json.loads(registro["body"])
            if evento.get("Event") == "s3:TestEvent":
                continue
            for r in evento.get("Records", []):
                procesar_objeto(r["s3"]["bucket"]["name"], unquote_plus(r["s3"]["object"]["key"]))
        except Exception:
            log.exception("fallo el mensaje %s", registro.get("messageId"))
            fallos.append({"itemIdentifier": registro["messageId"]})
    return {"batchItemFailures": fallos}
