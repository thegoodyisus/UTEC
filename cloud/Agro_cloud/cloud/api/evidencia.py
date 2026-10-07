#corre la coleccion de bruno contra el despliegue y escribe docs/api/evidencia-apis.md con las respuestas reales
#uso (desde cloud/api/, con node y docs/api/bruno/.env completo):
#  python evidencia.py            corre la coleccion (npx @usebruno/cli) y genera el md
#  python evidencia.py --solo-md  genera el md desde el ultimo reporte
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import coleccion as C

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BRUNO = os.path.join(RAIZ, "docs", "api", "bruno")
REPORTE = os.path.join(BRUNO, ".reportes", "ultimo.json")
SALIDA = os.path.join(RAIZ, "docs", "api", "evidencia-apis.md")
CLI = "@usebruno/cli@4.2.1"


def correr():
    if not os.path.exists(os.path.join(BRUNO, ".env")):
        sys.exit("falta docs/api/bruno/.env: copia .env.ejemplo y completa BASE_URL y los tokens")
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        sys.exit("falta node (npx) en el PATH")
    os.makedirs(os.path.dirname(REPORTE), exist_ok=True)
    #delay: las escrituras van por cola y el worker tarda 1 a 2 s en escribir
    cmd = [npx, "-y", CLI, "run", "--env", "agrocredit", "--delay", "2500", "--reporter-json", REPORTE]
    print("corriendo: " + " ".join(cmd[1:]))
    subprocess.run(cmd, cwd=BRUNO)


ocultar = C.ocultar
json_bonito = C.json_bonito


def generar_md():
    with open(REPORTE, encoding="utf-8") as f:
        corrida = json.load(f)[0]
    lima = datetime.fromtimestamp(os.path.getmtime(REPORTE), timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")
    s = corrida.get("summary", {})
    indice, detalle = [], []
    for r in corrida["results"]:
        #se busca por nombre: la numeracion cambia si se agregan peticiones
        num = int(r["name"][:2])
        paso = next(p for p in C.PASOS if p[1] == r["name"][3:])
        dom, tipo, destino, operacion = C.DESTINOS[paso[2]]
        metodo, ruta = paso[2].split(" ", 1)
        q = "&".join(k + "=" + v for k, v in (paso[5] or {}).items())
        ruta_q = "/api/v1" + ruta + ("?" + q if q else "")
        obtenido = r.get("response", {}).get("status")
        #ok solo si el codigo es el esperado y pasaron todas las pruebas del request
        ok = str(obtenido) in {str(c) for c in C.aceptados(paso)} and all(t.get("status") == "pass" for t in r.get("testResults", []))
        r["_ok"] = ok
        ms = r.get("response", {}).get("responseTime", "")
        indice.append("| %02d | %s | `%s %s` | %s | %s | %s | %s | %s |" % (
            num, paso[1], metodo, ruta, " o ".join(map(str, C.aceptados(paso))), obtenido, "OK" if ok else "FALLA", ms, C.celda_md(destino)))
        bloque = ["### %02d %s" % (num, paso[1]), "",
                  "- **Peticion**: `%s %s`" % (metodo, ruta_q),
                  "- **Token**: %s" % ({"tokenAgricultor": "agricultor", "tokenComprador": "comprador"}.get(paso[3], "sin token")),
                  "- **Microservicio**: %s · **Tipo**: %s" % (dom, tipo),
                  "- **Tabla o servicio**: %s" % C.celda_md(destino),
                  "- **Operacion**: %s" % C.celda_md(operacion),
                  "- **Resultado**: esperado %s, obtenido **%s** (%s, %s ms)" % (" o ".join(map(str, C.aceptados(paso))), obtenido, "OK" if ok else "FALLA", ms), ""]
        enviado = r.get("request", {}).get("data")
        if enviado:
            bloque += ["Cuerpo enviado:", "", "```json", json_bonito(enviado), "```", ""]
        datos = r.get("response", {}).get("data")
        bloque += ["Respuesta:", "", "```json", json_bonito(datos) if datos not in (None, "") else "(sin cuerpo)", "```", ""]
        if r.get("error"):
            bloque += ["Error: `" + str(r["error"]) + "`", ""]
        detalle += bloque
    total = len(corrida["results"])
    pasaron = sum(1 for r in corrida["results"] if r["_ok"])
    md = ["# Evidencia de las APIs de AgroCredit en AWS", "",
          "Corrida real con Bruno CLI (`" + CLI + "`) contra el despliegue en AWS (us-east-1), " + lima + " hora de Lima. "
          "Coleccion: `docs/api/bruno/` (generada desde `cloud/api/openapi.yaml`). Generado por `cloud/api/evidencia.py`; no editar a mano.", "",
          "**Resultado: %d de %d peticiones con el codigo esperado.** Tokens, firmas y credenciales temporales de S3 se ocultan; "
          "el host del balanceador sale como `/api/v1`. Datos de personas y empresas ficticios (Ley 29733)." % (pasaron, total), "",
          "Las escrituras 202 (campana, oferta) van por SQS y la Lambda `agro-worker` escribe en `agro-datos`; la coleccion espera 2.5 s entre peticiones. "
          "Para verlas en la base: `docs/base-datos/agrocredit-base-datos.md` (seccion 1 y 6).", "",
          "## Resumen", "",
          "| # | Peticion | API | Esperado | Obtenido | Estado | ms | Tabla o servicio |", "|---|---|---|---|---|---|---|---|",
          *indice, "", "## Detalle por servicio", "", *detalle]
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(md))
    print("evidencia: %s (%d/%d OK)" % (SALIDA, pasaron, total))


if __name__ == "__main__":
    if "--solo-md" not in sys.argv:
        correr()
    generar_md()
    #la coleccion de bruno lleva la respuesta real en la pestana docs de cada peticion
    C.escribir()
    print("coleccion de bruno actualizada con las respuestas reales: docs/api/bruno/")
