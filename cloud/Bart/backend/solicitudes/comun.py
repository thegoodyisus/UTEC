"""Utilidades comunes del microservicio Solicitudes."""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

VERSION_CONTRATO = "1.1"
LIMA = timezone(timedelta(hours=-5))  # Peru no usa horario de verano
DNI_RE = re.compile(r"^[0-9]{8}$")
ESTADOS = ["EN_PROCESO", "PRE_APROBADA", "CONTRAOFERTA", "NO_ELEGIBLE", "DOC_INCONSISTENTE", "DESISTIDA", "CERRADA", "ERROR"]
ESTADOS_ACTIVOS = ["EN_PROCESO", "CONTRAOFERTA", "PRE_APROBADA"]

# Textos fijos que ve el cliente.
T1_RIESGO = ("Por políticas de riesgo no podemos aprobar tu solicitud por este canal. "
             "Te invitamos a acercarte a una de nuestras tiendas.")
T2_CONDICIONES = ("Por este canal podemos ofrecerte hasta S/ {monto}{plazo}. "
                  "Si necesitas otras condiciones, te invitamos a acercarte a una de nuestras tiendas.")
T3_BOLETA = ("No pudimos validar tu boleta de pago. Te invitamos a acercarte a una de nuestras tiendas "
             "con tu última boleta.")
T4_ERROR = ("Tuvimos un problema al procesar tu solicitud. Inténtalo más tarde o "
            "acércate a una de nuestras tiendas.")

NOMBRE_WEB = {"PLD": "Préstamo de libre disponibilidad", "TC": "Tarjeta de crédito",
              "VEHICULAR": "Crédito vehicular", "HIPOTECARIO": "Crédito hipotecario",
              "COMPRA_DEUDA": "Compra de deuda"}  # nombres de producto para mostrar al cliente

_dynamo = boto3.resource("dynamodb")


def tabla(variable_entorno):
    return _dynamo.Table(os.environ[variable_entorno])


def ahora_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hoy_lima():
    return datetime.now(LIMA).strftime("%Y-%m-%d")


def soles(x):
    return "{:,.2f}".format(float(x))


def _plazo_txt(plazo):
    return " a %d meses" % int(plazo) if plazo else ""


def texto_resultado(estado, producto_id, monto, plazo, cuota):
    """Plantilla para cuando Groq no responde y texto al aceptar una contraoferta."""
    nombre = NOMBRE_WEB.get(producto_id, producto_id).lower()
    if estado == "PRE_APROBADA":
        return ("Tu solicitud de %s está pre-aprobada por S/ %s%s, con una cuota estimada de S/ %s, "
                "sujeta a validación del banco." % (nombre, soles(monto), _plazo_txt(plazo), soles(cuota)))
    return ("Hoy podemos ofrecerte S/ %s%s en tu %s, con una cuota estimada de S/ %s. "
            "¿Aceptas este monto o prefieres acercarte a una de nuestras tiendas?"
            % (soles(monto), _plazo_txt(plazo), nombre, soles(cuota)))


def texto_condiciones(monto, plazo):
    """Texto cuando el cliente pide otras condiciones."""
    return T2_CONDICIONES.format(monto=soles(monto), plazo=_plazo_txt(plazo))


def a_dynamo(x):
    """float -> Decimal (DynamoDB no acepta float). Recursivo."""
    if isinstance(x, bool) or x is None:
        return x
    if isinstance(x, float):
        return Decimal(str(round(x, 4)))
    if isinstance(x, dict):
        return {k: a_dynamo(v) for k, v in x.items()}
    if isinstance(x, list):
        return [a_dynamo(v) for v in x]
    return x


def de_dynamo(x):
    """Decimal -> int o float. Recursivo."""
    if isinstance(x, Decimal):
        return int(x) if x == x.to_integral_value() else float(x)
    if isinstance(x, dict):
        return {k: de_dynamo(v) for k, v in x.items()}
    if isinstance(x, list):
        return [de_dynamo(v) for v in x]
    return x


def num(x):
    return None if x is None or x == "" else float(x)


def log(evento, **campos):
    """Logs sin secretos ni datos personales: solo ids, codigos, estados y tiempos."""
    print(json.dumps({"evento": evento, **campos}, default=str))


class ErrorApi(Exception):
    def __init__(self, status, codigo, mensaje, detalle=None):
        super().__init__(codigo)
        self.status, self.codigo, self.mensaje, self.detalle = status, codigo, mensaje, detalle

    def cuerpo(self):
        e = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.detalle is not None:
            e["detalle"] = self.detalle
        return {"error": e}
