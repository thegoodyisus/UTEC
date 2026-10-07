#decision 59: conteo de peticiones por api en /salud y nombres funcionales en el panel de resiliencia
import os
import re
import uuid
from pathlib import Path

import yaml

from .conftest import quien

CLOUD = Path(__file__).resolve().parents[2]
#la web desplegada es web/ en la raiz (v05, decision 62); en docker se monta en SITIO_WEB
SITIO = Path(os.environ.get("SITIO_WEB") or CLOUD.parent / "web")
PANEL = (SITIO / "demo" / "resiliencia.html").read_text(encoding="utf-8")
CONTRATO = yaml.safe_load((CLOUD / "api" / "openapi.yaml").read_text(encoding="utf-8"))


def trafico(cliente):
    return cliente.get("/api/v1/salud").json()["trafico"]["peticiones"]


def test_cuenta_por_ruta_del_contrato_sin_valores(entorno):
    from app import trafico as t
    t.reiniciar()
    cid = str(uuid.uuid4())
    entorno.cliente.get("/api/v1/campanas/" + cid, headers=quien("agri-9", "agricultor"))
    entorno.cliente.get("/api/v1/campanas/" + cid, headers=quien("agri-9", "agricultor"))
    entorno.cliente.post("/api/v1/campanas", json={}, headers=quien("agri-9", "agricultor"))
    entorno.cliente.get("/api/v1/perfil")
    entorno.cliente.get("/api/v1/no-existe")
    p = trafico(entorno.cliente)
    assert p["GET /campanas/{campaniaId}"] == 2
    assert p["POST /campanas"] == 1
    #un 401 tambien cuenta: interesa a que api se llamo
    assert p["GET /perfil"] == 1
    assert p["otras"] == 1
    assert not any(cid in k or "agri-9" in k for k in p)


def test_salud_se_cuenta_aparte_y_acumula(entorno):
    from app import trafico as t
    t.reiniciar()
    trafico(entorno.cliente)
    r = entorno.cliente.get("/api/v1/salud").json()
    assert r["trafico"]["peticiones"]["GET /salud"] == 1 and r["trafico"]["desde"].endswith("Z")


def test_panel_nombra_todas_las_apis_del_contrato():
    #GET /salud no se lista: el panel lo ignora (ya se ve en las tarjetas de contenedores)
    claves = {m.upper() + " " + ruta for ruta, ops in CONTRATO["paths"].items() for m in ops if m in ("get", "post", "put", "patch", "delete")}
    en_panel = set(re.findall(r'clave: "([A-Z]+ /[^"]*)"', PANEL))
    assert claves - {"GET /salud"} <= en_panel, "faltan en el panel: %s" % sorted(claves - {"GET /salud"} - en_panel)
    assert "GET /salud" not in en_panel and '"GET /salud": true' in PANEL
