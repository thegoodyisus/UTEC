#genera la coleccion de pruebas de la api (thunder client y postman) desde openapi.yaml
#incluye cuerpos por servicio y que tabla o servicio aws toca cada api
#uso: python coleccion.py   (con el python de Conexion/.venv, necesita pyyaml)
import json
import os
import uuid

import documentar as D

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "docs", "api", "thunder")
FECHA = "2026-10-06T00:00:00.000Z"
BASE = uuid.UUID("5b0e7c1a-3d2f-4a6b-9c8d-1e2f3a4b5c6d")

ENTORNO = [
    ("baseUrl", "http://<dns-del-alb>/api/v1", "copiar la linea web: de python tareas.py probar y dejar solo http://<dns>/api/v1"),
    ("tokenAgricultor", "", "ID token de una sesion de agricultor (ver LEEME)"),
    ("tokenComprador", "", "ID token de una sesion de comprador (ver LEEME)"),
    ("dniAgricultor", "12345678", "DNI con que se creo la cuenta del agricultor (ficticio)"),
    ("rucComprador", "20123456789", "RUC con que se creo la cuenta del comprador (ficticio)"),
    ("dniRepresentante", "87654321", "DNI ficticio del representante del comprador"),
    ("campaniaId", "", "lo llena la prueba de Registrar campana"),
    ("ofertaId", "", "lo llena la prueba de Enviar oferta"),
    ("fotoId", "", "lo llena la prueba de Pedir URL de foto"),
]

#que toca cada api: microservicio (dominio), escritura (directa o por cola) y tablas o servicios aws
DESTINOS = {
    "GET /salud": ("Plataforma", "lectura", "memoria de la tarea ECS (sin tabla)", "-"),
    "GET /config": ("Identidad y perfil", "lectura", "variables de entorno de la tarea: ids de Cognito (sin tabla)", "-"),
    "POST /perfil": ("Identidad y perfil", "escritura directa", "agro-datos", "PutItem USER#<sub> / PROFILE (condicion attribute_not_exists); lee CATALOGO o CUENTA_DEMO para validar"),
    "GET /perfil": ("Identidad y perfil", "lectura", "agro-datos", "GetItem USER#<sub> / PROFILE"),
    "GET /catalogo/cultivos": ("Padron y catalogos", "lectura", "agro-datos", "Query PK=CATALOGO, SK empieza con CULTIVO#"),
    "POST /padron/consulta": ("Padron y catalogos", "escritura directa (transaccion)", "agro-padron-empresas o agro-padron-personas + agro-datos",
                              "Scan consistente + TransactWriteItems: Delete del registro del padron + Put USER#<sub> / PADRON#<uso>#<tipoDoc>"),
    "GET /cuentas-demo": ("Padron y catalogos", "lectura", "agro-datos", "Query PK=CUENTA_DEMO"),
    "POST /campanas": ("Campanas y fotos", "escritura asincrona", "SQS agro-insercion -> Lambda agro-worker -> agro-datos",
                       "la api lee CATALOGO y PROFILE y encola; el worker hace PutItem CAMP#<id> / META con indices por-usuario y publicadas-por-cultivo"),
    "GET /campanas/{campaniaId}": ("Campanas y fotos", "lectura", "agro-datos", "GetItem CAMP#<id> / META"),
    "PATCH /campanas/{campaniaId}": ("Campanas y fotos", "actualizacion directa", "agro-datos",
                                     "UpdateItem CAMP#<id> / META con condicion attribute_exists(PK) AND propietarioSub = <sub> AND numeroOfertas = 0"),
    "GET /campanas": ("Campanas y fotos", "lectura", "agro-datos (indice por-usuario)", "Query usuarioClave=USER#<sub>, usuarioOrden empieza con CAMP#"),
    "POST /campanas/{campaniaId}/fotos/url": ("Campanas y fotos", "escritura asincrona", "S3 agro-fotos -> SQS agro-fotos -> Lambda agro-etiquetar -> Rekognition -> agro-datos",
                                              "la api firma un POST a entrada/<sub>/<campana>/<foto>; la lambda registra CAMP#<id> / FOTO#<fotoId>"),
    "GET /campanas/{campaniaId}/fotos": ("Campanas y fotos", "lectura", "agro-datos + S3 agro-fotos", "Query PK=CAMP#<id>, SK empieza con FOTO#; URL de lectura temporal"),
    "GET /campanas/publicadas": ("Campanas y fotos", "lectura", "agro-datos (indice publicadas-por-cultivo)", "Query publicadaClave=PUB#<cultivo>#<departamento>"),
    "POST /campanas/{campaniaId}/ofertas": ("Ofertas", "escritura asincrona", "SQS agro-insercion -> Lambda agro-worker -> agro-datos",
                                            "la api lee META y PROFILE y encola; el worker hace TransactWriteItems: Put CAMP#<id> / OFFER#<id> + Update META numeroOfertas"),
    "GET /ofertas": ("Ofertas", "lectura", "agro-datos (indice por-usuario)", "Query usuarioClave=USER#<sub>, usuarioOrden empieza con OFFER#"),
    "GET /campanas/{campaniaId}/ofertas": ("Ofertas", "lectura", "agro-datos", "Query PK=CAMP#<id>, SK empieza con OFFER#"),
}

#orden de la demo: (carpeta, nombre, operacion, token, cuerpo a usar, query, codigo esperado, variable que se guarda)
PASOS = [
    ("0 Plataforma (publico)", "Chequeo de salud", "GET /salud", None, None, None, 200, None),
    ("0 Plataforma (publico)", "Configuracion de inicio de sesion", "GET /config", None, None, None, 200, None),
    ("1 Agricultor", "Crear mi perfil (agricultor)", "POST /perfil", "tokenAgricultor", "perfil_agricultor", None, 201, None),
    ("1 Agricultor", "Consultar mi perfil", "GET /perfil", "tokenAgricultor", None, None, 200, None),
    ("1 Agricultor", "Catalogo de cultivos", "GET /catalogo/cultivos", "tokenAgricultor", None, None, 200, None),
    ("1 Agricultor", "Registrar campana (insert por cola)", "POST /campanas", "tokenAgricultor", "campana", None, 202, ("campaniaId", "recursoId")),
    ("1 Agricultor", "Ver campana (repetir hasta 200)", "GET /campanas/{campaniaId}", "tokenAgricultor", None, None, 200, None),
    ("1 Agricultor", "Mis campanas", "GET /campanas", "tokenAgricultor", None, None, 200, None),
    ("1 Agricultor", "Actualizar campana (update directo, sin ofertas)", "PATCH /campanas/{campaniaId}", "tokenAgricultor", "campana_actualizar", None, 200, None),
    ("1 Agricultor", "Pedir URL para subir foto", "POST /campanas/{campaniaId}/fotos/url", "tokenAgricultor", "foto", None, 200, ("fotoId", "fotoId")),
    ("1 Agricultor", "Ver fotos de la campana", "GET /campanas/{campaniaId}/fotos", "tokenAgricultor", None, None, 200, None),
    ("2 Comprador", "Consultar padron (empresa por RUC)", "POST /padron/consulta", "tokenComprador", "padron_empresa", None, 200, None),
    ("2 Comprador", "Consultar padron (representante por DNI)", "POST /padron/consulta", "tokenComprador", "padron_representante", None, 200, None),
    ("2 Comprador", "Cuentas de prueba", "GET /cuentas-demo", "tokenComprador", None, None, 200, None),
    ("2 Comprador", "Crear mi perfil (comprador)", "POST /perfil", "tokenComprador", "perfil_comprador", None, 201, None),
    ("2 Comprador", "Buscar campanas publicadas (papa, Cusco)", "GET /campanas/publicadas", "tokenComprador", None, {"cultivo": "papa", "departamento": "Cusco"}, 200, None),
    ("2 Comprador", "Ver campana publicada", "GET /campanas/{campaniaId}", "tokenComprador", None, None, 200, None),
    ("2 Comprador", "Enviar oferta (insert por cola)", "POST /campanas/{campaniaId}/ofertas", "tokenComprador", "oferta", None, 202, ("ofertaId", "recursoId")),
    ("2 Comprador", "Mis ofertas (repetir hasta que aparezca)", "GET /ofertas", "tokenComprador", None, None, 200, None),
    ("3 Agricultor ve lo recibido", "Ofertas recibidas en mi campana", "GET /campanas/{campaniaId}/ofertas", "tokenAgricultor", None, None, 200, None),
    ("3 Agricultor ve lo recibido", "Ver campana (numeroOfertas = 1)", "GET /campanas/{campaniaId}", "tokenAgricultor", None, None, 200, None),
    ("3 Agricultor ve lo recibido", "Actualizar campana con ofertas (debe dar 409)", "PATCH /campanas/{campaniaId}", "tokenAgricultor", "campana_actualizar", None, 409, None),
    ("4 Seguridad (deben fallar)", "Registrar campana sin token", "POST /campanas", None, "campana", None, 401, None),
    ("4 Seguridad (deben fallar)", "Comprador intenta registrar campana", "POST /campanas", "tokenComprador", "campana", None, 403, None),
    ("4 Seguridad (deben fallar)", "Agricultor intenta ofertar", "POST /campanas/{campaniaId}/ofertas", "tokenAgricultor", "oferta", None, 403, None),
]

GUID = "__guid__"
#codigos alternativos validos: el perfil puede existir ya si se creo desde la web (409 = no se duplica)
ACEPTADOS = {"Crear mi perfil (agricultor)": (201, 409), "Crear mi perfil (comprador)": (201, 409)}


def aceptados(paso):
    return ACEPTADOS.get(paso[1], (paso[6],))


def cuerpos(doc):
    #parte del ejemplo del contrato y reemplaza ids y documentos por variables
    def base(nombre):
        return D.ejemplo(doc, {"$ref": "#/components/schemas/" + nombre})

    c = {}
    c["perfil_agricultor"] = dict(base("PerfilAgricultorCrear"), documento="{{dniAgricultor}}")
    c["perfil_comprador"] = dict(base("PerfilCompradorCrear"), documento="{{rucComprador}}", contactoCorreo="compras@correo.example")
    c["padron_empresa"] = dict(base("PadronConsulta"), tipoDoc="RUC", documento="{{rucComprador}}", uso="comprador")
    c["padron_representante"] = dict(base("PadronConsulta"), tipoDoc="DNI", documento="{{dniRepresentante}}", uso="representante")
    c["campana"] = dict(base("CampanaCrear"), campaniaId=GUID, precioAhoraPorKg="1.80", precioContraentregaPorKg="2.10")
    c["campana_actualizar"] = {"volumenKg": 1800, "precioAhoraPorKg": "1.95"}
    c["foto"] = dict(base("FotoUrlSolicitud"), fotoId=GUID)
    c["oferta"] = dict(base("OfertaCrear"), ofertaId=GUID, volumenKg=1200, precioPorKg="1.85", fechaEntrega="2027-06-20")
    return c


def texto_cuerpo(cuerpo, guid):
    return json.dumps(cuerpo, ensure_ascii=False, indent=2).replace('"' + GUID + '"', '"' + guid + '"')


def url(ruta, query, estilo):
    #estilo thunder usa {{var}} en la ruta; postman igual
    ruta = ruta.replace("{campaniaId}", "{{campaniaId}}")
    q = "&".join(k + "=" + v for k, v in (query or {}).items())
    return "{{baseUrl}}" + ruta + ("?" + q if q else "")


def ident(*partes):
    return str(uuid.uuid5(BASE, "/".join(str(p) for p in partes)))


def validar(doc):
    ops = set(D.operaciones(doc)) - D.OMITIR_OPERACIONES
    faltan = ops - set(DESTINOS)
    sobran = set(DESTINOS) - ops
    sin_paso = ops - {p[2] for p in PASOS}
    if faltan or sobran or sin_paso:
        raise SystemExit("coleccion desalineada con openapi.yaml: faltan " + str(sorted(faltan)) + ", sobran " + str(sorted(sobran)) +
                         ", sin paso " + str(sorted(sin_paso)))
    for p in PASOS:
        op = D.operaciones(doc)[p[2]]
        if str(p[6]) not in op.get("responses", {}):
            raise SystemExit("codigo " + str(p[6]) + " no declarado en el contrato para " + p[2])


def descripcion(paso):
    dom, tipo, destino, detalle = DESTINOS[paso[2]]
    return ("Microservicio: " + dom + ". Tipo: " + tipo + ". Destino: " + destino + ". Detalle: " + detalle +
            ". Esperado: " + str(paso[6]) + ".")


def thunder(doc, cs):
    col_id = ident("thunder", "coleccion")
    carpetas, requests = {}, []
    for i, p in enumerate(PASOS, 1):
        carpeta, nombre, clave, token, cuerpo, query, codigo, guardar = p
        if carpeta not in carpetas:
            carpetas[carpeta] = {"_id": ident("carpeta", carpeta), "name": carpeta, "containerId": "", "created": FECHA,
                                 "sortNum": 10000 * (len(carpetas) + 1)}
        metodo, ruta = clave.split(" ", 1)
        r = {"_id": ident("req", i), "colId": col_id, "containerId": carpetas[carpeta]["_id"],
             "name": "%02d %s" % (i, nombre), "url": url(ruta, query, "thunder"), "method": metodo,
             "sortNum": 10000 * i, "created": FECHA, "modified": FECHA, "headers": [], "params": [],
             "tests": [{"type": "res-code", "custom": "", "action": "equal", "value": str(codigo)}],
             "docs": descripcion(p)}
        if cuerpo:
            r["headers"].append({"name": "Content-Type", "value": "application/json"})
            r["body"] = {"type": "json", "raw": texto_cuerpo(cs[cuerpo], "{{#guid}}"), "form": []}
        if token:
            r["auth"] = {"type": "bearer", "bearer": "{{" + token + "}}"}
        if guardar:
            r["tests"].append({"type": "set-env-var", "custom": "json." + guardar[1], "action": "setto", "value": "{{" + guardar[0] + "}}"})
        requests.append(r)
    coleccion = {"clientName": "Thunder Client", "collectionName": "AgroCredit API v" + doc["info"]["version"],
                 "collectionId": col_id, "dateExported": FECHA, "version": "1.2", "folders": list(carpetas.values()),
                 "requests": requests}
    entorno = {"clientName": "Thunder Client", "environmentName": "agrocredit", "dateExported": FECHA, "version": "1.1",
               "folder": "", "data": [{"name": n, "value": v} for n, v, _ in ENTORNO]}
    return coleccion, entorno


def postman(doc, cs):
    carpetas = {}
    for i, p in enumerate(PASOS, 1):
        carpeta, nombre, clave, token, cuerpo, query, codigo, guardar = p
        metodo, ruta = clave.split(" ", 1)
        ruta_var = ruta.replace("{campaniaId}", "{{campaniaId}}")
        prueba = ['pm.test("codigo ' + str(codigo) + '", function () { pm.response.to.have.status(' + str(codigo) + '); });']
        if guardar:
            prueba.append('if (pm.response.code === ' + str(codigo) + ') { pm.environment.set("' + guardar[0] + '", pm.response.json().' + guardar[1] + '); }')
        req = {"method": metodo, "header": [], "description": descripcion(p),
               "url": {"raw": url(ruta, query, "postman"), "host": ["{{baseUrl}}"], "path": [x for x in ruta_var.split("/") if x],
                       "query": [{"key": k, "value": v} for k, v in (query or {}).items()]}}
        if cuerpo:
            req["header"].append({"key": "Content-Type", "value": "application/json"})
            req["body"] = {"mode": "raw", "raw": texto_cuerpo(cs[cuerpo], "{{$guid}}"), "options": {"raw": {"language": "json"}}}
        req["auth"] = ({"type": "bearer", "bearer": [{"key": "token", "value": "{{" + token + "}}", "type": "string"}]}
                       if token else {"type": "noauth"})
        carpetas.setdefault(carpeta, []).append({"name": "%02d %s" % (i, nombre), "request": req,
                                                 "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": prueba}}]})
    coleccion = {"info": {"_postman_id": ident("postman", "coleccion"), "name": "AgroCredit API v" + doc["info"]["version"],
                          "description": "Generada desde cloud/api/openapi.yaml con cloud/api/coleccion.py. Datos ficticios.",
                          "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
                 "item": [{"name": c, "item": items} for c, items in carpetas.items()]}
    entorno = {"id": ident("postman", "entorno"), "name": "agrocredit", "_postman_variable_scope": "environment",
               "values": [{"key": n, "value": v, "type": "secret" if n.startswith("token") else "default", "enabled": True} for n, v, _ in ENTORNO]}
    return coleccion, entorno


def leeme(doc, cs):
    filas = []
    for i, p in enumerate(PASOS, 1):
        dom, tipo, destino, detalle = DESTINOS[p[2]]
        cuerpo = "`cuerpos/%02d.json`" % i if p[4] else "-"
        filas.append("| %02d | %s | `%s` | %s | %s | %s | %s | %s |" % (i, p[1], p[2], p[3] or "sin token", cuerpo, dom, destino, p[6]))
    mapa = ["| API | Microservicio | Tipo | Tabla o servicio | Operacion |", "|---|---|---|---|---|"]
    mapa += ["| `%s` | %s | %s | %s | %s |" % (k, *v) for k, v in DESTINOS.items()]
    variables = ["| `%s` | %s |" % (n, d) for n, _, d in ENTORNO]
    return "\n".join([
        "# Coleccion de pruebas AgroCredit (Thunder Client y Postman)",
        "",
        "Generado por `cloud/api/coleccion.py` desde `cloud/api/openapi.yaml` v" + doc["info"]["version"] + ". No editar a mano: correr `python coleccion.py` en `cloud/api/` (o `python tareas.py documentar` y luego este script).",
        "",
        "## Archivos",
        "| Archivo | Para que |",
        "|---|---|",
        "| `thunder-collection_AgroCredit.json`, `thunder-environment_agrocredit.json` | Importar en Thunder Client (**la importacion es de la version de pago**) |",
        "| `agrocredit.postman_collection.json`, `agrocredit.postman_environment.json` | Importar en Postman (gratis) o en Thunder Client de pago |",
        "| `cuerpos/NN.json` | Cuerpo de cada peticion para pegar a mano en Thunder Client gratis (pestana Body > JSON) |",
        "",
        "## Antes de empezar",
        "1. Desplegar y correr `python tareas.py probar`; copiar el DNS de la linea `web:` y armar `baseUrl` = `http://<dns>/api/v1`.",
        "2. Crear dos cuentas en la web (agricultor con un DNI y comprador con un RUC, ficticios) e iniciar sesion con cada una.",
        "3. Sacar el ID token de cada sesion: en el navegador, con la web abierta y la sesion iniciada, abrir las herramientas de desarrollador (F12) > Consola y ejecutar:",
        "",
        "```js",
        "Object.entries(localStorage).find(([k]) => k.endsWith('.idToken'))[1]",
        "```",
        "",
        "   Copiar el texto (sin comillas) en `tokenAgricultor` o `tokenComprador`. Dura 60 minutos. Usar una ventana privada para la segunda cuenta.",
        "4. En Thunder Client gratis: crear el entorno `agrocredit` con las variables de abajo y crear cada peticion a mano con el metodo, la URL, Auth > Bearer `{{tokenAgricultor}}` o `{{tokenComprador}}` y el cuerpo de `cuerpos/`.",
        "5. Ejecutar en orden. Si el perfil ya se creo desde la web, `Crear mi perfil` responde 409 (correcto: no se duplica).",
        "",
        "`{{#guid}}` (Thunder) y `{{$guid}}` (Postman) generan un UUID nuevo en cada envio: es el id de idempotencia que en la web genera el navegador. En Thunder gratis, si la prueba no guarda la variable, copiar `recursoId` de la respuesta a `campaniaId` (o `ofertaId`) a mano.",
        "",
        "## Variables del entorno",
        "| Variable | Que es |",
        "|---|---|",
        *variables,
        "",
        "## Peticiones en orden",
        "| # | Peticion | API | Token | Cuerpo | Microservicio | Tabla o servicio | Esperado |",
        "|---|---|---|---|---|---|---|---|",
        *filas,
        "",
        "Las escrituras asincronas (202) no escriben en la tabla al responder: la API deja el mensaje en SQS y la Lambda `agro-worker` escribe en `agro-datos` en 1 a 2 segundos. Por eso `Ver campana` y `Mis ofertas` pueden dar 404 o lista vacia la primera vez: repetir.",
        "",
        "## Que tabla o servicio toca cada API",
        *mapa,
        "",
        "Evidencia en la base: despues de `Registrar campana` y `Enviar oferta`, consultar `agro-datos` con las consultas de `docs/base-datos/agrocredit-base-datos.md` (PartiQL en la consola de DynamoDB).",
        "",
    ])


def generar():
    doc = D.cargar()
    validar(doc)
    cs = cuerpos(doc)
    archivos = {}
    tc, te = thunder(doc, cs)
    pc, pe = postman(doc, cs)
    archivos["thunder-collection_AgroCredit.json"] = tc
    archivos["thunder-environment_agrocredit.json"] = te
    archivos["agrocredit.postman_collection.json"] = pc
    archivos["agrocredit.postman_environment.json"] = pe
    for i, p in enumerate(PASOS, 1):
        if p[4]:
            archivos[os.path.join("cuerpos", "%02d.json" % i)] = texto_cuerpo(cs[p[4]], "{{#guid}}")
    archivos["LEEME.md"] = leeme(doc, cs)
    archivos["api-tablas.json"] = {k: {"microservicio": v[0], "tipo": v[1], "destino": v[2], "operacion": v[3]} for k, v in DESTINOS.items()}
    return archivos


SALIDA_BRUNO = os.path.join(os.path.dirname(SALIDA), "bruno")
#variables de bruno: las privadas van en .env (no se comparte) y se leen como {{process.env.X}}
BRUNO_ENV = {"baseUrl": "BASE_URL", "tokenAgricultor": "TOKEN_AGRICULTOR", "tokenComprador": "TOKEN_COMPRADOR",
             "dniAgricultor": "DNI_AGRICULTOR", "rucComprador": "RUC_COMPRADOR", "dniRepresentante": "DNI_REPRESENTANTE"}


def celda_md(texto):
    #< > como entidades (si no, markdown los toma como etiquetas html) y | escapado
    return str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|")


def sangria(texto, n=2):
    return "\n".join((" " * n + l) if l else l for l in texto.splitlines())


def bruno_var(texto):
    #{{variable}} del entorno -> {{process.env.X}}; los ids guardados en ejecucion quedan como {{campaniaId}}
    for var, env in BRUNO_ENV.items():
        texto = texto.replace("{{" + var + "}}", "{{process.env." + env + "}}")
    return texto


OCULTAR = {"policy", "x-amz-signature", "x-amz-credential", "x-amz-security-token", "authorization"}


def ocultar(valor):
    #tokens, firmas, credenciales temporales de s3 y account id no se publican (decision 36)
    import re
    if isinstance(valor, dict):
        return {k: ("***" if k.lower() in OCULTAR else ocultar(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [ocultar(v) for v in valor]
    if isinstance(valor, str):
        valor = re.sub(r"(?<!\d)\d{12}(?!\d)", "<cuenta>", valor)
        if "X-Amz-" in valor and "?" in valor:
            return valor.split("?", 1)[0] + "?<firma temporal oculta>"
    return valor


def json_bonito(valor):
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return valor
    return json.dumps(ocultar(valor), ensure_ascii=False, indent=2)


def respuestas_reales():
    #ultima corrida real (python evidencia.py): nombre de la peticion -> (codigo, cuerpo, fecha lima)
    from datetime import datetime, timedelta, timezone
    ruta = os.path.join(SALIDA_BRUNO, ".reportes", "ultimo.json")
    if not os.path.exists(ruta):
        return {}
    fecha = datetime.fromtimestamp(os.path.getmtime(ruta), timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")
    with open(ruta, encoding="utf-8") as f:
        corrida = json.load(f)[0]
    return {r["name"][3:]: (r.get("response", {}).get("status"), r.get("response", {}).get("data"), fecha) for r in corrida["results"]}


DOCS_CARPETA = {
    "0 Plataforma (publico)": "APIs publicas, sin token. El balanceador usa `/salud` cada 5 s para saber si un contenedor puede recibir trafico; "
                              "`/config` le dice al navegador a que user pool de Cognito conectarse.",
    "1 Agricultor": "Flujo del agricultor con `TOKEN_AGRICULTOR`: perfil, catalogo, **insert de campana por cola** (SQS -> Lambda agro-worker -> agro-datos), "
                    "consulta, **update directo** de la campana (sin ofertas) y foto (URL prefirmada de S3).",
    "2 Comprador": "Flujo del comprador con `TOKEN_COMPRADOR`: padron (transaccion entre tablas de padron y agro-datos), cuentas de prueba, perfil, "
                   "busqueda por el indice `publicadas-por-cultivo` y **oferta por cola** (el worker suma `numeroOfertas` en la misma transaccion).",
    "3 Agricultor ve lo recibido": "El agricultor ve la oferta recibida, `numeroOfertas = 1`, y comprueba que ya **no puede** actualizar la campana (409).",
    "4 Seguridad (deben fallar)": "Controles de acceso: sin token 401; rol incorrecto 403. Que estas peticiones fallen es el resultado correcto.",
}


def docs_coleccion(doc):
    return "\n".join([
        "# AgroCredit API v" + doc["info"]["version"] + " (coleccion de evidencia)",
        "",
        "Generada desde `cloud/api/openapi.yaml` por `cloud/api/coleccion.py`. No editar a mano: regenerar.",
        "",
        "## Como usarla",
        "1. Copiar `.env.ejemplo` como `.env` en esta carpeta y completar `BASE_URL` (`http://<dns del ALB>/api/v1`, sale de `python tareas.py probar`).",
        "2. Iniciar sesion en la web con la cuenta de agricultor, abrir la consola del navegador y ejecutar:",
        "",
        "```js",
        "copy((() => { const k = Object.keys(localStorage).find(k => k.endsWith('.LastAuthUser')); return localStorage[k.slice(0, -13) + '.' + localStorage[k] + '.idToken']; })())",
        "```",
        "",
        "3. Pegar en `TOKEN_AGRICULTOR`; repetir con la cuenta de comprador para `TOKEN_COMPRADOR`. Completar `DNI_AGRICULTOR` y `RUC_COMPRADOR` con los documentos de esas cuentas. Los tokens duran 60 minutos.",
        "4. Elegir el entorno `agrocredit` y correr la coleccion en orden (Runner, con 2.5 s de espera entre peticiones: las escrituras por cola tardan 1 a 2 s).",
        "",
        "## Que demuestra",
        "- Lecturas por clave e indices de DynamoDB, insert asincrono (202, SQS + Lambda), update directo condicional (200 / 409), transaccion del padron y controles de acceso (401 / 403).",
        "- Cada peticion tiene en **Docs**: microservicio, tabla o servicio AWS, operacion de DynamoDB y la respuesta real de la ultima corrida en AWS.",
        "- Evidencia completa: `docs/api/evidencia-apis.md`. Modelo de datos y consultas PartiQL: `docs/base-datos/agrocredit-base-datos.md`.",
        "",
        "Datos ficticios (Ley 29733). `.env` y `.reportes/` no se comparten (tienen tokens).",
    ])


def docs_peticion(p, real):
    dom, tipo, destino, operacion = DESTINOS[p[2]]
    validos = " o ".join(map(str, aceptados(p)))
    lineas = ["# " + p[1], "",
              "| | |", "|---|---|",
              "| API | `" + p[2] + "` |",
              "| Token | " + {"tokenAgricultor": "agricultor", "tokenComprador": "comprador"}.get(p[3], "sin token") + " |",
              "| Microservicio | " + dom + " |",
              "| Tipo | " + tipo + " |",
              "| Tabla o servicio | " + destino.replace("|", "/") + " |",
              "| Operacion | " + operacion.replace("|", "/") + " |",
              "| Esperado | " + validos + " |", ""]
    if p[7]:
        lineas += ["Guarda `" + p[7][0] + "` (de `" + p[7][1] + "` en la respuesta) para las peticiones siguientes.", ""]
    if p[1] in ACEPTADOS:
        lineas += ["409 tambien es correcto: el perfil ya existe y no se duplica.", ""]
    if real:
        codigo, datos, fecha = real
        lineas += ["## Respuesta real en AWS (" + fecha + " hora de Lima): " + str(codigo), "", "```json",
                   json_bonito(datos) if datos not in (None, "") else "(sin cuerpo)", "```"]
    else:
        lineas += ["Respuesta real: aun no se ha corrido contra AWS (`python evidencia.py`)."]
    return "\n".join(lineas)


def bruno(doc, cs):
    archivos = {"bruno.json": {"version": "1", "name": "AgroCredit API v" + doc["info"]["version"], "type": "collection",
                               "ignore": ["node_modules", ".git", ".reportes"]}}
    archivos[os.path.join("environments", "agrocredit.bru")] = "vars {\n  baseUrl: {{process.env.BASE_URL}}\n}\n"
    archivos[".env.ejemplo"] = "\n".join([
        "#copiar como .env (no se comparte) y completar; los tokens duran 60 minutos",
        "BASE_URL=http://<dns-del-alb>/api/v1",
        "TOKEN_AGRICULTOR=",
        "TOKEN_COMPRADOR=",
        "DNI_AGRICULTOR=12345678",
        "RUC_COMPRADOR=20123456789",
        "DNI_REPRESENTANTE=87654321",
        ""])
    archivos["collection.bru"] = "docs {\n" + sangria(docs_coleccion(doc)) + "\n}\n"
    reales = respuestas_reales()
    carpetas = []
    for i, p in enumerate(PASOS, 1):
        carpeta, nombre, clave, token, cuerpo, query, codigo, guardar = p
        if carpeta not in carpetas:
            carpetas.append(carpeta)
            archivos[os.path.join(carpeta, "folder.bru")] = ("meta {\n  name: %s\n  seq: %d\n}\n\ndocs {\n%s\n}\n"
                                                              % (carpeta, len(carpetas), sangria(DOCS_CARPETA[carpeta])))
        metodo, ruta = clave.split(" ", 1)
        partes = ["meta {\n  name: %02d %s\n  type: http\n  seq: %d\n}" % (i, nombre, i)]
        partes.append("%s {\n  url: %s\n  body: %s\n  auth: %s\n}" % (
            metodo.lower(), bruno_var(url(ruta, query, "bruno")), "json" if cuerpo else "none", "bearer" if token else "none"))
        if query:
            partes.append("params:query {\n" + "\n".join("  %s: %s" % kv for kv in query.items()) + "\n}")
        if cuerpo:
            partes.append("headers {\n  Content-Type: application/json\n}")
        if token:
            partes.append("auth:bearer {\n  token: " + bruno_var("{{" + token + "}}") + "\n}")
        if cuerpo:
            partes.append("body:json {\n" + sangria(bruno_var(texto_cuerpo(cs[cuerpo], "{{$randomUUID}}"))) + "\n}")
        if guardar:
            partes.append("script:post-response {\n  if (res.getStatus() === %d) {\n    bru.setVar(\"%s\", res.getBody().%s);\n  }\n}"
                          % (codigo, guardar[0], guardar[1]))
        validos = aceptados(p)
        partes.append("tests {\n  test(\"codigo %s\", function () {\n    expect([%s]).to.include(res.getStatus());\n  });\n}"
                      % (" o ".join(map(str, validos)), ", ".join(map(str, validos))))
        partes.append("docs {\n" + sangria(docs_peticion(p, reales.get(nombre))) + "\n}")
        archivos[os.path.join(carpeta, "%02d %s.bru" % (i, nombre))] = "\n\n".join(partes) + "\n"
    return archivos


def limpiar_generados():
    #borra solo lo que genera este script (carpetas "N ..." de bruno y cuerpos/); conserva .env y .reportes
    import shutil
    if os.path.isdir(SALIDA_BRUNO):
        for n in os.listdir(SALIDA_BRUNO):
            ruta = os.path.join(SALIDA_BRUNO, n)
            if os.path.isdir(ruta) and n[:1].isdigit() and n[1:2] == " ":
                shutil.rmtree(ruta)
    shutil.rmtree(os.path.join(SALIDA, "cuerpos"), ignore_errors=True)


def escribir():
    doc = D.cargar()
    validar(doc)
    limpiar_generados()
    for nombre, contenido in bruno(doc, cuerpos(doc)).items():
        ruta = os.path.join(SALIDA_BRUNO, nombre)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        texto = contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False, indent=2)
        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto + ("" if texto.endswith("\n") else "\n"))
    for nombre, contenido in generar().items():
        ruta = os.path.join(SALIDA, nombre)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        texto = contenido if isinstance(contenido, str) else json.dumps(contenido, ensure_ascii=False, indent=2)
        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto + ("" if texto.endswith("\n") else "\n"))
    return SALIDA


if __name__ == "__main__":
    print("coleccion escrita en: " + escribir())
