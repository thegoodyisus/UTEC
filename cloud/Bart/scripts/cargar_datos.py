"""Carga los CSV dummy de Data/ a DynamoDB (montos como Decimal, nunca float).

Uso (desde la raiz del proyecto):
    source scripts/credenciales.sh
    .venv/bin/python scripts/cargar_datos.py rcc [--stage dev]
Conjuntos: rcc (central de riesgo), productos y ofertas (estos dos cuando exista el microservicio Solicitudes).
Sobrescribe items con la misma clave; es idempotente. Al final cuenta los items de la tabla.
"""
import argparse
import csv
import json
import pathlib
import re
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CONJUNTOS = {
    "rcc": ("rcc_evaluacion_clientes.csv", "bart-rcc-evaluacion-clientes-{stage}"),
    "productos": ("productos.csv", "bart-productos-{stage}"),
    "ofertas": ("ofertas_preaprobadas.csv", "bart-ofertas-preaprobadas-{stage}"),
}
NUMERO = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
SIEMPRE_TEXTO = {"documento", "periodo", "version", "oferta_id", "sbs_customer_id"}


def convertir(fila):
    item = {}
    for k, v in fila.items():
        if v == "":
            continue  # DynamoDB: el atributo vacio no se guarda
        if k == "lineas_json":
            item["lineas"] = json.loads(v, parse_float=Decimal)
        elif v in ("true", "false"):
            item[k] = v == "true"
        elif k not in SIEMPRE_TEXTO and NUMERO.match(v):
            item[k] = Decimal(v)
        else:
            item[k] = v
    return item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("conjunto", choices=sorted(CONJUNTOS))
    ap.add_argument("--stage", default="dev")
    args = ap.parse_args()
    archivo, plantilla = CONJUNTOS[args.conjunto]
    nombre_tabla = plantilla.format(stage=args.stage)
    tabla = boto3.resource("dynamodb").Table(nombre_tabla)
    try:
        tabla.load()
    except ClientError as e:
        raise SystemExit("No existe o no se puede leer la tabla %s (%s): despliega primero el microservicio"
                         % (nombre_tabla, e.response["Error"]["Code"]))

    filas = list(csv.DictReader((RAIZ / "Data" / archivo).read_text(encoding="utf-8").splitlines()))
    with tabla.batch_writer() as lote:
        for fila in filas:
            lote.put_item(Item=convertir(fila))

    total, kwargs = 0, {"Select": "COUNT"}
    while True:  # conteo de verificacion (tabla pequena; la API nunca usa Scan)
        r = tabla.scan(**kwargs)
        total += r["Count"]
        if "LastEvaluatedKey" not in r:
            break
        kwargs["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    print("%s: %d filas del CSV cargadas; la tabla %s tiene %d items" % (archivo, len(filas), nombre_tabla, total))


if __name__ == "__main__":
    main()
