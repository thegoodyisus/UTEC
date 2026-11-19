#!/usr/bin/env python3
"""Elimina de tu cuenta AWS todo lo que creo desplegar.py (para no gastar el presupuesto del laboratorio).

Uso:
    Mac / Linux:  python3 eliminar.py [--stage dev] [--si]
    Windows:      py eliminar.py [--stage dev] [--si]
Pide confirmacion escribiendo el nombre del stage (salvo --si). Vacia los 2 buckets y borra los 4 stacks en orden
inverso: web, Bart, Solicitudes y Central de riesgo (tablas, Lambdas, APIs, Step Functions y buckets). No se puede deshacer.
"""
import argparse
import sys

import desplegar as d


def vaciar_bucket(nombre):
    import boto3
    from botocore.exceptions import ClientError
    bucket = boto3.resource("s3").Bucket(nombre)
    try:
        borrados = sum(len(r.get("Deleted", [])) for r in bucket.object_versions.delete() or [])
        d.ok("bucket %s vaciado (%d objetos)" % (nombre, borrados))
    except ClientError as e:
        codigo = e.response["Error"]["Code"]
        if codigo in ("NoSuchBucket", "404"):
            d.ok("bucket %s no existe" % nombre)
        else:
            raise d.Fallo("No se pudo vaciar %s (%s)" % (nombre, codigo))


def main():
    ap = argparse.ArgumentParser(description="Elimina Bart de tu cuenta AWS.")
    ap.add_argument("--stage", default="dev")
    ap.add_argument("--si", action="store_true", help="no pedir confirmacion")
    args = ap.parse_args()
    env = d.cargar_credenciales()
    s, sufijo = args.stage, env["BART_SUFIJO"]
    print("Se eliminaran los stacks bart-web-%s, bart-chat-%s, bart-solicitudes-%s y bart-central-riesgo-%s" % (s, s, s, s))
    print("y los buckets bart-boletas-%s-%s y bart-web-%s-%s con todo su contenido. No se puede deshacer." % (s, sufijo, s, sufijo))
    if not args.si and input("Escribe el stage (%s) para confirmar: " % s).strip() != s:
        print("Cancelado.")
        return
    d.titulo(1, 2, "Vaciar buckets")
    vaciar_bucket("bart-web-%s-%s" % (s, sufijo))
    vaciar_bucket("bart-boletas-%s-%s" % (s, sufijo))
    d.titulo(2, 2, "Eliminar stacks (orden inverso)")
    import boto3
    from botocore.exceptions import ClientError
    cf = boto3.client("cloudformation")
    for nombre, carpeta, stack in reversed(d.SERVICIOS):
        try:
            existe = bool(cf.describe_stacks(StackName="%s-%s" % (stack, s))["Stacks"])
        except ClientError:  # "does not exist"
            existe = False
        if not existe:
            d.ok("%s-%s no existe" % (stack, s))
            continue
        sls = d.binario("serverless", carpeta if (carpeta / "node_modules").exists() else d.RAIZ)
        d.correr([sls, "remove", "--stage", s, "--region", "us-east-1"], carpeta, env, "remove_%s.log" % stack)
        d.ok("%s eliminado (%s-%s)" % (nombre, stack, s))
    print("\nListo: Bart (stage %s) eliminado de tu cuenta." % s)


if __name__ == "__main__":
    d.asegurar_venv()
    try:
        main()
    except d.Fallo as e:
        print("\nERROR: %s" % e, file=sys.stderr)
        sys.exit(1)
