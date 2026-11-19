"""Corre una coleccion Postman de Bart en orden, sin Postman ni newman (solo libreria estandar).

Uso: python3 scripts/correr_coleccion.py <coleccion.postman_collection.json> [--salida reporte.txt]
Reproduce lo que hacen los scripts de las colecciones generadas por generar_postman.py:
- sustituye {{variables}}; guarda variables con collectionVariables.set(...);
- espera y repite la peticion mientras el estado o paso sea EN_PROCESO (como setNextRequest);
- verifica el status esperado (have.status) y cada pm.expect(...).to.eql(...).
No ejecuta el JavaScript de los tests: lo interpreta con expresiones regulares. La sintaxis JS se revisa aparte con node.
Es una verificacion previa; la evidencia del curso es correr la coleccion en Postman.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

ruta = sys.argv[1]
salida = sys.argv[sys.argv.index("--salida") + 1] if "--salida" in sys.argv else None
col = json.load(open(ruta, encoding="utf-8"))
var = {v["key"]: v["value"] for v in col.get("variable", [])}
lineas, total, fallas = [], 0, 0


def sustituir(texto):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(var.get(m.group(1), "")), texto)


def obtener(obj, camino):
    for parte in camino.split("."):
        if parte == "length" and isinstance(obj, list):
            return len(obj)
        obj = obj.get(parte) if isinstance(obj, dict) else None
    return obj


def ejecutar(item):
    r = item["request"]
    datos = sustituir(r["body"]["raw"]).encode() if r.get("body") else None
    req = urllib.request.Request(sustituir(r["url"]), data=datos, method=r["method"],
                                 headers={h["key"]: h["value"] for h in r.get("header", [])})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            st, cuerpo = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        st, cuerpo = e.code, e.read()
    try:
        j = json.loads(cuerpo or b"{}")
    except ValueError:
        j = {}
    return st, j, int((time.time() - t0) * 1000)


def anotar(texto, ok):
    global total, fallas
    total += 1
    fallas += 0 if ok else 1
    lineas.append("    %s %s" % ("OK   " if ok else "FALLA", texto))


for item in col["item"]:
    tests = "\n".join(e["script"]["exec"][i] for e in item.get("event", []) if e["listen"] == "test" for i in range(len(e["script"]["exec"])))
    previo = "\n".join(l for e in item.get("event", []) if e["listen"] == "prerequest" for l in e["script"]["exec"])
    espera = int(m.group(1)) / 1000 if (m := re.search(r"setTimeout\(function \(\) \{\}, (\d+)\)", previo)) else 0
    intentos = 0
    while True:
        time.sleep(espera)
        st, j, ms = ejecutar(item)
        en_proceso = j.get("estado") == "EN_PROCESO" or j.get("paso") == "EN_PROCESO"
        if "setNextRequest" in tests and en_proceso and intentos < 10:
            intentos += 1
            continue
        break
    lineas.append("%s -> HTTP %s (%d ms%s)" % (item["name"], st, ms, ", %d reintentos" % intentos if intentos else ""))
    for esperado in re.findall(r"have\.status\((\d+)\)", tests):
        anotar("HTTP %s" % esperado, st == int(esperado))
    for camino, valor in re.findall(r"pm\.expect\(pm\.response\.json\(\)\.([\w.]+)\)\.to\.eql\((.+?)\)\);", tests):
        anotar("%s = %s" % (camino, valor), obtener(j, camino) == json.loads(valor))
    for nombre, camino in re.findall(r"collectionVariables\.set\('(\w+)', (?:pm\.response\.json\(\)|j)\.([\w.]+)\)", tests):
        if st < 300 and obtener(j, camino) is not None:
            var[nombre] = obtener(j, camino)
    if "to.include(pm.collectionVariables.get('sol_pre'))" in tests:
        anotar("bandeja incluye sol_pre", var.get("sol_pre") in [i["solicitud_id"] for i in j.get("items", [])])
    if "ofertas.length).to.eql(5)" in tests:
        anotar("5 ofertas", len(j.get("ofertas", [])) == 5)

resumen = "%s: %d peticiones, %d verificaciones, %d fallas" % (col["info"]["name"], len(col["item"]), total, fallas)
texto = "\n".join(lineas + ["", resumen])
print(texto)
if salida:
    open(salida, "w", encoding="utf-8").write(texto + "\n")
sys.exit(1 if fallas else 0)
