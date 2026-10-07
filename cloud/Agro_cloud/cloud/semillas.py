#datos iniciales de la demo: generados al azar una sola vez y fijados aqui (todos ficticios, ley 29733)
#los carga tareas.py desplegar en dynamodb; la aplicacion siempre lee de la base, nunca de este archivo
#catalogo y cuentas se actualizan en cada despliegue en agro-datos; el padron vive en cloud/semillas/*.json
#y se carga solo una vez en sus tablas propias (decision 58)
#ojo: la carpeta semillas/ no tiene __init__.py a proposito; asi "import semillas" siempre resuelve a este archivo
import json
import os

DIR_SEMILLAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "semillas")
VERSION_CATALOGO = "2026-10-04"

#precio de referencia de demostracion, no es un dato de mercado real
CULTIVOS = [
    {"slug": "papa", "nombre": "Papa", "orden": 1, "referenciaMercadoCentimosPorKg": 120,
     "etiquetasRekognition": ["Potato", "Sweet Potato", "Yam"]},
    {"slug": "maiz", "nombre": "Maíz", "orden": 2, "referenciaMercadoCentimosPorKg": 110,
     "etiquetasRekognition": ["Corn", "Maize", "Corn Cob"]},
    {"slug": "cafe", "nombre": "Café", "orden": 3, "referenciaMercadoCentimosPorKg": 1250,
     "etiquetasRekognition": ["Coffee Beans", "Coffee"]},
    {"slug": "arroz", "nombre": "Arroz", "orden": 4, "referenciaMercadoCentimosPorKg": 280,
     "etiquetasRekognition": ["Rice", "Brown Rice"]},
    {"slug": "esparrago", "nombre": "Espárrago", "orden": 5, "referenciaMercadoCentimosPorKg": 650,
     "etiquetasRekognition": ["Asparagus"]},
    {"slug": "quinua", "nombre": "Quinua", "orden": 6, "referenciaMercadoCentimosPorKg": 780,
     "etiquetasRekognition": ["Quinoa"]},
]

#cuentas de cargo de prueba que ve todo comprador (no se consumen)
CUENTAS = [
    {"id": "cc-8830", "orden": 1, "titulo": "Cta. Cte. Soles ***-8830", "descripcion": "Cuenta ficticia de prueba"},
    {"id": "ahorro-2217", "orden": 2, "titulo": "Cta. Ahorros Soles ***-2217", "descripcion": "Cuenta ficticia de prueba"},
    {"id": "cc-usd-7044", "orden": 3, "titulo": "Cta. Cte. Dólares ***-7044", "descripcion": "Cuenta ficticia de prueba"},
]


def items_catalogo():
    return [dict({"PK": "CATALOGO", "SK": "CULTIVO#" + c["slug"], "entidad": "CULTIVO", "versionCatalogo": VERSION_CATALOGO}, **c) for c in CULTIVOS]


def items_cuentas():
    return [dict({"PK": "CUENTA_DEMO", "SK": "CUENTA#" + c["id"], "entidad": "CUENTA_DEMO"}, **c) for c in CUENTAS]


def leer_padron():
    #padron ficticio en cloud/semillas/*.json (decision 58): solo lo usa desplegar para la carga inicial
    #ruta relativa a este archivo: funciona igual en windows y mac sin importar desde donde se ejecute
    def leer(nombre):
        with open(os.path.join(DIR_SEMILLAS, nombre), encoding="utf-8") as f:
            return json.load(f)
    return leer("padron-personas.json"), leer("padron-empresas.json")


def items_padron():
    #personas -> tabla <prefijo>padron-personas, empresas -> <prefijo>padron-empresas (clave simple id)
    personas, empresas = leer_padron()
    return ([dict({"entidad": "PADRON_PERSONA"}, **p) for p in personas],
            [dict({"entidad": "PADRON_EMPRESA"}, **e) for e in empresas])
