#semillas del padron en cloud/semillas/*.json (decision 58): formato, datos ficticios y resolucion del import
import importlib
import json
import os
import sys
from pathlib import Path

CLOUD = Path(__file__).resolve().parents[2]


def cargar_semillas():
    sys.path.insert(0, str(CLOUD))
    try:
        sys.modules.pop("semillas", None)
        return importlib.import_module("semillas")
    finally:
        sys.path.remove(str(CLOUD))


def test_import_resuelve_al_archivo_y_no_a_la_carpeta():
    s = cargar_semillas()
    assert Path(s.__file__).name == "semillas.py" and hasattr(s, "items_catalogo")


def test_padron_json_10_personas_y_10_empresas_sin_documentos():
    personas, empresas = cargar_semillas().leer_padron()
    assert [p["id"] for p in personas] == ["p%02d" % i for i in range(1, 11)]
    assert [e["id"] for e in empresas] == ["e%02d" % i for i in range(1, 11)]
    assert all(set(p) == {"id", "nombres", "apellidos", "celular", "correo"} for p in personas)
    assert all(set(e) == {"id", "razonSocial", "direccionFiscal", "actividad", "estado"} for e in empresas)
    texto = json.dumps(personas + empresas, ensure_ascii=False).lower()
    assert "dni" not in texto and "ruc" not in texto


def test_json_en_utf8_con_tildes():
    with open(os.path.join(CLOUD, "semillas", "padron-personas.json"), encoding="utf-8") as f:
        assert "Huamán" in f.read()


def test_items_padron_con_clave_simple():
    personas, empresas = cargar_semillas().items_padron()
    assert all("PK" not in i and i["entidad"] == "PADRON_PERSONA" for i in personas)
    assert all("PK" not in i and i["entidad"] == "PADRON_EMPRESA" for i in empresas)
