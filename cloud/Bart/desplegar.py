#!/usr/bin/env python3
"""Despliega Bart completo en tu cuenta AWS (AWS Academy Learner Lab con LabRole) con un solo comando.

Uso:
    Mac / Linux:  python3 desplegar.py
    Windows:      py desplegar.py
Opciones:
    --stage dev        nombre del ambiente (por defecto dev)
    --sin-pruebas      no corre las pruebas finales

Antes: copia credential.example.txt como credential.txt y pega tus claves (ver README.md).
Que hace, en orden:
     1. Crea .venv e instala requirements.txt (solo la primera vez).
     2. Lee credential.txt (no imprime ninguna clave).
     3. Verifica la cuenta AWS, LabRole, la clave de Groq y que los nombres de bucket esten libres.
     4. Instala Serverless Framework v4 y las dependencias de la web (npm).
     5. Despliega la Central de riesgo y carga 80 clientes.
     6. Despliega Solicitudes + workflow (Step Functions) y carga productos y ofertas.
     7. Despliega Bart (chat).
     8. Compila y publica la web en S3.
     9. Genera las colecciones Postman con tus URLs.
    10. Corre las 3 colecciones contra tu cuenta (pruebas).
    11. Escribe despliegue_resultado.txt con tus URLs.
Se puede volver a ejecutar: lo que ya existe se actualiza y los datos se vuelven a cargar igual.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ES_WINDOWS = os.name == "nt"
VENV = RAIZ / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if ES_WINDOWS else "bin/python")
LOGS = RAIZ / "despliegue_logs"
CLAVES = {
    "aws_access_key_id": "AWS_ACCESS_KEY_ID",
    "aws_secret_access_key": "AWS_SECRET_ACCESS_KEY",
    "aws_session_token": "AWS_SESSION_TOKEN",
    "groq_api_creditos": "GROQ_API_KEY",
    "serverless_creditos": "SERVERLESS_ACCESS_KEY",
    "sufijo": "BART_SUFIJO",
}
SERVICIOS = [  # orden de despliegue (cada uno lee las URLs del anterior)
    ("Central de riesgo", RAIZ / "backend/central-riesgo", "bart-central-riesgo"),
    ("Solicitudes y workflow", RAIZ / "backend/solicitudes", "bart-solicitudes"),
    ("Bart (chat)", RAIZ / "backend/bart", "bart-chat"),
    ("Web", RAIZ / "frontend", "bart-web"),
]


class Fallo(Exception):
    pass


def titulo(n, total, texto):
    print("\n[%d/%d] %s" % (n, total, texto), flush=True)


def ok(texto):
    print("      OK  " + texto, flush=True)


def aviso(texto):
    print("      !!  " + texto, flush=True)


# ---------------- 1. entorno Python ----------------
def en_venv():
    return Path(sys.prefix).resolve() == VENV.resolve()


def asegurar_venv():
    """Crea .venv con requirements.txt y vuelve a ejecutar este script dentro de el."""
    if sys.version_info < (3, 10):
        # En Mac, "python3" suele ser el Python 3.9 del sistema aunque haya otro mas nuevo instalado: se busca solo
        for nombre in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10"):
            otro = shutil.which(nombre) or next((r for r in ("/opt/homebrew/bin/" + nombre, "/usr/local/bin/" + nombre,
                                                              "/Library/Frameworks/Python.framework/Versions/%s/bin/%s" % (nombre[6:], nombre))
                                                 if Path(r).exists()), None)
            if otro:
                print("Python %s es antiguo; se usa %s" % (sys.version.split()[0], otro), flush=True)
                sys.exit(subprocess.run([otro, str(Path(sys.argv[0]).resolve())] + sys.argv[1:]).returncode)
        sys.exit("Necesitas Python 3.10 o superior (tienes %s). Instala Python 3.14 desde https://www.python.org "
                 "y vuelve a ejecutar. Ver README.md" % sys.version.split()[0])
    if en_venv():
        return
    req = (RAIZ / "requirements.txt").read_bytes()
    marca = VENV / ".requirements.sha256"
    huella = hashlib.sha256(req).hexdigest()
    if not VENV_PY.exists():
        print("Creando entorno Python en .venv ...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    if not marca.exists() or marca.read_text().strip() != huella:
        print("Instalando requirements.txt en .venv (puede tardar un minuto) ...", flush=True)
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=True)
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "--quiet", "-r", str(RAIZ / "requirements.txt")], check=True)
        marca.write_text(huella)
    sys.exit(subprocess.run([str(VENV_PY), str(Path(sys.argv[0]).resolve())] + sys.argv[1:]).returncode)


# ---------------- 2. credenciales ----------------
def cargar_credenciales():
    archivo = RAIZ / "credential.txt"
    if not archivo.exists():
        raise Fallo("No existe credential.txt. Copia credential.example.txt como credential.txt y pega tus claves "
                    "(README.md, seccion Credenciales).")
    valores = {}
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Za-z_]+)\s*=\s*(.*?)\s*$", linea)
        if m and m.group(1).lower() in CLAVES:
            valores[m.group(1).lower()] = m.group(2)
    faltan = [k for k in CLAVES if not valores.get(k) or valores[k].startswith(("PEGA_AQUI", "PON_AQUI"))]
    if faltan:
        raise Fallo("En credential.txt faltan o siguen de ejemplo: %s" % ", ".join(faltan))
    if not re.match(r"^[a-z0-9]{2,12}$", valores["sufijo"]):
        raise Fallo("El sufijo debe tener de 2 a 12 letras minusculas o numeros (ej. tus iniciales: jvt). Tienes: %r" % valores["sufijo"])
    env = dict(os.environ)
    env.pop("AWS_PROFILE", None)
    env.update({CLAVES[k]: v for k, v in valores.items()})
    env.update({"AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1", "CI": "true"})
    os.environ.update({k: v for k, v in env.items() if k.startswith(("AWS_", "GROQ_", "BART_", "SERVERLESS_"))})
    os.environ.pop("AWS_PROFILE", None)
    return env


# ---------------- 3. verificaciones ----------------
def verificar(stage, sufijo):
    import json
    import urllib.error
    import urllib.request

    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    try:
        ident = boto3.client("sts").get_caller_identity()
    except (ClientError, NoCredentialsError) as e:
        codigo = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        raise Fallo("Las credenciales de AWS no funcionan (%s). Si es ExpiredToken, copia otra vez 'AWS Details' "
                    "del Learner Lab en credential.txt." % codigo)
    ok("cuenta AWS %s****%s, region us-east-1" % (ident["Account"][:2], ident["Account"][-2:]))
    try:
        boto3.client("iam").get_role(RoleName="LabRole")
        ok("rol LabRole existe")
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchEntity":
            raise Fallo("Tu cuenta no tiene el rol LabRole. Este proyecto esta hecho para AWS Academy Learner Lab.")
        aviso("no se pudo leer LabRole (%s); se asume que existe" % e.response["Error"]["Code"])

    req = urllib.request.Request("https://api.groq.com/openai/v1/models", headers={
        "Authorization": "Bearer " + os.environ["GROQ_API_KEY"],
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"})
    try:
        modelos = [m["id"] for m in json.loads(urllib.request.urlopen(req, timeout=20).read())["data"]]
    except urllib.error.HTTPError as e:
        raise Fallo("La clave de Groq no funciona (HTTP %d). Revisa groq_api_creditos en credential.txt." % e.code)
    except urllib.error.URLError:
        raise Fallo("No hay conexion con api.groq.com. Revisa tu internet.")
    if "openai/gpt-oss-120b" not in modelos:
        raise Fallo("Tu cuenta de Groq no tiene el modelo openai/gpt-oss-120b.")
    ok("clave de Groq valida y modelo openai/gpt-oss-120b disponible")

    s3 = boto3.client("s3")
    for bucket in ("bart-boletas-%s-%s" % (stage, sufijo), "bart-web-%s-%s" % (stage, sufijo)):
        try:
            s3.head_bucket(Bucket=bucket)
            ok("bucket %s ya es tuyo (se actualiza)" % bucket)
        except ClientError as e:
            codigo = e.response["Error"]["Code"]
            if codigo in ("404", "NoSuchBucket"):
                ok("nombre de bucket libre: %s" % bucket)
            elif codigo in ("403", "AccessDenied"):
                raise Fallo("El bucket %s ya existe en OTRA cuenta de AWS. Cambia 'sufijo' en credential.txt." % bucket)
            else:
                raise Fallo("No se pudo revisar el bucket %s (%s)." % (bucket, codigo))

    for herramienta in ("node", "npm"):
        if not shutil.which(herramienta):
            raise Fallo("No encuentro '%s'. Instala Node.js 22 o superior (https://nodejs.org) y abre otra terminal." % herramienta)
    version = subprocess.run([shutil.which("node"), "--version"], capture_output=True, text=True).stdout.strip()
    if int(version.lstrip("v").split(".")[0]) < 22:
        raise Fallo("Necesitas Node.js 22 o superior (tienes %s)." % version)
    ok("Node.js %s" % version)


# ---------------- utilidades de comandos ----------------
def correr(cmd, cwd, env, log, mostrar_error=True):
    LOGS.mkdir(exist_ok=True)
    ruta_log = LOGS / log
    with open(ruta_log, "w", encoding="utf-8", errors="replace") as f:
        r = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode != 0:
        if mostrar_error:
            lineas = ruta_log.read_text(encoding="utf-8", errors="replace").splitlines()
            print("\n".join("      | " + l for l in lineas[-25:] if "DeprecationWarning" not in l))
        raise Fallo("Fallo: %s (detalle completo en despliegue_logs/%s)" % (" ".join(str(c) for c in cmd[:3]), log))
    return ruta_log


def binario(nombre, carpeta):
    ruta = shutil.which(nombre, path=str(carpeta / "node_modules" / ".bin"))
    if not ruta:
        raise Fallo("No se encontro %s en %s/node_modules (fallo npm install)." % (nombre, carpeta.name))
    return ruta


def npm_instalar(carpeta, env):
    if (carpeta / "node_modules").exists():
        ok("dependencias npm ya instaladas en %s" % (carpeta.name if carpeta != RAIZ else "la raiz"))
        return
    npm = shutil.which("npm")
    comando = [npm, "ci"] if (carpeta / "package-lock.json").exists() else [npm, "install"]
    correr(comando, carpeta, env, "npm_%s.log" % (carpeta.name if carpeta != RAIZ else "raiz"))
    ok("npm instalado en %s" % (carpeta.name if carpeta != RAIZ else "la raiz"))


def desplegar_servicio(nombre, carpeta, stack, stage, env):
    sls = binario("serverless", carpeta if (carpeta / "node_modules").exists() else RAIZ)
    t0 = time.time()
    correr([sls, "deploy", "--stage", stage, "--region", "us-east-1"], carpeta, env, "deploy_%s.log" % stack)
    ok("%s desplegado: stack %s-%s (%d s)" % (nombre, stack, stage, time.time() - t0))


def salida_stack(stack, clave):
    import boto3
    outs = boto3.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])
    return next((o["OutputValue"] for o in outs if o["OutputKey"] == clave), None)


def py(script, *args, env, log):
    return correr([str(VENV_PY), str(RAIZ / script)] + list(args), RAIZ, env, log)


# ---------------- principal ----------------
def main():
    ap = argparse.ArgumentParser(description="Despliega Bart completo en tu cuenta AWS.")
    ap.add_argument("--stage", default="dev")
    ap.add_argument("--sin-pruebas", action="store_true")
    args = ap.parse_args()
    if not re.match(r"^[a-z0-9]{2,10}$", args.stage):
        raise Fallo("El stage debe tener de 2 a 10 letras minusculas o numeros.")
    total, inicio = 11, time.time()
    titulo(1, total, "Entorno Python (.venv con requirements.txt)")
    ok("Python %s en %s" % (sys.version.split()[0], VENV.name))
    titulo(2, total, "Credenciales (credential.txt)")
    env = cargar_credenciales()
    ok("claves cargadas (no se muestran); sufijo de buckets: %s" % env["BART_SUFIJO"])
    titulo(3, total, "Verificaciones previas")
    verificar(args.stage, env["BART_SUFIJO"])
    titulo(4, total, "Herramientas: Serverless Framework v4 y dependencias de la web")
    npm_instalar(RAIZ, env)
    npm_instalar(RAIZ / "frontend", env)

    titulo(5, total, "Central de riesgo y sus datos")
    desplegar_servicio(*SERVICIOS[0], args.stage, env)
    py("scripts/cargar_datos.py", "rcc", "--stage", args.stage, env=env, log="datos_rcc.log")
    ok("80 clientes cargados en bart-rcc-evaluacion-clientes-%s" % args.stage)

    titulo(6, total, "Solicitudes y workflow (Step Functions) y sus datos")
    vendor = RAIZ / "backend/solicitudes/vendor"
    shutil.rmtree(vendor, ignore_errors=True)
    correr([str(VENV_PY), "-m", "pip", "install", "--quiet", "--no-deps", "--target", str(vendor), "pypdf==7.0.1"],
           RAIZ, env, "pypdf_vendor.log")
    ok("pypdf empaquetado para la Lambda")
    desplegar_servicio(*SERVICIOS[1], args.stage, env)
    py("scripts/cargar_datos.py", "productos", "--stage", args.stage, env=env, log="datos_productos.log")
    py("scripts/cargar_datos.py", "ofertas", "--stage", args.stage, env=env, log="datos_ofertas.log")
    ok("5 productos y 124 ofertas cargados")

    titulo(7, total, "Bart (chat por estados)")
    desplegar_servicio(*SERVICIOS[2], args.stage, env)

    titulo(8, total, "Web (React + Vite en S3)")
    desplegar_servicio(*SERVICIOS[3], args.stage, env)

    titulo(9, total, "Colecciones Postman con tus URLs")
    py("scripts/generar_postman.py", "--stage", args.stage, env=env, log="postman.log")
    ok("backend/*/*.postman_collection.json actualizadas")

    resultados = []
    titulo(10, total, "Pruebas finales contra tu cuenta" + (" (omitidas)" if args.sin_pruebas else ""))
    if not args.sin_pruebas:
        for carpeta, nombre in (("central-riesgo", "bart-central-riesgo"), ("solicitudes", "bart-solicitudes"), ("bart", "bart-chat")):
            log = py("scripts/correr_coleccion.py", "backend/%s/%s.postman_collection.json" % (carpeta, nombre),
                     env=env, log="pruebas_%s.log" % nombre)
            linea = log.read_text(encoding="utf-8").strip().splitlines()[-1]
            resultados.append(linea)
            ok(linea)

    titulo(11, total, "Resumen")
    s = args.stage
    urls = {
        "Web (cliente y banco)": salida_stack("bart-web-" + s, "WebsiteURL"),
        "API Bart (chat)": salida_stack("bart-chat-" + s, "ChatApiUrl"),
        "API Solicitudes": salida_stack("bart-solicitudes-" + s, "SolicitudesApiUrl"),
        "API Central de riesgo": salida_stack("bart-central-riesgo-" + s, "RccApiUrl"),
    }
    texto = ["Bart desplegado (stage %s) el %s en %d minutos." % (s, time.strftime("%Y-%m-%d %H:%M"), (time.time() - inicio) / 60), ""]
    texto += ["%-24s %s" % (k + ":", v) for k, v in urls.items()]
    texto += ["", "Pruebas:"] + (["  " + r for r in resultados] or ["  omitidas"])
    texto += ["", "Siguiente: abre la URL de la web y usa los DNI del panel 'Datos de demostracion'.",
              "Postman: importa backend/central-riesgo, backend/solicitudes y backend/bart (*.postman_collection.json).",
              "Para borrar todo: python3 eliminar.py  (Windows: py eliminar.py)"]
    (RAIZ / "despliegue_resultado.txt").write_text("\n".join(texto) + "\n", encoding="utf-8")
    print("\n" + "\n".join(texto))
    print("\n(Guardado en despliegue_resultado.txt)")


if __name__ == "__main__":
    asegurar_venv()
    try:
        main()
    except Fallo as e:
        print("\nERROR: %s" % e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.", file=sys.stderr)
        sys.exit(130)
