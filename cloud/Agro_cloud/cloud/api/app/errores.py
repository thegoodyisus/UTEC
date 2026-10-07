#errores en formato application/problem+json (rfc 9457) con requestId
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

TITULOS = {400: "Solicitud invalida", 401: "No autenticado", 403: "Sin permiso", 404: "No encontrado",
           405: "Metodo no permitido", 409: "Conflicto", 422: "Datos invalidos", 503: "Servicio no disponible"}


class Problema(Exception):
    def __init__(self, estado, detalle="", titulo=None):
        super().__init__(detalle)
        self.estado = estado
        self.detalle = detalle
        self.titulo = titulo or TITULOS.get(estado, "Error")


def respuesta(request, estado, titulo, detalle=""):
    cuerpo = {"type": "about:blank", "title": titulo, "status": estado,
              "instance": request.url.path, "requestId": getattr(request.state, "request_id", "")}
    if detalle:
        cuerpo["detail"] = detalle
    return JSONResponse(cuerpo, status_code=estado, media_type="application/problem+json")


def registrar_manejadores(app):
    @app.exception_handler(Problema)
    async def _problema(request: Request, exc: Problema):
        return respuesta(request, exc.estado, exc.titulo, exc.detalle)

    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError):
        partes = []
        for e in exc.errors()[:5]:
            campo = ".".join(str(x) for x in e.get("loc", []) if x != "body")
            partes.append(campo + ": " + e.get("msg", ""))
        return respuesta(request, 422, TITULOS[422], "; ".join(partes))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return respuesta(request, exc.status_code, TITULOS.get(exc.status_code, "Error"), str(exc.detail or ""))
