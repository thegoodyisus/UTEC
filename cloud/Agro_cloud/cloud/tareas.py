#punto de entrada unico del despliegue de agrocredit (mac y windows)
#uso: python tareas.py <accion>
#acciones: preparar, init, plan, pruebas, documentar, flujo, padron, desplegar [--revisar] [--sin-pruebas], probar, caida [api|web] [--brusca], apagar, encender, destruir [--por-prefijo]
#pendiente: empaquetar (debe incluir cloud/semillas/ y web/)
import atexit
import base64
import hashlib
import io
import json
import os
import platform
import re
import secrets
import shutil
import ssl
import stat
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
CONEXION = os.path.join(RAIZ, "Conexion")
DIR_TF = os.path.join(AQUI, "terraform")
PARAMETROS = os.path.join(DIR_TF, "parametros.tfvars")
CUENTA_ESTADO = os.path.join(DIR_TF, ".cuenta-estado")
#token del endpoint de caida brusca: uno por despliegue, se borra al destruir; no se comparte
TOKEN_DEMO = os.path.join(DIR_TF, ".token-demo")
HERRAMIENTAS = os.path.join(AQUI, ".herramientas")
#cada corrida deja registros/<accion>-<fecha>.txt (resumen) y -completo.txt (todo sin colores)
REGISTROS = os.path.join(AQUI, "registros")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
IMPORTANTE = re.compile(
    r"^(Plan:|Apply complete|Destroy complete|No changes|Error:|ERROR|error:|.*digest: sha256"
    r"|.*: (Creation|Destruction|Modifications) complete after|\u2502 (Error|Warning):|=+ .*(passed|failed|error)|FAILED |[0-9]+ (passed|failed))"
)
RESUMEN = []
COMPLETO = []
#que entra en cada imagen: el tag es el hash de estos archivos (mismo contenido = mismo tag)
#la web sale de web/ en la raiz del proyecto (v05, decisiones 61 y 62): "origen" indica de donde se copia cada entrada al contexto de docker
SITIO_WEB = os.path.join(RAIZ, "web")
IMAGENES = {
    "web": {"dir": os.path.join(AQUI, "web"), "entradas": ["Dockerfile", "nginx.conf", "40-salud.sh", "sitio"],
            "origen": {"sitio": SITIO_WEB}},
    "api": {"dir": os.path.join(AQUI, "api"), "entradas": ["Dockerfile", "requirements.txt", "app"]},
}
IGNORAR = {"__pycache__", ".DS_Store"}
#lambdas: cada carpeta se empaqueta en un zip reproducible (solo los .py de la carpeta; boto3 lo trae el runtime)
LAMBDAS = ["worker", "etiquetar"]
CONSTRUCCION = os.path.join(AQUI, ".construccion")
#reemplazos sin datos ni costo que no piden confirmacion en desplegar
REEMPLAZO_SEGURO = {"time_static", "aws_ecs_task_definition"}

TF_VERSION = "1.16.5"
#sha256 oficiales de releases.hashicorp.com (decision 39)
TF_SHA256 = {
    "darwin_amd64": "9809158e481cf2d3a8433e59179f397b8edb5172397711bd98f6bb32edcaf53b",
    "darwin_arm64": "ecdef65e24193d627f27c39baeda31295f08c938d8a3d4764f442fb916d4b7dc",
    "windows_amd64": "01700102b7291f95c0ab61394b55bfd5f57a12ac65632c2c1958691c8cf438ef",
    "windows_arm64": "f5978cc73678af764c0799cd4960f93a600d89daa23f833c6f3070f2e758c490",
}
#hashicorp/aws 6.67.0 y time 0.14.2 no se publican para windows_arm64: esos equipos usan windows_amd64 (emulacion x64)
PLATAFORMAS_LOCK = ["darwin_arm64", "darwin_amd64", "windows_amd64"]

#si el python actual no tiene botocore, se relanza con el del .venv de Conexion
try:
    import botocore
    import botocore.session
    from botocore.exceptions import BotoCoreError, ClientError
except ModuleNotFoundError:
    if not os.environ.get("TAREAS_RELANZADO"):
        for rel in (os.path.join(".venv", "bin", "python"), os.path.join(".venv", "Scripts", "python.exe")):
            py = os.path.join(CONEXION, rel)
            if os.path.exists(py):
                os.environ["TAREAS_RELANZADO"] = "1"
                sys.exit(subprocess.call([py] + sys.argv))
    print("falta el entorno de python: en Conexion ejecuta bash ./preparar.sh (windows: .\\preparar.ps1)")
    sys.exit(1)


def anotar(texto, resumen=True):
    limpio = ANSI.sub("", str(texto)).rstrip("\n")
    COMPLETO.append(limpio)
    if resumen:
        RESUMEN.append(limpio)


def salida(texto):
    print(texto)
    anotar(texto)


def info(texto):
    salida("[tareas] " + texto)


def fallar(texto):
    salida("[tareas] ERROR: " + texto)
    sys.exit(1)


def ejecutar(comando, cwd=None, env=None, entrada=None):
    #muestra la salida en pantalla, la guarda completa y deja en el resumen solo lo importante
    p = subprocess.Popen(
        comando, cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace", bufsize=1,
        stdin=subprocess.PIPE if entrada is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if entrada is not None:
        p.stdin.write(entrada)
        p.stdin.close()
    ultimas = []
    en_error = False
    for linea in p.stdout:
        try:
            sys.stdout.write(linea)
        except UnicodeEncodeError:
            sys.stdout.write(linea.encode("ascii", "replace").decode())
        sys.stdout.flush()
        limpia = ANSI.sub("", linea).rstrip("\n")
        COMPLETO.append(limpia)
        ultimas = (ultimas + [limpia])[-25:]
        if IMPORTANTE.match(limpia):
            RESUMEN.append(limpia)
            en_error = "Error" in limpia
        elif en_error and limpia.startswith("\u2502"):
            RESUMEN.append(limpia)
        else:
            en_error = False
    r = p.wait()
    if r != 0:
        RESUMEN.append("--- ultimas lineas antes de la falla ---")
        RESUMEN.extend(ultimas)
    return r


def guardar_registro():
    if not COMPLETO:
        return
    os.makedirs(REGISTROS, exist_ok=True)
    accion = sys.argv[1] if len(sys.argv) > 1 else "sin-accion"
    if len(sys.argv) > 2:
        accion += "-" + "-".join(a.strip("-") for a in sys.argv[2:])
    base = os.path.join(REGISTROS, accion + "-" + time.strftime("%Y%m%d-%H%M%S"))
    cabecera = ["#python tareas.py " + " ".join(sys.argv[1:]), "#fecha local " + time.strftime("%Y-%m-%d %H:%M:%S"), ""]
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write("\n".join(cabecera + RESUMEN) + "\n")
    with open(base + "-completo.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(cabecera + COMPLETO) + "\n")
    print("[tareas] registro: " + os.path.relpath(base + ".txt", RAIZ) + " (y -completo.txt)")


def plataforma():
    so = {"darwin": "darwin", "win32": "windows"}.get(sys.platform)
    maq = platform.machine().lower()
    arq = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(maq)
    if not so or not arq:
        fallar("plataforma no soportada: " + sys.platform + " " + maq + " (solo mac y windows)")
    if so == "windows" and arq == "arm64":
        arq = "amd64"
    return so + "_" + arq


def ruta_terraform():
    nombre = "terraform.exe" if sys.platform == "win32" else "terraform"
    return os.path.join(HERRAMIENTAS, "terraform-" + TF_VERSION, plataforma(), nombre)


def contexto_ssl():
    #se usa el certificado raiz que trae botocore: evita fallas de certificados en python de mac
    return ssl.create_default_context(cafile=os.path.join(os.path.dirname(botocore.__file__), "cacert.pem"))


def entorno_aws():
    cred = os.path.join(CONEXION, "credenciales.txt")
    if not os.path.exists(cred):
        fallar("no existe Conexion/credenciales.txt: pega ahi el bloque AWS CLI de AWS Details")
    env = dict(os.environ)
    env["AWS_SHARED_CREDENTIALS_FILE"] = cred
    env["AWS_REGION"] = parametros()["region"]
    env["AWS_DEFAULT_REGION"] = env["AWS_REGION"]
    env["AWS_PAGER"] = ""
    env.pop("AWS_PROFILE", None)
    return env


def parametros():
    if not os.path.exists(PARAMETROS):
        fallar("no existe terraform/parametros.tfvars")
    valores = {}
    with open(PARAMETROS, encoding="utf-8") as f:
        for linea in f:
            m = re.match(r'^\s*([a-z_]+)\s*=\s*"?([^"#\n]*?)"?\s*(#.*)?$', linea)
            if m:
                valores[m.group(1)] = m.group(2).strip()
    for clave in ("prefijo", "region"):
        if not valores.get(clave):
            fallar("falta " + clave + " en parametros.tfvars")
    return valores


def cuenta_actual():
    env = entorno_aws()
    os.environ.update({k: env[k] for k in ("AWS_SHARED_CREDENTIALS_FILE", "AWS_REGION", "AWS_DEFAULT_REGION")})
    try:
        sts = botocore.session.get_session().create_client("sts", region_name=env["AWS_REGION"])
        return sts.get_caller_identity()["Account"]
    except (ClientError, BotoCoreError) as e:
        texto = str(e)
        if "expired" in texto.lower() or "ExpiredToken" in texto:
            fallar("credenciales vencidas: inicia el lab y pega el bloque nuevo en Conexion/credenciales.txt")
        fallar("no se pudo validar la cuenta: " + texto[:200])


def terraform(*args, interactivo=False):
    tf = ruta_terraform()
    if not os.path.exists(tf):
        fallar("terraform no esta instalado: ejecuta python tareas.py preparar")
    comando = [tf] + list(args)
    info("terraform " + " ".join("-var=token_demo=***" if a.startswith("-var=token_demo=") else a for a in args))
    r = ejecutar(comando, cwd=DIR_TF, env=entorno_aws())
    if r != 0:
        fallar("terraform " + args[0] + " termino con codigo " + str(r))


def instalar_terraform():
    plat = plataforma()
    tf = ruta_terraform()
    if os.path.exists(tf):
        salida = subprocess.run([tf, "version", "-json"], capture_output=True, text=True)
        try:
            if json.loads(salida.stdout)["terraform_version"] == TF_VERSION:
                info("terraform " + TF_VERSION + " ya instalado (" + plat + ")")
                return
        except (ValueError, KeyError):
            pass
    url = "https://releases.hashicorp.com/terraform/{v}/terraform_{v}_{p}.zip".format(v=TF_VERSION, p=plat)
    info("descargando " + url)
    with urllib.request.urlopen(url, timeout=120, context=contexto_ssl()) as r:
        datos = r.read()
    calculado = hashlib.sha256(datos).hexdigest()
    if calculado != TF_SHA256[plat]:
        fallar("el sha256 del zip no coincide; no se instala. esperado " + TF_SHA256[plat] + " obtenido " + calculado)
    info("sha256 verificado")
    destino = os.path.dirname(tf)
    if os.path.exists(destino):
        shutil.rmtree(destino)
    os.makedirs(destino)
    with zipfile.ZipFile(io.BytesIO(datos)) as z:
        z.extract(os.path.basename(tf), destino)
    if sys.platform != "win32":
        os.chmod(tf, os.stat(tf).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    info("terraform " + TF_VERSION + " instalado en " + os.path.relpath(tf, RAIZ))


def revisar_docker():
    if not shutil.which("docker"):
        info("AVISO: docker no esta instalado; se necesita para construir imagenes (paso 7)")
        return
    r = subprocess.run(["docker", "info", "--format", "{{.Architecture}}"], capture_output=True, text=True)
    if r.returncode != 0:
        info("AVISO: docker esta instalado pero no corriendo: abre Docker Desktop antes de desplegar imagenes")
    else:
        info("docker corriendo (" + r.stdout.strip() + ")")


def accion_preparar():
    if sys.version_info < (3, 9):
        fallar("se necesita python 3.9 o superior")
    info("python " + platform.python_version() + " con botocore " + botocore.__version__)
    instalar_terraform()
    revisar_docker()
    p = parametros()
    info("parametros: prefijo " + p["prefijo"] + ", region " + p["region"])
    info("listo. siguiente: python tareas.py init")


def accion_init():
    cuenta = cuenta_actual()
    info("cuenta " + cuenta)
    estado = os.path.join(DIR_TF, "terraform.tfstate")
    anterior = open(CUENTA_ESTADO).read().strip() if os.path.exists(CUENTA_ESTADO) else ""
    if anterior and anterior != cuenta and os.path.exists(estado):
        #cuenta regenerada: el estado viejo apunta a recursos que ya no existen
        marca = time.strftime("%Y%m%d-%H%M%S")
        for nombre in ("terraform.tfstate", "terraform.tfstate.backup"):
            origen = os.path.join(DIR_TF, nombre)
            if os.path.exists(origen):
                os.replace(origen, os.path.join(DIR_TF, "estado-anterior-" + anterior + "-" + marca + "-" + nombre))
        info("la cuenta cambio (" + anterior + " -> " + cuenta + "): estado anterior archivado, se parte de cero")
    with open(CUENTA_ESTADO, "w") as f:
        f.write(cuenta)
    terraform("init", "-input=false")
    #se registran los hashes de proveedores para las 4 plataformas del curso
    terraform("providers", "lock", *["-platform=" + p for p in PLATAFORMAS_LOCK])
    info("listo. siguiente: python tareas.py plan")


def archivos_imagen(servicio):
    #(nombre dentro del contexto en formato posix, ruta real) de todo lo que entra en la imagen
    conf = IMAGENES[servicio]
    salida = []
    for entrada in conf["entradas"]:
        ruta = conf.get("origen", {}).get(entrada) or os.path.join(conf["dir"], entrada)
        if not os.path.exists(ruta):
            fallar("falta " + os.path.relpath(ruta, RAIZ))
        if os.path.isfile(ruta):
            salida.append((entrada, ruta))
            continue
        #orden por entrada y, dentro de cada una, por nombre (mismo tag que antes de la decision 61)
        bloque = []
        for base, dirs, nombres in os.walk(ruta):
            dirs[:] = sorted(d for d in dirs if d not in IGNORAR)
            for n in nombres:
                if n not in IGNORAR:
                    a = os.path.join(base, n)
                    bloque.append((entrada + "/" + os.path.relpath(a, ruta).replace(os.sep, "/"), a))
        salida += sorted(bloque)
    return salida


def hash_imagen(servicio):
    #hash del contenido, con rutas en formato posix para que mac y windows den el mismo tag
    h = hashlib.sha256()
    for nombre, ruta in archivos_imagen(servicio):
        h.update(nombre.encode())
        with open(ruta, "rb") as f:
            h.update(hashlib.sha256(f.read()).digest())
    return h.hexdigest()[:12]


def contexto_imagen(servicio):
    #si alguna entrada viene de otra carpeta (la web desde web/) se arma el contexto en .construccion
    conf = IMAGENES[servicio]
    if not conf.get("origen"):
        return conf["dir"]
    destino = os.path.join(CONSTRUCCION, "contexto-" + servicio)
    if os.path.isdir(destino):
        shutil.rmtree(destino)
    for nombre, ruta in archivos_imagen(servicio):
        final = os.path.join(destino, *nombre.split("/"))
        os.makedirs(os.path.dirname(final), exist_ok=True)
        shutil.copy2(ruta, final)
    ignorar = os.path.join(conf["dir"], ".dockerignore")
    if os.path.exists(ignorar):
        shutil.copy2(ignorar, os.path.join(destino, ".dockerignore"))
    return destino


def uri_imagen(cuenta, servicio):
    p = parametros()
    return cuenta + ".dkr.ecr." + p["region"] + ".amazonaws.com/" + p["prefijo"] + servicio + ":" + hash_imagen(servicio)


def token_demo(crear=False):
    if os.path.exists(TOKEN_DEMO):
        with open(TOKEN_DEMO) as f:
            return f.read().strip()
    if not crear:
        return ""
    token = secrets.token_urlsafe(24)
    with open(TOKEN_DEMO, "w") as f:
        f.write(token)
    return token


def construir_zip(nombre):
    #zip determinista (fechas fijas y orden estable): mismo contenido = mismo hash = terraform no lo actualiza
    origen = os.path.join(AQUI, "lambdas", nombre)
    archivos = sorted(f for f in os.listdir(origen) if f.endswith(".py"))
    if "app.py" not in archivos:
        fallar("falta lambdas/" + nombre + "/app.py")
    h = hashlib.sha256()
    for f in archivos:
        with open(os.path.join(origen, f), "rb") as a:
            h.update(f.encode() + b"\0" + a.read())
    os.makedirs(CONSTRUCCION, exist_ok=True)
    nombre_zip = nombre + "-" + h.hexdigest()[:12] + ".zip"
    destino = os.path.join(CONSTRUCCION, nombre_zip)
    if not os.path.exists(destino):
        with zipfile.ZipFile(destino + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
            for f in archivos:
                info_zip = zipfile.ZipInfo(f, date_time=(1980, 1, 1, 0, 0, 0))
                info_zip.external_attr = 0o644 << 16
                info_zip.compress_type = zipfile.ZIP_DEFLATED
                with open(os.path.join(origen, f), "rb") as a:
                    z.writestr(info_zip, a.read())
        os.replace(destino + ".tmp", destino)
        for viejo in os.listdir(CONSTRUCCION):
            if viejo.startswith(nombre + "-") and viejo.endswith(".zip") and viejo != nombre_zip:
                os.remove(os.path.join(CONSTRUCCION, viejo))
    #ruta relativa a cloud/terraform con barras normales: funciona igual en mac y windows
    return "../.construccion/" + nombre_zip


def variables_tf(cuenta):
    marca = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return ["-var=zip_" + n + "=" + construir_zip(n) for n in LAMBDAS] + [
        "-var=token_demo=" + (token_demo() or "sin-token"),
        "-var-file=parametros.tfvars",
        "-var=imagen_web=" + uri_imagen(cuenta, "web"),
        "-var=imagen_api=" + uri_imagen(cuenta, "api"),
        "-var=marca_despliegue=" + marca,
    ]


def accion_plan():
    cuenta = cuenta_actual()
    terraform("plan", "-input=false", *variables_tf(cuenta))


def terraform_json(*args):
    r = subprocess.run([ruta_terraform()] + list(args), cwd=DIR_TF, env=entorno_aws(), capture_output=True, text=True)
    if r.returncode != 0:
        fallar("terraform " + args[0] + ": " + (r.stderr or r.stdout)[-300:])
    return json.loads(r.stdout)


def docker(*args, entrada=None):
    r = ejecutar(["docker"] + list(args), entrada=entrada)
    if r != 0:
        fallar("docker " + args[0] + " termino con codigo " + str(r))


def docker_corre():
    return bool(shutil.which("docker")) and subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def abrir_docker_desktop():
    #intenta abrir docker desktop segun el sistema; devuelve false si no lo encuentra
    if sys.platform == "darwin":
        return subprocess.run(["open", "-a", "Docker"], capture_output=True).returncode == 0
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramW6432", "")):
            exe = os.path.join(base, "Docker", "Docker", "Docker Desktop.exe")
            if base and os.path.exists(exe):
                subprocess.Popen([exe])
                return True
    return False


def exigir_docker():
    #docker es dependencia de desplegar: si esta instalado pero cerrado, se abre y se espera
    if docker_corre():
        return
    info("docker no esta corriendo: abriendo Docker Desktop")
    if not abrir_docker_desktop():
        fallar("no se encontro Docker Desktop: instalalo (mac o windows) y vuelve a ejecutar")
    limite = time.time() + 180
    while time.time() < limite:
        time.sleep(5)
        if docker_corre():
            info("docker listo")
            return
        info("esperando a Docker Desktop...")
    fallar("Docker Desktop no arranco en 3 min: revisalo y vuelve a ejecutar")


def fase_imagenes(cuenta):
    #fase 1: repos ecr ; fase 2: construir arm64 y subir solo si el tag no existe
    prefijo = parametros()["prefijo"]
    ecr = cliente("ecr")
    faltan = []
    for servicio in IMAGENES:
        try:
            ecr.describe_repositories(repositoryNames=[prefijo + servicio])
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "RepositoryNotFoundException":
                raise
            faltan.append(servicio)
    if faltan:
        info("fase 1: creando repositorios ecr (" + ", ".join(faltan) + ")")
        objetivos = ["-target=aws_ecr_repository.repo[\"" + s + "\"]" for s in IMAGENES]
        terraform("apply", "-input=false", "-auto-approve", *objetivos, *variables_tf(cuenta))
    pendientes = []
    for servicio in IMAGENES:
        tag = hash_imagen(servicio)
        try:
            ecr.describe_images(repositoryName=prefijo + servicio, imageIds=[{"imageTag": tag}])
            info("imagen " + servicio + ":" + tag + " ya esta en ecr, no se reconstruye")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ImageNotFoundException":
                raise
            pendientes.append(servicio)
    if not pendientes:
        return
    dato = ecr.get_authorization_token()["authorizationData"][0]
    usuario, clave = base64.b64decode(dato["authorizationToken"]).decode().split(":", 1)
    docker("login", "--username", usuario, "--password-stdin", dato["proxyEndpoint"], entrada=clave)
    for servicio in pendientes:
        uri = uri_imagen(cuenta, servicio)
        info("fase 2: construyendo " + uri + " (linux/arm64)")
        docker("build", "--platform", "linux/arm64", "-t", uri, contexto_imagen(servicio))
        docker("push", uri)


def limpiar_registros():
    #cada desplegar abre una secuencia nueva: se borran los registros de la anterior
    if not os.path.isdir(REGISTROS):
        return
    viejos = [n for n in os.listdir(REGISTROS) if n.endswith(".txt")]
    for n in viejos:
        os.remove(os.path.join(REGISTROS, n))
    if viejos:
        info("registros anteriores borrados: " + str(len(viejos)))


def accion_pruebas():
    #pruebas de la api en un contenedor: nada que instalar en el equipo; el codigo se monta, no se copia
    exigir_docker()
    dir_api = IMAGENES["api"]["dir"]
    h = hashlib.sha256()
    for nombre in ("requirements.txt", "requirements-pruebas.txt", "pruebas.Dockerfile"):
        with open(os.path.join(dir_api, nombre), "rb") as f:
            h.update(f.read())
    imagen = "agrocredit-pruebas-api:" + h.hexdigest()[:12]
    if subprocess.run(["docker", "image", "inspect", imagen], capture_output=True).returncode != 0:
        info("construyendo la imagen de pruebas (solo la primera vez o si cambian las dependencias)")
        docker("build", "-t", imagen, "-f", os.path.join(dir_api, "pruebas.Dockerfile"), dir_api)
    info("pruebas: api (reglas de negocio, seguridad, deriva contra openapi.yaml) y lambdas (worker, etiquetar)")
    #la web desplegada (web/) se monta aparte, solo lectura, para las pruebas del panel
    r = ejecutar(["docker", "run", "--rm", "--mount", "type=bind,source=" + AQUI + ",target=/srv",
                  "--mount", "type=bind,source=" + SITIO_WEB + ",target=/sitio,readonly", "-w", "/srv",
                  "-e", "PYTHONPATH=/srv/api", "-e", "SITIO_WEB=/sitio", imagen,
                  "pytest", "-q", "-p", "no:cacheprovider", "-c", "api/pytest.ini", "--rootdir", "/srv",
                  "api/pruebas", "lambdas/pruebas_lambdas"])
    if r != 0:
        fallar("las pruebas fallaron: corrige antes de desplegar")
    info("pruebas OK")


def a_dynamo(valor):
    if isinstance(valor, bool):
        return {"BOOL": valor}
    if isinstance(valor, int):
        return {"N": str(valor)}
    if isinstance(valor, str):
        return {"S": valor}
    if isinstance(valor, list):
        return {"L": [a_dynamo(v) for v in valor]}
    if isinstance(valor, dict):
        return {"M": {k: a_dynamo(v) for k, v in valor.items()}}
    raise ValueError("tipo no soportado en semillas: " + type(valor).__name__)


def escribir_lote(ddb, tabla, items):
    for i in range(0, len(items), 25):
        pedido = {tabla: [{"PutRequest": {"Item": {k: a_dynamo(v) for k, v in it.items()}}} for it in items[i:i + 25]]}
        for _ in range(10):
            pendiente = ddb.batch_write_item(RequestItems=pedido).get("UnprocessedItems")
            if not pendiente:
                break
            pedido = pendiente
            time.sleep(1)
        else:
            fallar("no se pudieron cargar los datos iniciales en " + tabla)


def sembrar(s):
    #catalogo y cuentas en agro-datos se actualizan siempre
    #el padron (cloud/semillas/*.json) se carga una sola vez en sus tablas propias (decision 58): no se rellena lo consumido
    #la marca SIEMBRA/PADRON guarda la fecha de creacion de cada tabla de padron: si una tabla se recreo, se vuelve a cargar
    sys.path.insert(0, AQUI)
    import semillas
    ddb = cliente("dynamodb")
    tabla, padron = s["tabla"], s["tablas_padron"]
    escribir_lote(ddb, tabla, semillas.items_catalogo() + semillas.items_cuentas())
    creadas = {padron[k]: "%.3f" % ddb.describe_table(TableName=padron[k])["Table"]["CreationDateTime"].timestamp() for k in ("personas", "empresas")}
    marca = ddb.get_item(TableName=tabla, Key={"PK": {"S": "SIEMBRA"}, "SK": {"S": "PADRON"}}, ConsistentRead=True).get("Item", {})
    previas = {k: v.get("S") for k, v in marca.get("tablasPadron", {}).get("M", {}).items()}
    nuevo_padron = previas != creadas
    if nuevo_padron:
        personas, empresas = semillas.items_padron()
        escribir_lote(ddb, padron["personas"], personas)
        escribir_lote(ddb, padron["empresas"], empresas)
        escribir_lote(ddb, tabla, [{"PK": "SIEMBRA", "SK": "PADRON", "entidad": "SIEMBRA", "tablasPadron": creadas,
                                    "creadoEn": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}])
    info("datos iniciales: catalogo " + str(len(semillas.CULTIVOS)) + " cultivos, " + str(len(semillas.CUENTAS)) + " cuentas de prueba" +
         (", padron " + str(len(personas)) + " personas en " + padron["personas"] + " y " + str(len(empresas)) + " empresas en " + padron["empresas"]
          if nuevo_padron else "; el padron ya estaba cargado (no se rellena)"))


def accion_desplegar():
    #sin confirmacion si solo crea o modifica; pide confirmacion si borra o reemplaza algo
    #python tareas.py desplegar --revisar  obliga a confirmar siempre
    limpiar_registros()
    #docker se revisa antes de crear cualquier cosa en aws
    exigir_docker()
    if "--sin-pruebas" not in sys.argv:
        accion_pruebas()
    cuenta = cuenta_actual()
    info("desplegando en la cuenta " + cuenta + " con prefijo " + parametros()["prefijo"])
    token_demo(crear=True)
    fase_imagenes(cuenta)
    info("fase 3: despliegue completo (espera a que las tareas esten sanas, unos minutos)")
    plan = os.path.join(DIR_TF, ".plan-desplegar")
    try:
        terraform("plan", "-input=false", *variables_tf(cuenta), "-out=" + os.path.basename(plan))
        cambios = terraform_json("show", "-json", os.path.basename(plan)).get("resource_changes", [])
        conteo = {"crear": 0, "modificar": 0, "renovar": 0, "borrar": []}
        for c in cambios:
            acciones = c["change"]["actions"]
            if "delete" in acciones and c["type"] in REEMPLAZO_SEGURO and "create" in acciones:
                conteo["renovar"] += 1
            elif "delete" in acciones:
                conteo["borrar"].append(c["address"] + (" (reemplazo)" if "create" in acciones else ""))
            elif "create" in acciones:
                conteo["crear"] += 1
            elif "update" in acciones:
                conteo["modificar"] += 1
        #renovar = reemplazo sin datos ni costo (time_static, task definitions); terraform lo cuenta como add + destroy
        info("plan: crear " + str(conteo["crear"]) + ", modificar " + str(conteo["modificar"]) + ", renovar sin riesgo " + str(conteo["renovar"]) + ", borrar/reemplazar " + str(len(conteo["borrar"])))
        if conteo["borrar"] or "--revisar" in sys.argv:
            for b in conteo["borrar"]:
                salida("   se borra: " + b)
            respuesta = input("escribe si para aplicar: ").strip().lower()
            anotar("respuesta a la confirmacion: " + respuesta)
            if respuesta != "si":
                fallar("no se aplico nada")
        terraform("apply", "-input=false", os.path.basename(plan))
    finally:
        if os.path.exists(plan):
            os.remove(plan)
    s = salidas()
    sembrar(s)
    info("listo: " + s["url"] + "  (apagado automatico de tareas: " + s["apagado_utc"] + " utc)")
    info("siguiente: python tareas.py probar")


def cliente(servicio):
    return botocore.session.get_session().create_client(servicio, region_name=parametros()["region"])


def vaciar_bucket(s3, nombre):
    try:
        pag = s3.get_paginator("list_objects_v2")
        total = 0
        for pagina in pag.paginate(Bucket=nombre):
            objetos = [{"Key": o["Key"]} for o in pagina.get("Contents", [])]
            if objetos:
                s3.delete_objects(Bucket=nombre, Delete={"Objects": objetos, "Quiet": True})
                total += len(objetos)
        info("bucket " + nombre + " vaciado (" + str(total) + " objetos)")
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchBucket", "404"):
            return False
        raise


def preparar_destruccion(cuenta, prefijo):
    #cloudformation no borra un bucket con objetos: se vacia antes
    s3 = cliente("s3")
    nombre = prefijo + "fotos-" + cuenta
    vaciar_bucket(s3, nombre)
    #compatibilidad: versiones anteriores crearon el bucket con aws_s3_bucket, que falla al refrescar en el lab
    estado = os.path.join(DIR_TF, "terraform.tfstate")
    if not os.path.exists(estado):
        return
    with open(estado) as f:
        viejos = [
            r["type"] + "." + r["name"]
            for r in json.load(f).get("resources", [])
            if r.get("mode") == "managed" and r["type"].startswith("aws_s3_bucket")
        ]
    if viejos:
        info("se quitan del estado recursos s3 de la version anterior: " + ", ".join(viejos))
        terraform("state", "rm", *viejos)
        try:
            s3.delete_bucket(Bucket=nombre)
            info("bucket " + nombre + " borrado")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "NoSuchBucket":
                raise


def motivo(e):
    if isinstance(e, ClientError):
        err = e.response.get("Error", {})
        return (err.get("Code", "") + ": " + err.get("Message", ""))[:200]
    return str(e)[:200]


def no_existe(e):
    if not isinstance(e, ClientError):
        return False
    codigo = e.response.get("Error", {}).get("Code", "")
    return any(x in codigo for x in ("NotFound", "NotExist", "NoSuch", "NonExistent"))


def paginar(cl, operacion, clave, **kw):
    if cl.can_paginate(operacion):
        datos = []
        for pagina in cl.get_paginator(operacion).paginate(**kw):
            datos += pagina.get(clave, [])
        return datos
    return getattr(cl, operacion)(**kw).get(clave, [])


def inventario(prefijo):
    #solo lectura: todo lo que empiece con el prefijo, consultando la api de cada servicio (decisiones 22, 35, 37)
    hallados = []
    no_verificados = []

    def agregar(tipo, ident, **extra):
        hallados.append(dict(tipo=tipo, id=ident, **extra))

    def buscar(servicio, fn):
        try:
            fn()
        except (ClientError, BotoCoreError) as e:
            no_verificados.append(servicio + ": " + motivo(e))

    def f_scheduler():
        sc = cliente("scheduler")
        for x in paginar(sc, "list_schedules", "Schedules", NamePrefix=prefijo):
            agregar("scheduler schedule", x["Name"], grupo=x["GroupName"])
        for g in paginar(sc, "list_schedule_groups", "ScheduleGroups", NamePrefix=prefijo):
            agregar("scheduler grupo", g["Name"])

    def f_autoscaling():
        aa = cliente("application-autoscaling")
        for t in paginar(aa, "describe_scalable_targets", "ScalableTargets", ServiceNamespace="ecs"):
            if t["ResourceId"].startswith("service/" + prefijo):
                agregar("autoscaling ecs", t["ResourceId"], dimension=t["ScalableDimension"])

    def f_ecs():
        ecs = cliente("ecs")
        nombres = [a.rsplit("/", 1)[-1] for a in paginar(ecs, "list_clusters", "clusterArns")]
        nombres = [n for n in nombres if n.startswith(prefijo)]
        if nombres:
            for c in ecs.describe_clusters(clusters=nombres)["clusters"]:
                if c["status"] == "ACTIVE":
                    agregar("ecs cluster", c["clusterName"])
                    for sv in paginar(ecs, "list_services", "serviceArns", cluster=c["clusterName"]):
                        agregar("ecs servicio", sv.rsplit("/", 1)[-1], cluster=c["clusterName"])
        #familyPrefix de list_task_definitions es la familia exacta: primero se listan las familias
        for familia in paginar(ecs, "list_task_definition_families", "families", familyPrefix=prefijo, status="ALL"):
            if not familia.startswith(prefijo):
                continue
            for estado in ("ACTIVE", "INACTIVE"):
                for td in paginar(ecs, "list_task_definitions", "taskDefinitionArns", familyPrefix=familia, status=estado):
                    agregar("ecs task definition " + estado.lower(), td.rsplit("/", 1)[-1], arn=td)

    def f_elb():
        elb = cliente("elbv2")
        for lb in paginar(elb, "describe_load_balancers", "LoadBalancers"):
            if lb["LoadBalancerName"].startswith(prefijo):
                agregar("alb", lb["LoadBalancerName"], arn=lb["LoadBalancerArn"])
        for tg in paginar(elb, "describe_target_groups", "TargetGroups"):
            if tg["TargetGroupName"].startswith(prefijo):
                agregar("target group", tg["TargetGroupName"], arn=tg["TargetGroupArn"])

    def f_lambda():
        lam = cliente("lambda")
        for fn in paginar(lam, "list_functions", "Functions"):
            if fn["FunctionName"].startswith(prefijo):
                agregar("lambda", fn["FunctionName"])
                for m in paginar(lam, "list_event_source_mappings", "EventSourceMappings", FunctionName=fn["FunctionName"]):
                    agregar("lambda mapeo", m["UUID"], funcion=fn["FunctionName"])

    def f_cfn():
        cfn = cliente("cloudformation")
        for st in paginar(cfn, "list_stacks", "StackSummaries"):
            if st["StackName"].startswith(prefijo) and st["StackStatus"] != "DELETE_COMPLETE":
                agregar("cloudformation stack", st["StackName"], estado=st["StackStatus"])

    def f_s3():
        for b in cliente("s3").list_buckets().get("Buckets", []):
            if b["Name"].startswith(prefijo):
                agregar("s3 bucket", b["Name"])

    def f_sqs():
        for url in paginar(cliente("sqs"), "list_queues", "QueueUrls", QueueNamePrefix=prefijo):
            agregar("sqs cola", url.rsplit("/", 1)[-1], url=url)

    def f_dynamodb():
        for t in paginar(cliente("dynamodb"), "list_tables", "TableNames"):
            if t.startswith(prefijo):
                agregar("dynamodb tabla", t)

    def f_cognito():
        for up in paginar(cliente("cognito-idp"), "list_user_pools", "UserPools", MaxResults=60):
            if up["Name"].startswith(prefijo):
                agregar("cognito pool", up["Name"], pool_id=up["Id"])

    def f_ecr():
        for r in paginar(cliente("ecr"), "describe_repositories", "repositories"):
            if r["repositoryName"].startswith(prefijo):
                agregar("ecr repositorio", r["repositoryName"])

    def f_logs():
        logs = cliente("logs")
        for base in ("/ecs/" + prefijo, "/aws/lambda/" + prefijo):
            for g in paginar(logs, "describe_log_groups", "logGroups", logGroupNamePrefix=base):
                agregar("log group", g["logGroupName"])

    def f_ec2():
        ec2 = cliente("ec2")
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": [prefijo + "*"]}])["Vpcs"]
        ids = [v["VpcId"] for v in vpcs]
        for v in vpcs:
            agregar("vpc", v["VpcId"], nombre=[t["Value"] for t in v.get("Tags", []) if t["Key"] == "Name"][0])
        for g in ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [prefijo + "*"]}])["SecurityGroups"]:
            agregar("security group", g["GroupId"], nombre=g["GroupName"], vpc=g["VpcId"], en_vpc_propia=g["VpcId"] in ids)

    def f_ssm():
        for prm in paginar(cliente("ssm"), "get_parameters_by_path", "Parameters", Path="/" + prefijo, Recursive=True):
            agregar("ssm parametro", prm["Name"])

    for servicio, fn in (
        ("scheduler", f_scheduler), ("autoscaling", f_autoscaling), ("ecs", f_ecs), ("elb", f_elb),
        ("lambda", f_lambda), ("cloudformation", f_cfn), ("s3", f_s3), ("sqs", f_sqs), ("dynamodb", f_dynamodb),
        ("cognito", f_cognito), ("ecr", f_ecr), ("logs", f_logs), ("ec2", f_ec2), ("ssm", f_ssm),
    ):
        buscar(servicio, fn)
    return hallados, no_verificados


def mostrar_inventario(hallados):
    for h in hallados:
        extra = h.get("nombre") or h.get("cluster") or h.get("grupo") or h.get("funcion") or h.get("estado") or ""
        salida("   " + h["tipo"].ljust(30) + " " + h["id"] + ("  (" + str(extra) + ")" if extra else ""))


def verificar_sobrantes(prefijo, intentos=3):
    #algunas apis tardan en reflejar lo borrado: se reintenta antes de declarar sobrantes
    for i in range(intentos):
        hallados, no_verificados = inventario(prefijo)
        if not hallados and not no_verificados:
            info("VERIFICADO por la api de cada servicio: 0 recursos con prefijo " + prefijo)
            return 0
        if i + 1 < intentos:
            info("quedan " + str(len(hallados)) + " recursos o servicios sin verificar; reintento en 30 s (consistencia eventual)")
            time.sleep(30)
    if hallados:
        info("SOBRANTES con prefijo " + prefijo + ":")
        mostrar_inventario(hallados)
    for nv in no_verificados:
        info("NO VERIFICADO " + nv)
    return len(hallados) + len(no_verificados)


def borrar_task_definitions(prefijo):
    #terraform solo las da de baja (quedan INACTIVE); aqui se borran de verdad (respuesta 2a del 9.3)
    ecs = cliente("ecs")
    hallados, _ = inventario_solo_ecs(prefijo)
    activas = [h["arn"] for h in hallados if h["tipo"] == "ecs task definition active"]
    for arn in activas:
        try:
            ecs.deregister_task_definition(taskDefinition=arn)
        except ClientError as e:
            info("no se pudo dar de baja " + arn + ": " + motivo(e))
    todas = activas + [h["arn"] for h in hallados if h["tipo"] == "ecs task definition inactive"]
    for i in range(0, len(todas), 10):
        try:
            ecs.delete_task_definitions(taskDefinitions=todas[i:i + 10])
        except ClientError as e:
            info("no se pudieron borrar task definitions: " + motivo(e))
    if todas:
        info("task definitions borradas: " + str(len(todas)))


def inventario_solo_ecs(prefijo):
    ecs = cliente("ecs")
    hallados = []
    for familia in paginar(ecs, "list_task_definition_families", "families", familyPrefix=prefijo, status="ALL"):
        if not familia.startswith(prefijo):
            continue
        for estado in ("ACTIVE", "INACTIVE"):
            for td in paginar(ecs, "list_task_definitions", "taskDefinitionArns", familyPrefix=familia, status=estado):
                hallados.append({"tipo": "ecs task definition " + estado.lower(), "id": td.rsplit("/", 1)[-1], "arn": td})
    return hallados, []


def leer_registro(prefijo):
    try:
        valor = cliente("ssm").get_parameter(Name="/" + prefijo + "/registro")["Parameter"]["Value"]
        return json.loads(valor)
    except ClientError as e:
        if no_existe(e):
            return None
        raise


def borrar_red(ec2, vpc, quitar):
    filtro = [{"Name": "vpc-id", "Values": [vpc]}]
    #las interfaces del alb y de fargate tardan en soltarse
    for _ in range(36):
        enis = ec2.describe_network_interfaces(Filters=filtro)["NetworkInterfaces"]
        if not enis:
            break
        for e in enis:
            if e["Status"] == "available":
                quitar("interfaz de red " + e["NetworkInterfaceId"], lambda e=e: ec2.delete_network_interface(NetworkInterfaceId=e["NetworkInterfaceId"]))
        time.sleep(10)
    grupos = [g for g in ec2.describe_security_groups(Filters=filtro)["SecurityGroups"] if g["GroupName"] != "default"]
    #los grupos se referencian entre si (alb <-> tareas): primero se quitan las reglas
    for g in grupos:
        if g.get("IpPermissions"):
            quitar("reglas de entrada " + g["GroupName"], lambda g=g: ec2.revoke_security_group_ingress(GroupId=g["GroupId"], IpPermissions=g["IpPermissions"]))
        if g.get("IpPermissionsEgress"):
            quitar("reglas de salida " + g["GroupName"], lambda g=g: ec2.revoke_security_group_egress(GroupId=g["GroupId"], IpPermissions=g["IpPermissionsEgress"]))
    for g in grupos:
        quitar("security group " + g["GroupName"], lambda g=g: ec2.delete_security_group(GroupId=g["GroupId"]), veces=36, espera=10)
    for rt in ec2.describe_route_tables(Filters=filtro)["RouteTables"]:
        if any(a.get("Main") for a in rt["Associations"]):
            continue
        for a in rt["Associations"]:
            quitar("asociacion de rutas", lambda a=a: ec2.disassociate_route_table(AssociationId=a["RouteTableAssociationId"]))
        quitar("tabla de rutas " + rt["RouteTableId"], lambda rt=rt: ec2.delete_route_table(RouteTableId=rt["RouteTableId"]))
    for igw in ec2.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [vpc]}])["InternetGateways"]:
        i = igw["InternetGatewayId"]
        quitar("internet gateway (separar) " + i, lambda i=i: ec2.detach_internet_gateway(InternetGatewayId=i, VpcId=vpc), veces=24, espera=10)
        quitar("internet gateway " + i, lambda i=i: ec2.delete_internet_gateway(InternetGatewayId=i))
    for sn in ec2.describe_subnets(Filters=filtro)["Subnets"]:
        quitar("subred " + sn["SubnetId"], lambda sn=sn: ec2.delete_subnet(SubnetId=sn["SubnetId"]), veces=12, espera=10)
    quitar("vpc " + vpc, lambda: ec2.delete_vpc(VpcId=vpc), veces=12, espera=10)


def borrar_por_prefijo(prefijo, cuenta, hallados, registro):
    fallas = []

    def quitar(titulo, fn, veces=1, espera=5):
        ultimo = ""
        for _ in range(veces):
            try:
                fn()
                info("borrado: " + titulo)
                return True
            except (ClientError, BotoCoreError) as e:
                if no_existe(e):
                    return True
                ultimo = motivo(e)
                time.sleep(espera)
        fallas.append(titulo + " :: " + ultimo)
        info("FALLA al borrar " + titulo + " :: " + ultimo)
        return False

    def esperar(titulo, fn):
        try:
            fn()
        except (ClientError, BotoCoreError) as e:
            info("AVISO esperando " + titulo + ": " + motivo(e))

    def de(tipo):
        return [h for h in hallados if h["tipo"] == tipo]

    sc = cliente("scheduler")
    for h in de("scheduler schedule"):
        quitar("schedule " + h["id"], lambda h=h: sc.delete_schedule(Name=h["id"], GroupName=h["grupo"]))
    for h in de("scheduler grupo"):
        quitar("grupo de schedules " + h["id"], lambda h=h: sc.delete_schedule_group(Name=h["id"]))
    aa = cliente("application-autoscaling")
    for h in de("autoscaling ecs"):
        quitar("autoscaling " + h["id"], lambda h=h: aa.deregister_scalable_target(ServiceNamespace="ecs", ResourceId=h["id"], ScalableDimension=h["dimension"]))

    ecs = cliente("ecs")
    servicios = de("ecs servicio")
    for h in servicios:
        quitar("servicio ecs " + h["id"], lambda h=h: ecs.delete_service(cluster=h["cluster"], service=h["id"], force=True))
    for c in sorted(set(h["cluster"] for h in servicios)):
        nombres = [h["id"] for h in servicios if h["cluster"] == c]
        info("esperando que los servicios de " + c + " terminen (puede tardar 2 a 4 min)")
        esperar("servicios", lambda: ecs.get_waiter("services_inactive").wait(cluster=c, services=nombres, WaiterConfig={"Delay": 10, "MaxAttempts": 40}))
    for h in de("ecs cluster"):
        tareas = paginar(ecs, "list_tasks", "taskArns", cluster=h["id"])
        for t in tareas:
            quitar("tarea ecs " + t.rsplit("/", 1)[-1], lambda t=t: ecs.stop_task(cluster=h["id"], task=t))
        if tareas:
            esperar("tareas", lambda: ecs.get_waiter("tasks_stopped").wait(cluster=h["id"], tasks=tareas[:100], WaiterConfig={"Delay": 6, "MaxAttempts": 50}))
        quitar("cluster ecs " + h["id"], lambda h=h: ecs.delete_cluster(cluster=h["id"]), veces=12, espera=10)
    borrar_task_definitions(prefijo)

    elb = cliente("elbv2")
    lbs = de("alb")
    for h in lbs:
        quitar("alb " + h["id"], lambda h=h: elb.delete_load_balancer(LoadBalancerArn=h["arn"]))
    if lbs:
        esperar("alb", lambda: elb.get_waiter("load_balancers_deleted").wait(LoadBalancerArns=[h["arn"] for h in lbs], WaiterConfig={"Delay": 10, "MaxAttempts": 40}))
    for h in de("target group"):
        quitar("target group " + h["id"], lambda h=h: elb.delete_target_group(TargetGroupArn=h["arn"]), veces=12, espera=10)

    lam = cliente("lambda")
    uuids = [h["id"] for h in de("lambda mapeo")] + list((registro or {}).get("mapeos_lambda", []))
    for u in sorted(set(uuids)):
        quitar("mapeo sqs->lambda " + u, lambda u=u: lam.delete_event_source_mapping(UUID=u))
    for h in de("lambda"):
        quitar("lambda " + h["id"], lambda h=h: lam.delete_function(FunctionName=h["id"]))

    #cloudformation no borra buckets con objetos: se vacian antes
    s3 = cliente("s3")
    for h in de("s3 bucket"):
        vaciar_bucket(s3, h["id"])
    cfn = cliente("cloudformation")
    for h in de("cloudformation stack"):
        quitar("stack " + h["id"], lambda h=h: cfn.delete_stack(StackName=h["id"]))
        esperar("stack " + h["id"], lambda h=h: cfn.get_waiter("stack_delete_complete").wait(StackName=h["id"], WaiterConfig={"Delay": 10, "MaxAttempts": 60}))
    for h in de("s3 bucket"):
        quitar("bucket " + h["id"], lambda h=h: s3.delete_bucket(Bucket=h["id"]))

    sqs = cliente("sqs")
    for h in de("sqs cola"):
        quitar("cola " + h["id"], lambda h=h: sqs.delete_queue(QueueUrl=h["url"]))
    ddb = cliente("dynamodb")
    for h in de("dynamodb tabla"):
        quitar("tabla " + h["id"], lambda h=h: ddb.delete_table(TableName=h["id"]))
    cog = cliente("cognito-idp")
    for h in de("cognito pool"):
        quitar("pool de cognito " + h["id"], lambda h=h: cog.delete_user_pool(UserPoolId=h["pool_id"]))
    ecr = cliente("ecr")
    for h in de("ecr repositorio"):
        quitar("repositorio ecr " + h["id"], lambda h=h: ecr.delete_repository(repositoryName=h["id"], force=True))
    logs = cliente("logs")
    for h in de("log group"):
        quitar("log group " + h["id"], lambda h=h: logs.delete_log_group(logGroupName=h["id"]))

    ec2 = cliente("ec2")
    for h in de("vpc"):
        info("borrando la red " + h["id"] + " (espera a que se suelten las interfaces, hasta 6 min)")
        borrar_red(ec2, h["id"], quitar)
    for h in de("security group"):
        if not h["en_vpc_propia"]:
            quitar("security group " + h["nombre"], lambda h=h: ec2.delete_security_group(GroupId=h["id"]), veces=12, espera=10)

    ssm = cliente("ssm")
    for h in de("ssm parametro"):
        quitar("parametro " + h["id"], lambda h=h: ssm.delete_parameter(Name=h["id"]))
    return fallas


def archivar_estado_local(cuenta, motivo_archivo):
    estado = os.path.join(DIR_TF, "terraform.tfstate")
    if not os.path.exists(estado):
        return
    with open(estado) as f:
        recursos = [r for r in json.load(f).get("resources", []) if r.get("mode") == "managed"]
    if not recursos:
        return
    marca = time.strftime("%Y%m%d-%H%M%S")
    for nombre in ("terraform.tfstate", "terraform.tfstate.backup"):
        origen = os.path.join(DIR_TF, nombre)
        if os.path.exists(origen):
            os.replace(origen, os.path.join(DIR_TF, "estado-anterior-" + cuenta + "-" + marca + "-" + motivo_archivo + "-" + nombre))
    info("el estado local ya no coincide con la cuenta: archivado como estado-anterior-" + cuenta + "-" + marca + "-*")


def destruir_por_prefijo(cuenta, prefijo):
    #modo de rescate: no usa el estado de terraform, selecciona solo por prefijo (decision 37)
    region = parametros()["region"]
    registro = leer_registro(prefijo)
    if registro:
        if registro.get("cuenta") != cuenta or registro.get("region") != region:
            fallar("el registro /" + prefijo + "/registro es de otra cuenta o region (" + str(registro.get("cuenta")) + ", " + str(registro.get("region")) + "); no se borra nada")
        info("registro encontrado: cuenta y region coinciden")
    else:
        info("AVISO: no existe /" + prefijo + "/registro; se busca solo por nombre")
    hallados, no_verificados = inventario(prefijo)
    for nv in no_verificados:
        info("NO VERIFICADO " + nv)
    if not hallados:
        info("no hay recursos con prefijo " + prefijo + " en la cuenta " + cuenta)
        archivar_estado_local(cuenta, "por-prefijo")
        return
    salida("vista previa: se borraran " + str(len(hallados)) + " recursos con prefijo " + prefijo + " en la cuenta " + cuenta + ":")
    mostrar_inventario(hallados)
    salida("ATENCION: se borra todo lo que empiece con " + prefijo + " aunque no lo haya creado este proyecto")
    confirmado = input("escribe el prefijo (" + prefijo + ") para confirmar: ").strip()
    anotar("respuesta a la confirmacion: " + confirmado)
    if confirmado != prefijo:
        fallar("confirmacion incorrecta; no se borro nada")
    fallas = borrar_por_prefijo(prefijo, cuenta, hallados, registro)
    archivar_estado_local(cuenta, "por-prefijo")
    if fallas:
        info(str(len(fallas)) + " borrados fallaron (detalle arriba)")


def accion_destruir():
    cuenta = cuenta_actual()
    prefijo = parametros()["prefijo"]
    if "--por-prefijo" in sys.argv:
        destruir_por_prefijo(cuenta, prefijo)
    else:
        salida("se destruira TODO lo de agrocredit con prefijo " + prefijo + " en la cuenta " + cuenta)
        confirmado = input("escribe el prefijo (" + prefijo + ") para confirmar: ").strip()
        anotar("respuesta a la confirmacion: " + confirmado)
        if confirmado != prefijo:
            fallar("confirmacion incorrecta; no se borro nada")
        preparar_destruccion(cuenta, prefijo)
        terraform("destroy", "-auto-approve", "-input=false", *variables_tf(cuenta))
        borrar_task_definitions(prefijo)
    info("verificando sobrantes con la api de cada servicio")
    if verificar_sobrantes(prefijo):
        fallar("la cuenta no quedo limpia (ver lista). si el estado de terraform se perdio: python tareas.py destruir --por-prefijo")
    info("cuenta limpia de recursos " + prefijo)
    if os.path.exists(TOKEN_DEMO):
        os.remove(TOKEN_DEMO)


def salidas():
    datos = terraform_json("output", "-json")
    if "alb_dns" not in datos:
        fallar("no hay despliegue con alb: ejecuta python tareas.py desplegar")
    return {k: v["value"] for k, v in datos.items()}


def pedir(url, intentos=1):
    #devuelve (codigo, json o None); codigo 0 si no hubo respuesta
    for i in range(intentos):
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                cuerpo = r.read()
                try:
                    return r.status, json.loads(cuerpo)
                except ValueError:
                    return r.status, None
        except urllib.error.HTTPError as e:
            return e.code, None
        except (urllib.error.URLError, OSError):
            if i + 1 < intentos:
                time.sleep(5)
    return 0, None


def accion_probar():
    cuenta_actual()
    base = "http://" + salidas()["alb_dns"]
    fallas = 0
    #espera hasta 3 min: dns recien creado o tareas recien encendidas (el alb da 503 sin tareas sanas)
    limite = time.time() + 180
    codigo, _ = pedir(base + "/api/v1/salud", intentos=24)
    while codigo != 200 and time.time() < limite:
        info("esperando que el servicio responda (http " + str(codigo) + ")")
        time.sleep(10)
        codigo, _ = pedir(base + "/api/v1/salud")
    if codigo == 0:
        fallar("el alb no responde (el dns puede tardar unos minutos en propagarse): " + base)
    time.sleep(5)
    for ruta in ("/salud-web", "/api/v1/salud"):
        vistas = {}
        for _ in range(10):
            codigo, cuerpo = pedir(base + ruta)
            if codigo == 200 and cuerpo:
                vistas[cuerpo.get("tareaId")] = vistas.get(cuerpo.get("tareaId"), 0) + 1
            else:
                fallas += 1
        estado = "OK" if len(vistas) >= 2 else "FALLA"
        if estado == "FALLA":
            fallas += 1
        info(estado + " " + ruta + ": respondieron " + str(len(vistas)) + " tareas distintas " + str(vistas))
    for ruta in ("/", "/onboarding/00-inicio.html", "/design-system/styles/base.css", "/api/docs", "/demo/resiliencia.html"):
        codigo, _ = pedir(base + ruta)
        info(("OK" if codigo == 200 else "FALLA") + " " + ruta + ": http " + str(codigo) + (" (403 = permisos de archivos en la imagen)" if codigo == 403 else ""))
        fallas += codigo != 200
    codigo, cuerpo = pedir(base + "/api/v1/config")
    ok = codigo == 200 and cuerpo and all(cuerpo.get(k) for k in ("region", "userPoolId", "clientId"))
    info(("OK" if ok else "FALLA") + " /api/v1/config: " + str(cuerpo))
    fallas += not ok
    if fallas:
        fallar(str(fallas) + " verificaciones fallaron")
    info("web: " + base + "/onboarding/00-inicio.html")
    info("estado del servicio: " + base + "/demo/resiliencia.html")
    info("todo OK")
    info("demo de resiliencia: python tareas.py caida api  (o caida api --brusca)")


def accion_caida():
    #detiene una tarea a proposito y muestra que el alb sigue respondiendo con la otra
    #ecs saca la tarea del balanceador antes de detenerla y luego lanza un reemplazo
    argumentos = [a for a in sys.argv[2:] if not a.startswith("--")]
    servicio = argumentos[0] if argumentos else "api"
    brusca = "--brusca" in sys.argv
    if servicio not in IMAGENES:
        fallar("uso: python tareas.py caida [api|web] [--brusca]")
    if brusca and servicio != "api":
        fallar("la caida brusca solo existe para la api (la web es nginx sin endpoint de demo)")
    cuenta_actual()
    s = salidas()
    url = "http://" + s["alb_dns"] + ("/api/v1/salud" if servicio == "api" else "/salud-web")
    ecs = cliente("ecs")
    nombre = s["servicios"][servicio]
    tareas = ecs.list_tasks(cluster=s["cluster"], serviceName=nombre, desiredStatus="RUNNING")["taskArns"]
    if len(tareas) < 2:
        fallar("hay " + str(len(tareas)) + " tarea(s) corriendo; se necesitan 2 (si se apagaron: python tareas.py encender)")
    iniciales = set()
    for _ in range(10):
        codigo, cuerpo = pedir(url)
        if codigo == 200 and cuerpo:
            iniciales.add(cuerpo.get("tareaId"))
    info("antes de la caida responden: " + ", ".join(sorted(iniciales)))
    if brusca:
        #el proceso muere sin avisar: el alb lo descubre por fallas y chequeos de salud
        token = token_demo()
        if not token:
            fallar("no hay token de demo: vuelve a ejecutar python tareas.py desplegar")
        pedido = urllib.request.Request("http://" + s["alb_dns"] + "/api/v1/demo/caer", method="POST", headers={"X-Demo-Token": token})
        try:
            with urllib.request.urlopen(pedido, timeout=5) as r:
                muerta = json.loads(r.read()).get("tareaId", "?")
        except urllib.error.HTTPError as e:
            fallar("el endpoint de caida respondio http " + str(e.code) + (" (token distinto: vuelve a desplegar)" if e.code == 403 else ""))
        info("CAIDA BRUSCA: el proceso de la tarea " + muerta + " termina sin apagado ordenado")
    else:
        victima = tareas[0]
        detalle = ecs.describe_tasks(cluster=s["cluster"], tasks=[victima])["tasks"][0]
        zona = detalle.get("availabilityZone", "?")
        info("CAIDA ORDENADA: deteniendo la tarea " + victima.rsplit("/", 1)[-1] + " (zona " + zona + ")")
        ecs.stop_task(cluster=s["cluster"], task=victima, reason="demo de resiliencia agrocredit")
    inicio = time.time()
    total = errores = 0
    nueva = None
    while time.time() - inicio < 240:
        codigo, cuerpo = pedir(url)
        total += 1
        tarea = cuerpo.get("tareaId") if (codigo == 200 and cuerpo) else "-"
        if codigo != 200:
            errores += 1
        if tarea not in iniciales and tarea != "-" and not nueva:
            nueva = (tarea, int(time.time() - inicio))
        salida("   t+%3ds  http %s  tarea %s" % (int(time.time() - inicio), codigo or "sin respuesta", tarea))
        if nueva and time.time() - inicio > nueva[1] + 5:
            break
        time.sleep(1)
    salida("")
    info("peticiones: " + str(total) + ", fallidas: " + str(errores))
    if nueva:
        info("ecs lanzo el reemplazo " + nueva[0] + " y el alb lo uso a los " + str(nueva[1]) + " s")
    else:
        info("el reemplazo aun no recibe trafico (revisa en unos minutos con python tareas.py probar)")
    if errores == 0:
        info("resultado: RESILIENTE, el servicio nunca dejo de responder")
    else:
        info("resultado: " + str(errores) + " de " + str(total) + " respuestas fallidas mientras el alb detectaba la caida; luego el servicio siguio con la otra tarea")


def leer_item(ddb, tabla, pk, sk):
    r = ddb.get_item(TableName=tabla, Key={"PK": {"S": pk}, "SK": {"S": sk}}, ConsistentRead=True)
    return r.get("Item")


def esperar_item(ddb, tabla, pk, sk, condicion, segundos=90):
    inicio = time.time()
    while time.time() - inicio < segundos:
        item = leer_item(ddb, tabla, pk, sk)
        if item and condicion(item):
            return item, int(time.time() - inicio)
        time.sleep(2)
    return None, segundos


def esperar_indice(ddb, tabla, indice, atributo, valor, atributo_orden, orden, segundos=30):
    #los indices globales son eventualmente consistentes: se consulta hasta que aparece el item
    inicio = time.time()
    while time.time() - inicio < segundos:
        r = ddb.query(TableName=tabla, IndexName=indice, KeyConditionExpression="#a = :v",
                      ExpressionAttributeNames={"#a": atributo}, ExpressionAttributeValues={":v": {"S": valor}})
        ordenes = {i.get(atributo_orden, {}).get("S") for i in r.get("Items", [])}
        if orden in ordenes:
            return True, round(time.time() - inicio)
        time.sleep(1)
    return False, segundos


def accion_flujo():
    #prueba el camino asincrono en aws sin la web: cola -> worker -> dynamodb y foto -> s3 -> etiquetar -> rekognition
    #usa un usuario ficticio prueba-flujo y borra todo lo que crea al terminar
    cuenta_actual()
    s = salidas()
    tabla, cola, bucket = s["tabla"], s["colas"]["insercion"], s["bucket_fotos"]
    ddb, sqs, s3 = cliente("dynamodb"), cliente("sqs"), cliente("s3")
    sub, cid, oid, fid = "prueba-flujo", str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    ahora = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    campana = {"PK": "CAMP#" + cid, "SK": "META", "entidad": "CAMPANA", "campaniaId": cid, "propietarioSub": sub,
               "productorNombre": "Prueba de flujo", "cultivo": "papa", "departamento": "Prueba", "provincia": "Prueba",
               "distrito": "Prueba", "cosecha": "2099-01-01", "volumenKg": 100, "logistica": "Recojo", "capitalCentimos": 100,
               "precioAhoraCentimosPorKg": 100, "precioContraentregaCentimosPorKg": 100, "referenciaMercadoCentimosPorKg": 100,
               "estado": "PUBLICADA", "numeroOfertas": 0, "creadoEn": ahora, "publicadaEn": ahora,
               "usuarioClave": "USER#" + sub, "usuarioOrden": "CAMP#" + ahora + "#" + cid,
               "publicadaClave": "PUB#papa#Prueba", "publicadaOrden": "2099-01-01#" + cid}
    oferta = {"PK": "CAMP#" + cid, "SK": "OFFER#" + oid, "entidad": "OFERTA", "ofertaId": oid, "campaniaId": cid,
              "compradorSub": sub + "-comprador", "compradorNombre": "Prueba SAC", "volumenKg": 10, "precioCentimosPorKg": 100,
              "modalidad": "Pago ahora", "logistica": "Recojo", "fechaEntrega": "2099-01-01", "totalCentimos": 1000,
              "estado": "PENDIENTE", "creadoEn": ahora,
              "usuarioClave": "USER#" + sub + "-comprador", "usuarioOrden": "OFFER#" + ahora + "#" + oid}
    fallas = 0
    final_foto = None
    try:
        info("1/4 campana por la cola (como la api)")
        sqs.send_message(QueueUrl=cola, MessageBody=json.dumps({"tipo": "campana", "item": campana}))
        item, t = esperar_item(ddb, tabla, "CAMP#" + cid, "META", lambda i: True)
        info(("OK campana registrada por el worker en " + str(t) + " s") if item else "FALLA la campana no aparecio en 90 s")
        fallas += item is None
        if item:
            info("2/4 oferta por la cola, dos veces (debe contarse una sola)")
            for _ in range(2):
                sqs.send_message(QueueUrl=cola, MessageBody=json.dumps({"tipo": "oferta", "item": oferta}))
            item, t = esperar_item(ddb, tabla, "CAMP#" + cid, "META", lambda i: i.get("numeroOfertas", {}).get("N") == "1")
            time.sleep(5)
            item = leer_item(ddb, tabla, "CAMP#" + cid, "META")
            n = item.get("numeroOfertas", {}).get("N") if item else "?"
            info(("OK" if n == "1" else "FALLA") + " numeroOfertas = " + str(n) + " tras enviar la misma oferta dos veces")
            fallas += n != "1"
            info("3/4 indices por-usuario y publicadas-por-cultivo (decision 58)")
            consultas = [("por-usuario", "usuarioClave", "USER#" + sub, "usuarioOrden", "CAMP#" + ahora + "#" + cid, "campana del agricultor"),
                         ("publicadas-por-cultivo", "publicadaClave", "PUB#papa#Prueba", "publicadaOrden", "2099-01-01#" + cid, "campana publicada"),
                         ("por-usuario", "usuarioClave", "USER#" + sub + "-comprador", "usuarioOrden", "OFFER#" + ahora + "#" + oid, "oferta del comprador")]
            for indice, atributo, valor, atributo_orden, orden, que in consultas:
                ok, t = esperar_indice(ddb, tabla, indice, atributo, valor, atributo_orden, orden)
                info(("OK " + que + " visible en " + indice + " en " + str(t) + " s") if ok else ("FALLA " + que + " no aparecio en " + indice))
                fallas += not ok
        info("4/4 foto de prueba (papa) subida a entrada/ como lo haria el navegador")
        with open(os.path.join(CONEXION, "foto-prueba.jpg"), "rb") as f:
            s3.put_object(Bucket=bucket, Key="entrada/" + sub + "/" + cid + "/" + fid + ".jpg", Body=f.read(), ContentType="image/jpeg")
        foto, t = esperar_item(ddb, tabla, "CAMP#" + cid, "FOTO#" + fid, lambda i: True, segundos=120)
        if foto:
            final_foto = foto.get("s3Key", {}).get("S")
            label = foto.get("label", {}).get("S")
            estado = foto.get("estado", {}).get("S")
            info(("OK" if label == "papa" else "FALLA") + " foto " + str(estado) + " como '" + str(label) + "' (" +
                 foto.get("labelConfianza", {}).get("N", "?") + "%) en " + str(t) + " s -> " + str(final_foto))
            fallas += label != "papa"
        else:
            info("FALLA la foto no se proceso en 120 s (revisa /aws/lambda/" + parametros()["prefijo"] + "etiquetar)")
            fallas += 1
    finally:
        for sk in ("META", "OFFER#" + oid, "FOTO#" + fid):
            ddb.delete_item(TableName=tabla, Key={"PK": {"S": "CAMP#" + cid}, "SK": {"S": sk}})
        for clave in [final_foto, "entrada/" + sub + "/" + cid + "/" + fid + ".jpg"]:
            if clave:
                s3.delete_object(Bucket=bucket, Key=clave)
        info("datos de prueba borrados")
    if fallas:
        fallar(str(fallas) + " verificaciones del flujo fallaron")
    info("flujo asincrono OK: worker, contador de ofertas y etiquetado con rekognition")


def reprogramar_apagado(horas):
    salidas()
    sched = cliente("scheduler")
    cuando = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() + horas * 3600))
    for servicio in IMAGENES:
        nombre = parametros()["prefijo"] + "apagar-" + servicio
        grupo = parametros()["prefijo"] + "apagado"
        actual = sched.get_schedule(Name=nombre, GroupName=grupo)
        sched.update_schedule(
            Name=nombre,
            GroupName=grupo,
            ScheduleExpression="at(" + cuando + ")",
            ScheduleExpressionTimezone="UTC",
            FlexibleTimeWindow=actual["FlexibleTimeWindow"],
            Target=actual["Target"],
            State="ENABLED",
            ActionAfterCompletion=actual.get("ActionAfterCompletion", "NONE"),
        )
    return cuando


def cambiar_tareas(cantidad):
    s = salidas()
    ecs = cliente("ecs")
    for servicio, nombre in s["servicios"].items():
        ecs.update_service(cluster=s["cluster"], service=nombre, desiredCount=cantidad)
        info("servicio " + nombre + " -> " + str(cantidad) + " tareas")
    #se espera a que ecs termine: asi apagar/encender seguidos no dejan estados intermedios
    info("esperando que los servicios queden estables (1 a 3 min)")
    inicio = time.time()
    try:
        ecs.get_waiter("services_stable").wait(cluster=s["cluster"], services=list(s["servicios"].values()), WaiterConfig={"Delay": 10, "MaxAttempts": 36})
    except (ClientError, BotoCoreError) as e:
        fallar("los servicios no quedaron estables en 6 min: " + motivo(e))
    for d in ecs.describe_services(cluster=s["cluster"], services=list(s["servicios"].values()))["services"]:
        info("servicio " + d["serviceName"] + ": " + str(d["runningCount"]) + " tareas corriendo")
    info("estables en " + str(int(time.time() - inicio)) + " s")


def accion_apagar():
    cuenta_actual()
    cambiar_tareas(0)
    info("tareas apagadas. el alb sigue cobrando hasta python tareas.py destruir")


def accion_encender():
    cuenta_actual()
    p = parametros()
    cambiar_tareas(int(p.get("tareas_por_servicio", "2")))
    cuando = reprogramar_apagado(int(p.get("horas_apagado", "2")))
    info("nuevo apagado automatico: " + cuando + " utc. siguiente: python tareas.py probar")


def accion_documentar():
    #genera docs/api/agrocredit-api.html desde api/openapi.yaml (sin aws ni docker)
    sys.path.insert(0, os.path.join(AQUI, "api"))
    import documentar
    ruta, cambio = documentar.escribir()
    info(("documentacion de apis actualizada: " if cambio else "documentacion de apis sin cambios: ") + os.path.relpath(ruta, RAIZ))


def accion_padron():
    #solo lectura: registros que quedan en cada tabla de padron y asignaciones hechas en agro-datos
    #uso: python tareas.py padron  (antes y despues de registrar compradores)
    cuenta_actual()
    s = salidas()
    ddb = cliente("dynamodb")
    for tipo, campos in (("empresas", ("razonSocial",)), ("personas", ("nombres", "apellidos"))):
        nombre = s["tablas_padron"][tipo]
        items = []
        for pagina in ddb.get_paginator("scan").paginate(TableName=nombre, ConsistentRead=True):
            items += pagina.get("Items", [])
        items.sort(key=lambda i: i["id"]["S"])
        info(nombre + ": quedan " + str(len(items)))
        for i in items:
            salida("   " + i["id"]["S"] + "  " + " ".join(i.get(c, {}).get("S", "") for c in campos))
    asignados = []
    for pagina in ddb.get_paginator("scan").paginate(TableName=s["tabla"], ConsistentRead=True, FilterExpression="entidad = :e",
                                                     ExpressionAttributeValues={":e": {"S": "PADRON_ASIGNADO"}}):
        asignados += pagina.get("Items", [])
    asignados.sort(key=lambda i: i.get("creadoEn", {}).get("S", ""))
    info(s["tabla"] + ": asignaciones del padron " + str(len(asignados)))
    for a in asignados:
        datos = a.get("datos", {}).get("M", {})
        quien = datos.get("razonSocial", datos.get("nombres", {})).get("S", "")
        salida("   " + a.get("creadoEn", {}).get("S", "") + "  " + a["SK"]["S"] + "  " + a.get("origen", {}).get("S", "") +
               "  " + quien + "  usuario " + a["PK"]["S"][5:13] + "...")


ACCIONES = {
    "preparar": accion_preparar,
    "init": accion_init,
    "plan": accion_plan,
    "pruebas": accion_pruebas,
    "flujo": accion_flujo,
    "padron": accion_padron,
    "documentar": accion_documentar,
    "desplegar": accion_desplegar,
    "probar": accion_probar,
    "caida": accion_caida,
    "apagar": accion_apagar,
    "encender": accion_encender,
    "destruir": accion_destruir,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ACCIONES:
        print("uso: python tareas.py <" + "|".join(ACCIONES) + ">")
        sys.exit(1)
    atexit.register(guardar_registro)
    try:
        ACCIONES[sys.argv[1]]()
    except KeyboardInterrupt:
        info("interrumpido por el usuario")
        sys.exit(130)
    except Exception:
        detalle = traceback.format_exc()
        print(detalle)
        anotar(detalle)
        sys.exit(1)
