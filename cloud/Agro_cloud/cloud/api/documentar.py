#genera docs/api/agrocredit-api.html desde openapi.yaml (html autocontenido, sin internet)
#uso: python documentar.py   (o python tareas.py documentar)
#omite lo del panel de resiliencia: POST /demo/caer y el campo trafico de /salud (decision 60)
import html
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
CONTRATO = os.path.join(AQUI, "openapi.yaml")
SALIDA = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "docs", "api", "agrocredit-api.html")
METODOS = ("get", "post", "put", "patch", "delete")
OMITIR_OPERACIONES = {"POST /demo/caer"}
OMITIR_CAMPOS = {"Salud": {"trafico"}}
#descripciones propias donde el contrato habla del panel de resiliencia
DESCRIPCIONES = {
    "GET /salud": "Sin autenticación. Devuelve el id de la tarea (contenedor) y su zona. El balanceador lo consulta cada 5 s: "
                  "si un contenedor no responde 2 veces seguidas, deja de enviarle tráfico.",
}

#grupos funcionales y nombre de cada api (mismo criterio que el panel, sin monitoreo)
GRUPOS = [
    ("plataforma", "Plataforma", "Lo usa el balanceador de carga para saber si un contenedor puede recibir tráfico.", [
        ("GET /salud", "Chequeo de salud")]),
    ("identidad", "Identidad y perfil", "Inicio de sesión con Amazon Cognito y perfil de negocio del usuario.", [
        ("GET /config", "Configuración de inicio de sesión"),
        ("GET /perfil", "Consultar mi perfil"),
        ("POST /perfil", "Crear mi perfil")]),
    ("campanas", "Campañas y fotos", "El agricultor registra campañas con fotos; el comprador las busca.", [
        ("GET /campanas", "Mis campañas"),
        ("POST /campanas", "Registrar campaña"),
        ("GET /campanas/publicadas", "Buscar campañas publicadas"),
        ("GET /campanas/{campaniaId}", "Ver campaña"),
        ("PATCH /campanas/{campaniaId}", "Actualizar campaña"),
        ("POST /campanas/{campaniaId}/fotos/url", "Subir foto (URL prefirmada)"),
        ("GET /campanas/{campaniaId}/fotos", "Ver fotos")]),
    ("ofertas", "Ofertas", "El comprador ofrece sobre campañas publicadas; el agricultor ve las que recibe.", [
        ("POST /campanas/{campaniaId}/ofertas", "Enviar oferta"),
        ("GET /campanas/{campaniaId}/ofertas", "Ofertas de una campaña"),
        ("GET /ofertas", "Mis ofertas")]),
    ("padron", "Padrón y catálogos", "Datos de referencia ficticios para completar formularios.", [
        ("POST /padron/consulta", "Consultar padrón"),
        ("GET /catalogo/cultivos", "Catálogo de cultivos"),
        ("GET /cuentas-demo", "Cuentas de prueba")]),
]

ESTADOS = {
    "200": "OK", "201": "Creado", "202": "Aceptado (se procesa por cola)", "401": "No autenticado", "403": "Sin permiso",
    "404": "No encontrado", "409": "Conflicto", "422": "Datos inválidos", "503": "No disponible",
}


def cargar():
    try:
        import yaml
    except ModuleNotFoundError:
        sys.exit("falta pyyaml: ejecuta con el python de Conexion/.venv (python tareas.py documentar)")
    with open(CONTRATO, encoding="utf-8") as f:
        return yaml.safe_load(f)


def operaciones(doc):
    salida = {}
    for ruta, ops in doc["paths"].items():
        for metodo, op in ops.items():
            if metodo in METODOS:
                salida[metodo.upper() + " " + ruta] = op
    return salida


def resolver(doc, nodo):
    #sigue $ref y combina las claves hermanas (openapi 3.1 permite description junto a $ref)
    while isinstance(nodo, dict) and "$ref" in nodo:
        destino = doc
        for parte in nodo["$ref"].lstrip("#/").split("/"):
            destino = destino[parte]
        nodo = dict(destino, **{k: v for k, v in nodo.items() if k != "$ref"})
    if isinstance(nodo, dict) and "allOf" in nodo:
        #allOf (ej. PerfilAgricultor = PerfilAgricultorCrear + sub y creadoEn): se unen campos y obligatorios
        unido = {k: v for k, v in nodo.items() if k != "allOf"}
        unido.setdefault("type", "object")
        props, req = {}, []
        for parte in nodo["allOf"]:
            r = resolver(doc, parte)
            props.update(r.get("properties", {}))
            req += [x for x in r.get("required", []) if x not in req]
            if "description" in r and "description" not in unido:
                unido["description"] = r["description"]
        unido["properties"] = dict(props, **unido.get("properties", {}))
        unido["required"] = req + [x for x in unido.get("required", []) if x not in req]
        nodo = unido
    return nodo


def nombre_ref(nodo):
    return nodo["$ref"].rsplit("/", 1)[-1] if isinstance(nodo, dict) and "$ref" in nodo else None


def e(texto):
    return html.escape(str(texto), quote=True)


def md(texto):
    #markdown minimo del contrato: parrafos, listas con "- ", **negrita** y `codigo`
    if not texto:
        return ""

    def linea(t):
        t = e(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        return re.sub(r"`(.+?)`", r"<code>\1</code>", t)

    bloques, parrafo, lista = [], [], []

    def cerrar():
        if parrafo:
            bloques.append("<p>" + " ".join(linea(p) for p in parrafo) + "</p>")
            parrafo.clear()
        if lista:
            bloques.append("<ul>" + "".join("<li>" + linea(i) + "</li>" for i in lista) + "</ul>")
            lista.clear()

    for fila in texto.strip().splitlines():
        fila = fila.strip()
        if not fila:
            cerrar()
        elif fila.startswith("- "):
            if parrafo:
                cerrar()
            lista.append(fila[2:])
        else:
            if lista:
                cerrar()
            parrafo.append(fila)
    cerrar()
    return "".join(bloques)


def tipo(doc, esquema):
    s = resolver(doc, esquema)
    if "oneOf" in s:
        return " o ".join(nombre_ref(v) or tipo(doc, v) for v in s["oneOf"])
    t = s.get("type", "objeto")
    if isinstance(t, list):
        #openapi 3.1: ["string", "null"] = texto que puede venir vacio
        reales = [x for x in t if x != "null"]
        return tipo(doc, dict(s, type=reales[0] if len(reales) == 1 else "objeto")) + (" o null" if "null" in t else "")
    if t == "array":
        interno = s.get("items", {})
        return "lista de " + (nombre_ref(interno) or tipo(doc, interno))
    nombres = {"string": "texto", "integer": "entero", "number": "número", "boolean": "booleano", "object": "objeto"}
    base = nombres.get(t, t)
    if s.get("format"):
        base += " (" + s["format"] + ")"
    return base


def reglas(doc, esquema):
    s = resolver(doc, esquema)
    r = []
    if "enum" in s:
        r.append("valores: " + ", ".join("<code>" + e(v) + "</code>" for v in s["enum"]))
    if "pattern" in s:
        r.append("patrón <code>" + e(s["pattern"]) + "</code>")
    for clave, texto in (("minimum", "mín."), ("maximum", "máx."), ("minLength", "largo mín."), ("maxLength", "largo máx."),
                         ("minItems", "mín. elementos"), ("maxItems", "máx. elementos"), ("default", "por defecto")):
        if clave in s:
            r.append(texto + " " + e(s[clave]))
    return "; ".join(r)


#valores ficticios por nombre de campo, para que los ejemplos se lean como un caso real
POR_CAMPO = {
    "nombres": "Rosa", "apellidos": "Quispe Mamani", "productorNombre": "Rosa Quispe Mamani",
    "razonSocial": "Agroindustrias Sierra Verde SAC", "compradorNombre": "Agroindustrias Sierra Verde SAC",
    "contactoNombre": "Marisol Quispe Huamán", "contactoCargo": "Jefa de compras", "contactoCorreo": "compras@correo.example",
    "direccionFiscal": "Av. Los Incas 845, Wanchaq, Cusco", "actividad": "Procesamiento de papa",
    "capital": "5000.00", "total": "2160.00", "tamanoBytes": 245760, "siguienteCursor": None,
    "tareaId": "3f2a9c1d8b7e4a6f9d0c1b2a3e4f5a6b", "zona": "us-east-1a", "version": "c8f329de711b",
    "titulo": "Cta. Cte. Soles ***-8830", "descripcion": "Cuenta ficticia de prueba", "cuentaCargoId": "cc-8830",
    "label": "papa", "labelConfianza": 99, "region": "us-east-1", "userPoolId": "us-east-1_AbCdEfGhI",
    "clientId": "1example23456789abcdefghij", "consultar": "/api/v1/campanas/6f1c2a0e-1b7d-4a53-9c1e-2f0d3a7b9e11",
    "campos": {"key": "entrada/<sub>/<campaniaId>/<fotoId>.jpg", "Content-Type": "image/jpeg", "policy": "<firmado por AWS>",
               "x-amz-algorithm": "AWS4-HMAC-SHA256", "x-amz-credential": "<credencial temporal>", "x-amz-date": "20261005T210000Z",
               "x-amz-signature": "<firma>"},
    "url": "https://agro-fotos-<cuenta>.s3.amazonaws.com/",
    "Foto.estado": "ETIQUETADA",
    "Foto.url": "https://agro-fotos-<cuenta>.s3.amazonaws.com/<sub>/papa_20261005_160000.jpg?X-Amz-Signature=<firma>&X-Amz-Expires=300",
}


def ejemplo(doc, esquema, nombre="", profundidad=0, padre=None):
    s = resolver(doc, esquema)
    if profundidad > 6:
        return None
    if padre and padre + "." + nombre in POR_CAMPO:
        return POR_CAMPO[padre + "." + nombre]
    if nombre in POR_CAMPO:
        return POR_CAMPO[nombre]
    if "oneOf" in s:
        return ejemplo(doc, s["oneOf"][0], nombre, profundidad + 1)
    if s.get("examples"):
        return s["examples"][0]
    if "example" in s:
        return s["example"]
    if "enum" in s:
        return s["enum"][0]
    t = s.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), None)
    if t == "object" or "properties" in s:
        props = s.get("properties", {})
        nombre_esquema = nombre_ref(esquema)
        return {k: ejemplo(doc, v, k, profundidad + 1, nombre_esquema) for k, v in props.items()
                if k not in OMITIR_CAMPOS.get(nombre_esquema or "", set())}
    if t == "array":
        return [ejemplo(doc, s.get("items", {}), nombre, profundidad + 1)]
    if t == "integer":
        return s.get("default", s.get("minimum", 1))
    if t == "number":
        return 1.5
    if t == "boolean":
        return True
    fmt = s.get("format")
    fijos = {"uuid": "6f1c2a0e-1b7d-4a53-9c1e-2f0d3a7b9e11", "date": "2027-06-15", "date-time": "2026-10-05T21:00:00Z",
             "email": "nombre@correo.example", "uri": "https://ejemplo.example/"}
    if fmt in fijos:
        return fijos[fmt]
    patron = s.get("pattern", "")
    if "{11}" in patron:
        return "20123456789"
    if "{8}" in patron:
        return "12345678"
    if "{9}" in patron:
        return "987654321"
    return {"departamento": "Cusco", "provincia": "Cusco", "distrito": "Wanchaq"}.get(nombre, "texto")


def filas_campos(doc, esquema, prefijo="", profundidad=0, nombre_esquema=None):
    s = resolver(doc, esquema)
    nombre_esquema = nombre_esquema or nombre_ref(esquema)
    if s.get("type") == "array":
        interno = s.get("items", {})
        return filas_campos(doc, interno, prefijo + "[]." if prefijo else "[].", profundidad, nombre_ref(interno))
    filas = []
    requeridos = set(s.get("required", []))
    omitir = OMITIR_CAMPOS.get(nombre_esquema or "", set())
    for campo, sub in s.get("properties", {}).items():
        if campo in omitir:
            continue
        rs = resolver(doc, sub)
        filas.append("<tr><td><code>" + e(prefijo + campo) + "</code>" + (' <span class="req">obligatorio</span>' if campo in requeridos else "") +
                     "</td><td>" + e(tipo(doc, sub)) + "</td><td>" + md(rs.get("description", "")) +
                     ('<div class="reglas">' + reglas(doc, sub) + "</div>" if reglas(doc, sub) else "") + "</td></tr>")
        hijo = rs.get("items", {}) if rs.get("type") == "array" else sub
        hijo_r = resolver(doc, hijo)
        if profundidad < 2 and ("properties" in hijo_r):
            marca = "[]." if rs.get("type") == "array" else "."
            filas += filas_campos(doc, hijo, prefijo + campo + marca, profundidad + 1, nombre_ref(hijo))
    return filas


def tabla_esquema(doc, esquema, titulo):
    s = resolver(doc, esquema)
    variantes = s.get("oneOf")
    if variantes:
        partes = []
        for i, v in enumerate(variantes, 1):
            vr = resolver(doc, v)
            partes.append('<h5>' + e(titulo) + " · variante " + str(i) + ": <code>" + e(nombre_ref(v) or "") + "</code></h5>" +
                          md(vr.get("description", "")) + tabla_esquema(doc, v, titulo))
        return "".join(partes)
    filas = filas_campos(doc, esquema)
    if not filas:
        return '<p class="tenue">' + e(tipo(doc, esquema)) + "</p>"
    return ('<div class="tabla"><table><thead><tr><th>Campo</th><th>Tipo</th><th>Descripción</th></tr></thead><tbody>' +
            "".join(filas) + "</tbody></table></div>")


def bloque_json(valor):
    return "<pre><code>" + e(json.dumps(valor, ensure_ascii=False, indent=2)) + "</code></pre>"


def curl(clave, op, doc, cuerpo):
    metodo, ruta = clave.split(" ", 1)
    ruta = ruta.replace("{campaniaId}", "6f1c2a0e-1b7d-4a53-9c1e-2f0d3a7b9e11")
    query = [resolver(doc, p) for p in op.get("parameters", []) if resolver(doc, p)["in"] == "query" and resolver(doc, p).get("required")]
    if query:
        ruta += "?" + "&".join(p["name"] + "=" + str(ejemplo(doc, p["schema"], p["name"])) for p in query)
    partes = ["curl -s" + (" -X " + metodo if metodo != "GET" else "") + ' "$URL/api/v1' + ruta + '"']
    if op.get("security") != []:
        partes.append('-H "Authorization: Bearer $TOKEN"')
    if cuerpo is not None:
        partes.append('-H "Content-Type: application/json"')
        partes.append("-d '" + json.dumps(cuerpo, ensure_ascii=False) + "'")
    return "<pre><code>" + e(" \\\n  ".join(partes)) + "</code></pre>"


def ancla(clave):
    return "op-" + re.sub(r"[^a-z0-9]+", "-", clave.lower()).strip("-")


def seccion_operacion(doc, clave, nombre, op):
    metodo, ruta = clave.split(" ", 1)
    publica = op.get("security") == []
    roles = op.get("x-roles", [])
    acceso = "Público (sin token)" if publica else "Token de Cognito · rol: " + " o ".join(roles)
    partes = ['<article class="op" id="' + ancla(clave) + '">',
              '<h3><span class="metodo ' + metodo.lower() + '">' + metodo + "</span> " + e(nombre) + "</h3>",
              '<p class="ruta"><code>/api/v1' + e(ruta) + "</code></p>",
              '<p class="resumen">' + e(op.get("summary", "")) + "</p>",
              '<p class="acceso ' + ("publico" if publica else "privado") + '">' + e(acceso) + "</p>"]
    descripcion = DESCRIPCIONES.get(clave, op.get("description"))
    if descripcion:
        partes.append(md(descripcion))
    parametros = [resolver(doc, p) for p in op.get("parameters", [])]
    if parametros:
        filas = "".join("<tr><td><code>" + e(p["name"]) + "</code>" + (' <span class="req">obligatorio</span>' if p.get("required") else "") +
                        "</td><td>" + {"path": "ruta", "query": "consulta", "header": "cabecera"}.get(p["in"], p["in"]) +
                        "</td><td>" + e(tipo(doc, p.get("schema", {}))) + "</td><td>" + md(p.get("description", "")) +
                        ('<div class="reglas">' + reglas(doc, p.get("schema", {})) + "</div>" if reglas(doc, p.get("schema", {})) else "") +
                        "</td></tr>" for p in parametros)
        partes.append('<h4>Parámetros</h4><div class="tabla"><table><thead><tr><th>Nombre</th><th>En</th><th>Tipo</th><th>Descripción</th></tr></thead><tbody>' + filas + "</tbody></table></div>")
    cuerpo = None
    if "requestBody" in op:
        esquema = op["requestBody"]["content"]["application/json"]["schema"]
        cuerpo = ejemplo(doc, esquema)
        partes.append("<h4>Cuerpo de la petición</h4>" + tabla_esquema(doc, esquema, "Cuerpo") +
                      '<p class="etq">Ejemplo</p>' + bloque_json(cuerpo))
    partes.append("<h4>Respuestas</h4>")
    filas = []
    exito = None
    for codigo, resp in op.get("responses", {}).items():
        r = resolver(doc, resp)
        filas.append('<tr><td><span class="codigo c' + codigo[0] + '">' + e(codigo) + "</span></td><td>" + e(ESTADOS.get(codigo, "")) +
                     "</td><td>" + md(r.get("description", "")) + "</td></tr>")
        if codigo.startswith("2") and exito is None:
            exito = (codigo, r)
    partes.append('<div class="tabla"><table><thead><tr><th>Código</th><th>Significado</th><th>Detalle</th></tr></thead><tbody>' + "".join(filas) + "</tbody></table></div>")
    if exito and exito[1].get("content"):
        esquema = list(exito[1]["content"].values())[0]["schema"]
        partes.append("<h4>Respuesta " + e(exito[0]) + "</h4>" + tabla_esquema(doc, esquema, "Respuesta") +
                      '<p class="etq">Ejemplo</p>' + bloque_json(ejemplo(doc, esquema)))
    partes.append('<h4>Probar con curl</h4>' + curl(clave, op, doc, cuerpo))
    partes.append("</article>")
    return "".join(partes)


ESTILO = """
:root{--fondo:#f5f6f7;--superficie:#fff;--texto:#1d1d1b;--tenue:#5f6368;--borde:#e2e4e7;--primario:#05be50;--primario-osc:#03873a;
--codigo:#f1f3f4;--get:#1565c0;--post:#03873a;--c2:#0a7a3a;--c4:#b26a00;--c5:#c62828;--req:#c62828}
@media (prefers-color-scheme:dark){:root{--fondo:#121417;--superficie:#1b1e22;--texto:#e8eaed;--tenue:#9aa0a6;--borde:#2d3136;
--codigo:#24282d;--get:#64b5f6;--post:#5fd38d;--c2:#5fd38d;--c4:#ffb74d;--c5:#ef9a9a;--req:#ef9a9a;--primario-osc:#5fd38d}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--fondo);color:var(--texto);line-height:1.5}
header{background:var(--primario);color:#fff;padding:24px 32px}header h1{margin:0;font-size:1.6rem}header p{margin:4px 0 0;opacity:.95}
.marco{display:grid;grid-template-columns:280px 1fr;gap:24px;max-width:1280px;margin:0 auto;padding:24px 16px}
nav{position:sticky;top:16px;align-self:start;max-height:calc(100vh - 32px);overflow:auto;background:var(--superficie);border:1px solid var(--borde);border-radius:14px;padding:14px}
nav h2{font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;color:var(--tenue);margin:14px 0 6px}nav h2:first-child{margin-top:0}
nav a{display:flex;gap:8px;align-items:baseline;color:var(--texto);text-decoration:none;font-size:.88rem;padding:3px 6px;border-radius:6px}
nav a:hover{background:var(--codigo)}nav .m{font-family:ui-monospace,Menlo,monospace;font-size:.68rem;font-weight:700;min-width:34px}
nav .m.get{color:var(--get)}nav .m.post{color:var(--post)}nav .m.patch{color:#8a5a00}
main{min-width:0}section.grupo,section.intro{background:var(--superficie);border:1px solid var(--borde);border-radius:14px;padding:20px 24px;margin-bottom:20px}
section h2{margin:0 0 4px;font-size:1.35rem}.desc-grupo{color:var(--tenue);margin:0 0 8px}
.op{border-top:1px solid var(--borde);padding-top:18px;margin-top:18px}.op h3{margin:0;font-size:1.12rem;display:flex;gap:10px;align-items:center}
.metodo{font-family:ui-monospace,Menlo,monospace;font-size:.75rem;padding:3px 8px;border-radius:6px;color:#fff}.metodo.get{background:var(--get)}.metodo.post{background:var(--post)}.metodo.patch{background:#8a5a00}
@media (prefers-color-scheme:dark){.metodo{color:#121417}}
.ruta{margin:6px 0 0}.resumen{margin:4px 0;color:var(--tenue)}
.acceso{display:inline-block;font-size:.8rem;padding:2px 10px;border-radius:999px;margin:4px 0 8px;background:var(--codigo)}
h4{margin:16px 0 6px;font-size:.95rem}h5{margin:12px 0 4px;font-size:.88rem}
.tabla{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.86rem}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--borde);vertical-align:top}th{color:var(--tenue);font-weight:500;font-size:.78rem}
td p{margin:0}td ul{margin:0;padding-left:18px}.reglas{font-size:.78rem;color:var(--tenue);margin-top:2px}
.req{font-size:.68rem;color:var(--req);font-weight:600;white-space:nowrap}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.85em;background:var(--codigo);padding:1px 5px;border-radius:5px;word-break:break-word}
pre{background:var(--codigo);border-radius:10px;padding:12px 14px;overflow-x:auto;margin:6px 0}pre code{background:none;padding:0;font-size:.8rem;word-break:normal}
.codigo{font-family:ui-monospace,Menlo,monospace;font-weight:700}.codigo.c2{color:var(--c2)}.codigo.c4{color:var(--c4)}.codigo.c5{color:var(--c5)}
.etq{font-size:.78rem;color:var(--tenue);margin:10px 0 0}.tenue{color:var(--tenue)}
.pie{color:var(--tenue);font-size:.8rem;text-align:center;padding:8px 0 24px}
@media (max-width:860px){.marco{grid-template-columns:1fr}nav{position:static;max-height:none}header{padding:20px 16px}section.grupo,section.intro{padding:16px}}
@media print{nav{display:none}.marco{display:block}header{background:none;color:#000}}
"""


def generar():
    doc = cargar()
    ops = operaciones(doc)
    nombradas = {c for _, _, _, apis in GRUPOS for c, _ in apis}
    faltan = set(ops) - nombradas - OMITIR_OPERACIONES
    if faltan:
        raise SystemExit("operaciones del contrato sin grupo en documentar.py: " + ", ".join(sorted(faltan)))
    info = doc["info"]
    menu, cuerpo = [], []
    menu.append('<h2>Guía</h2><a href="#intro">Convenciones</a><a href="#autenticacion">Autenticación</a><a href="#asincrono">Escrituras asíncronas (202)</a><a href="#errores">Errores</a>')
    for gid, titulo, descripcion, apis in GRUPOS:
        menu.append("<h2>" + e(titulo) + "</h2>")
        partes = ['<section class="grupo" id="' + gid + '"><h2>' + e(titulo) + '</h2><p class="desc-grupo">' + e(descripcion) + "</p>"]
        for clave, nombre in apis:
            metodo = clave.split(" ", 1)[0]
            menu.append('<a href="#' + ancla(clave) + '"><span class="m ' + metodo.lower() + '">' + metodo + "</span>" + e(nombre) + "</a>")
            partes.append(seccion_operacion(doc, clave, nombre, ops[clave]))
        partes.append("</section>")
        cuerpo.append("".join(partes))
    intro = (
        '<section class="intro" id="intro"><h2>Convenciones</h2>' + md(info.get("description", "")) +
        "<p>Base de todas las rutas: <code>http://&lt;dns del balanceador&gt;/api/v1</code> (la imprime <code>python tareas.py desplegar</code>). "
        "Swagger interactivo de la API desplegada: <code>/api/docs</code>.</p></section>"
        '<section class="intro" id="autenticacion"><h2>Autenticación</h2>'
        "<p>El navegador inicia sesión contra Amazon Cognito con el protocolo SRP (usuario = DNI o RUC, clave = PIN de 6 dígitos) usando "
        "<code>GET /config</code> para saber a qué pool conectarse. Cognito entrega un <strong>ID token</strong> (JWT, 60 min) que va en "
        "<code>Authorization: Bearer &lt;token&gt;</code>. La API valida firma (JWKS), emisor, audiencia, vencimiento y que "
        "<code>token_use</code> sea <code>id</code>; el rol sale del claim <code>custom:rol</code> (<code>agricultor</code> o "
        "<code>comprador</code>), fijado al crear la cuenta e inmutable.</p></section>"
        '<section class="intro" id="asincrono"><h2>Escrituras asíncronas (202)</h2>'
        "<p><code>POST /campanas</code> y <code>POST /campanas/{campaniaId}/ofertas</code> validan, encolan el registro en Amazon SQS y responden "
        "<code>202</code> con <code>recursoId</code> y la ruta a <code>consultar</code>. Una Lambda lo escribe en DynamoDB con escritura condicional: "
        "reenviar el mismo id no duplica (idempotencia). El cliente consulta la ruta hasta que deja de responder <code>404</code>, "
        "normalmente en 1 a 2 segundos.</p></section>"
        '<section class="intro" id="errores"><h2>Errores</h2>'
        "<p>Todos los errores usan <code>application/problem+json</code>:</p>" +
        bloque_json({"type": "about:blank", "title": "Unprocessable Entity", "status": 422, "detail": "la cosecha debe ser una fecha futura",
                     "requestId": "3c9d0e6a-6f2b-4d0f-9a43-1f1f7c2b8e55"}) +
        '<p>El <code>requestId</code> también llega en la cabecera <code>X-Request-Id</code> y sirve para buscar la petición en CloudWatch Logs.</p></section>'
    )
    return (
        '<!DOCTYPE html>\n<html lang="es">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>AgroCredit API v" + e(info["version"]) + "</title>\n<style>" + ESTILO + "</style>\n</head>\n<body>\n"
        "<header><h1>AgroCredit API</h1><p>Documentación funcional del contrato v" + e(info["version"]) +
        " · corte vertical en AWS · todos los datos son ficticios</p></header>\n"
        '<div class="marco"><nav>' + "".join(menu) + "</nav><main>" + intro + "".join(cuerpo) +
        '<p class="pie">Generado desde <code>cloud/api/openapi.yaml</code> v' + e(info["version"]) +
        " con <code>python tareas.py documentar</code>. No editar a mano.</p></main></div>\n</body>\n</html>\n"
    )


def escribir():
    contenido = generar()
    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    previo = None
    if os.path.exists(SALIDA):
        with open(SALIDA, encoding="utf-8") as f:
            previo = f.read()
    if previo == contenido:
        return SALIDA, False
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenido)
    return SALIDA, True


if __name__ == "__main__":
    ruta, cambio = escribir()
    print(("documentacion actualizada: " if cambio else "documentacion sin cambios: ") + ruta)
