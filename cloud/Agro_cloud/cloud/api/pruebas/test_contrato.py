#prueba de deriva: la api implementada debe coincidir con openapi.yaml (rutas, metodos, codigos de exito, campos)
from pathlib import Path

import yaml

from app.main import app

METODOS = {"get", "post", "put", "patch", "delete"}
CONTRATO = yaml.safe_load((Path(__file__).resolve().parents[1] / "openapi.yaml").read_text(encoding="utf-8"))
GENERADO = app.openapi()


def resolver(doc, nodo):
    while isinstance(nodo, dict) and "$ref" in nodo:
        partes = nodo["$ref"].lstrip("#/").split("/")
        nodo = doc
        for p in partes:
            nodo = nodo[p]
    return nodo


def operaciones(doc, prefijo):
    salida = {}
    for ruta, ops in doc["paths"].items():
        if not ruta.startswith(prefijo):
            continue
        for metodo, op in ops.items():
            if metodo in METODOS:
                salida[(ruta[len(prefijo):] or "/", metodo)] = op
    return salida


C = operaciones(CONTRATO, "")
G = operaciones(GENERADO, "/api/v1")


def requeridos(doc, op):
    cuerpo = op.get("requestBody")
    if not cuerpo:
        return None
    esquema = resolver(doc, cuerpo["content"]["application/json"]["schema"])
    variantes = esquema.get("oneOf") or esquema.get("anyOf")
    if variantes:
        return sorted(tuple(sorted(resolver(doc, v).get("required", []))) for v in variantes)
    return sorted(esquema.get("required", []))


def test_mismas_rutas_y_metodos():
    assert set(C) == set(G), "solo en contrato: %s / solo en api: %s" % (sorted(set(C) - set(G)), sorted(set(G) - set(C)))


def test_mismos_codigos_de_exito():
    for clave in C:
        exito_c = sorted(c for c in C[clave]["responses"] if c.startswith("2"))
        exito_g = sorted(c for c in G[clave]["responses"] if c.startswith("2"))
        assert exito_c == exito_g, clave


def test_mismos_campos_requeridos_en_cuerpos():
    for clave in C:
        assert requeridos(CONTRATO, C[clave]) == requeridos(GENERADO, G[clave]), clave


def test_mismos_parametros_de_consulta():
    for clave in C:
        q_c = sorted(resolver(CONTRATO, p)["name"] for p in C[clave].get("parameters", []) if resolver(CONTRATO, p)["in"] == "query")
        q_g = sorted(p["name"] for p in G[clave].get("parameters", []) if p["in"] == "query")
        assert q_c == q_g, clave
