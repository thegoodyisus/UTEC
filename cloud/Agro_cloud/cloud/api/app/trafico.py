#conteo de peticiones por api en memoria de cada tarea (decision 59): solo metodo y ruta del contrato, nunca valores ni usuario
from collections import Counter

from .datos import ahora_iso

PREFIJO = "/api/v1"
DESDE = ahora_iso()
_conteo = Counter()


def clave(scope, metodo):
    #ruta del contrato (ej. GET /campanas/{campaniaId}); lo que no coincide con ninguna ruta va a "otras"
    ruta = getattr(scope.get("route"), "path", None)
    if not ruta:
        return "otras"
    return metodo + " " + (ruta[len(PREFIJO):] if ruta.startswith(PREFIJO + "/") else ruta)


def contar(scope, metodo):
    _conteo[clave(scope, metodo)] += 1


def resumen():
    return {"desde": DESDE, "peticiones": dict(_conteo)}


def reiniciar():
    _conteo.clear()
