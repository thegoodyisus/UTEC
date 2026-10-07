#api de agrocredit: implementa cloud/api/openapi.yaml v1.5.0 (la prueba de deriva lo verifica)
import hmac
import json
import os
import socket
import threading
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse

from . import modelos as m
from . import trafico
from .datos import Datos, ahora_iso, datos
from .dinero import a_centimos, a_texto
from .errores import Problema, registrar_manejadores
from .seguridad import Usuario, exigir_rol

LIMA = timezone(timedelta(hours=-5))
EXT = {"image/jpeg": "jpg", "image/png": "png"}


def datos_tarea():
    #en ecs se toman el id de la tarea y la zona desde el endpoint de metadata v4
    uri = os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
    if uri:
        try:
            with urllib.request.urlopen(uri + "/task", timeout=2) as r:
                info = json.load(r)
                return info["TaskARN"].rsplit("/", 1)[-1], info.get("AvailabilityZone", "")
        except Exception:
            pass
    return socket.gethostname(), "local"


TAREA, ZONA = datos_tarea()
VERSION = os.environ.get("TAREA_VERSION", "local")
TOKEN_DEMO = os.environ.get("DEMO_TOKEN", "")

app = FastAPI(title="AgroCredit API", version="1.5.0", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
registrar_manejadores(app)
cualquiera = exigir_rol("agricultor", "comprador")
agricultor = exigir_rol("agricultor")
comprador = exigir_rol("comprador")


@app.middleware("http")
async def id_peticion(request: Request, siguiente):
    request.state.request_id = str(uuid.uuid4())
    try:
        respuesta = await siguiente(request)
    finally:
        #se cuenta tambien si fallo (401, 422, 500): interesa a que api se llamo
        trafico.contar(request.scope, request.method)
    respuesta.headers["X-Request-Id"] = request.state.request_id
    return respuesta


def hoy_lima():
    return datetime.now(LIMA).date()


def aceptado(recurso_id, consultar):
    return JSONResponse({"recursoId": recurso_id, "estado": "PROCESANDO", "consultar": consultar}, status_code=202)


def lista(items, cursor):
    return {"items": items, "siguienteCursor": cursor}


#vistas de salida
def vista_perfil(p):
    fuera = ("PK", "SK", "entidad", "usuarioClave", "usuarioOrden", "publicadaClave", "publicadaOrden")
    return {k: v for k, v in p.items() if k not in fuera}


def vista_campana(c):
    return {
        "campaniaId": c["campaniaId"], "propietarioSub": c["propietarioSub"], "productorNombre": c["productorNombre"],
        "cultivo": c["cultivo"], "departamento": c["departamento"], "provincia": c["provincia"], "distrito": c["distrito"],
        "cosecha": c["cosecha"], "volumenKg": c["volumenKg"], "logistica": c["logistica"],
        "capital": a_texto(c["capitalCentimos"]), "precioAhoraPorKg": a_texto(c["precioAhoraCentimosPorKg"]),
        "precioContraentregaPorKg": a_texto(c["precioContraentregaCentimosPorKg"]),
        "referenciaMercadoPorKg": a_texto(c["referenciaMercadoCentimosPorKg"]),
        "estado": c["estado"], "numeroOfertas": c.get("numeroOfertas", 0), "creadoEn": c["creadoEn"],
    }


def vista_campana_publica(c):
    v = vista_campana(c)
    #sin capital, documento ni celular del productor
    for k in ("capital", "propietarioSub", "estado", "creadoEn", "numeroOfertas"):
        v.pop(k, None)
    return v


def vista_oferta(o):
    return {
        "ofertaId": o["ofertaId"], "campaniaId": o["campaniaId"], "compradorNombre": o["compradorNombre"],
        "volumenKg": o["volumenKg"], "precioPorKg": a_texto(o["precioCentimosPorKg"]), "modalidad": o["modalidad"],
        "logistica": o["logistica"], "fechaEntrega": o["fechaEntrega"], "total": a_texto(o["totalCentimos"]),
        "estado": o["estado"], "creadoEn": o["creadoEn"],
        "cultivo": o.get("cultivo"), "productorNombre": o.get("productorNombre"), "departamento": o.get("departamento"),
    }


def campana_o_404(d, campania_id):
    c = d.obtener("CAMP#" + campania_id, "META")
    if not c:
        raise Problema(404, "la campana no existe o aun se esta procesando")
    return c


def visible(c, usuario):
    return c["propietarioSub"] == usuario.sub or (usuario.rol == "comprador" and c["estado"] == "PUBLICADA")


def perfil_o_403(d, usuario):
    p = d.obtener("USER#" + usuario.sub, "PROFILE")
    if not p:
        raise Problema(403, "primero completa tu perfil")
    return p


#sistema
@app.get("/api/v1/salud")
def obtener_salud():
    #trafico: peticiones por api que atendio esta tarea desde que arranco (el panel suma las tareas)
    return JSONResponse({"estado": "ok", "tareaId": TAREA, "zona": ZONA, "version": VERSION, "trafico": trafico.resumen()},
                        headers={"Cache-Control": "no-store"})


@app.get("/api/v1/config")
def obtener_config():
    valores = {"region": os.environ.get("REGION_AWS", ""), "userPoolId": os.environ.get("USER_POOL_ID", ""), "clientId": os.environ.get("CLIENT_ID", "")}
    if not all(valores.values()):
        raise Problema(503, "configuracion incompleta")
    return JSONResponse(valores, headers={"Cache-Control": "public, max-age=300"})


@app.post("/api/v1/demo/caer", status_code=202)
def demo_caer(x_demo_token: str = Header(default="")):
    #solo para la demo de resiliencia: mata el proceso sin apagado ordenado, como un fallo real
    if not TOKEN_DEMO:
        raise Problema(404, "demo desactivada")
    if not hmac.compare_digest(x_demo_token.encode(), TOKEN_DEMO.encode()):
        raise Problema(403, "token de demo invalido")
    threading.Timer(0.5, os._exit, [1]).start()
    return {"estado": "cayendo", "tareaId": TAREA}


#perfil
@app.get("/api/v1/perfil")
def obtener_perfil(usuario: Usuario = Depends(cualquiera), d: Datos = Depends(datos)):
    p = d.obtener("USER#" + usuario.sub, "PROFILE")
    if not p:
        raise Problema(404, "perfil no creado")
    return vista_perfil(p)


@app.post("/api/v1/perfil", status_code=201)
def crear_perfil(cuerpo: m.PerfilCrear, usuario: Usuario = Depends(cualquiera), d: Datos = Depends(datos)):
    if cuerpo.rol != usuario.rol:
        raise Problema(403, "el rol del perfil debe coincidir con el de la cuenta")
    #el documento del perfil es el usuario de la cuenta (no se puede declarar otro)
    if usuario.documento and cuerpo.documento != usuario.documento:
        raise Problema(403, "el documento debe ser el de tu cuenta")
    if cuerpo.rol == "comprador":
        largo = 11 if cuerpo.tipoDoc == "RUC" else 8
        if len(cuerpo.documento) != largo:
            raise Problema(422, cuerpo.tipoDoc + " debe tener " + str(largo) + " numeros")
        if cuerpo.cuentaCargoId and not d.obtener("CUENTA_DEMO", "CUENTA#" + cuerpo.cuentaCargoId):
            raise Problema(422, "cuenta de cargo desconocida")
    if cuerpo.rol == "agricultor":
        catalogo = d.catalogo()
        desconocidos = [c for c in cuerpo.cultivos if c not in catalogo]
        if desconocidos:
            raise Problema(422, "cultivos fuera del catalogo: " + ", ".join(desconocidos))
    item = dict(cuerpo.model_dump(exclude_none=True), PK="USER#" + usuario.sub, SK="PROFILE", entidad="USUARIO",
                sub=usuario.sub, creadoEn=ahora_iso())
    if not d.crear(item):
        raise Problema(409, "el perfil ya existe")
    return JSONResponse(vista_perfil(item), status_code=201)


#catalogo, padron y cuentas de prueba
@app.get("/api/v1/catalogo/cultivos")
def listar_cultivos(usuario: Usuario = Depends(cualquiera), d: Datos = Depends(datos)):
    return [{"slug": c["slug"], "nombre": c["nombre"], "referenciaMercadoPorKg": a_texto(c["referenciaMercadoCentimosPorKg"])}
            for c in d.catalogo().values()]


@app.post("/api/v1/padron/consulta")
def consultar_padron(cuerpo: m.PadronConsulta, usuario: Usuario = Depends(comprador), d: Datos = Depends(datos)):
    largo = 11 if cuerpo.tipoDoc == "RUC" else 8
    if len(cuerpo.documento) != largo:
        raise Problema(422, cuerpo.tipoDoc + " debe tener " + str(largo) + " numeros")
    encontrado = d.tomar_padron(usuario.sub, cuerpo.uso, cuerpo.tipoDoc)
    if encontrado is None:
        raise Problema(503, "sistema no disponible: no quedan registros en el padron de demostracion")
    return dict(encontrado, tipoDoc=cuerpo.tipoDoc, documento=cuerpo.documento, demo=True)


@app.get("/api/v1/cuentas-demo")
def listar_cuentas_demo(usuario: Usuario = Depends(comprador), d: Datos = Depends(datos)):
    cuentas = sorted(d.todos("CUENTA_DEMO", "CUENTA#"), key=lambda c: c.get("orden", 99))
    return [{"id": c["id"], "titulo": c["titulo"], "descripcion": c["descripcion"]} for c in cuentas]


#campanas
@app.get("/api/v1/campanas")
def listar_mis_campanas(cursor: Optional[str] = None, limite: int = Query(20, ge=1, le=50),
                        usuario: Usuario = Depends(agricultor), d: Datos = Depends(datos)):
    items, siguiente = d.consultar("USER#" + usuario.sub, "CAMP#", limite, cursor, adelante=False, indice="por-usuario")
    return lista([vista_campana(c) for c in items], siguiente)


@app.post("/api/v1/campanas", status_code=202)
def crear_campana(cuerpo: m.CampanaCrear, usuario: Usuario = Depends(agricultor), d: Datos = Depends(datos)):
    campania_id = str(cuerpo.campaniaId)
    consultar = "/api/v1/campanas/" + campania_id
    existente = d.obtener("CAMP#" + campania_id, "META")
    if existente:
        if existente["propietarioSub"] != usuario.sub:
            raise Problema(409, "el identificador de campana ya existe")
        return aceptado(campania_id, consultar)
    catalogo = d.catalogo()
    if cuerpo.cultivo not in catalogo:
        raise Problema(422, "cultivo fuera del catalogo")
    if cuerpo.cosecha <= hoy_lima():
        raise Problema(422, "la cosecha debe ser una fecha futura")
    precios = [a_centimos(cuerpo.capital), a_centimos(cuerpo.precioAhoraPorKg), a_centimos(cuerpo.precioContraentregaPorKg)]
    if min(precios[1:]) <= 0:
        raise Problema(422, "los precios deben ser mayores a 0")
    perfil = perfil_o_403(d, usuario)
    creado = ahora_iso()
    item = {
        "PK": "CAMP#" + campania_id, "SK": "META", "entidad": "CAMPANA", "campaniaId": campania_id,
        "propietarioSub": usuario.sub, "productorNombre": (perfil.get("nombres", "") + " " + perfil.get("apellidos", "")).strip(),
        "cultivo": cuerpo.cultivo, "departamento": cuerpo.departamento, "provincia": cuerpo.provincia, "distrito": cuerpo.distrito,
        "cosecha": cuerpo.cosecha.isoformat(), "volumenKg": cuerpo.volumenKg, "logistica": cuerpo.logistica,
        "capitalCentimos": precios[0], "precioAhoraCentimosPorKg": precios[1], "precioContraentregaCentimosPorKg": precios[2],
        "referenciaMercadoCentimosPorKg": catalogo[cuerpo.cultivo]["referenciaMercadoCentimosPorKg"],
        "estado": "PUBLICADA", "numeroOfertas": 0, "creadoEn": creado, "publicadaEn": creado,
        "usuarioClave": "USER#" + usuario.sub, "usuarioOrden": "CAMP#" + creado + "#" + campania_id,
        "publicadaClave": "PUB#" + cuerpo.cultivo + "#" + cuerpo.departamento, "publicadaOrden": cuerpo.cosecha.isoformat() + "#" + campania_id,
    }
    d.encolar("campana", item)
    return aceptado(campania_id, consultar)


@app.get("/api/v1/campanas/publicadas")
def listar_campanas_publicadas(cultivo: str = Query(..., pattern=r"^[a-z]+$"), departamento: str = Query(..., min_length=1, max_length=120),
                               cursor: Optional[str] = None, limite: int = Query(20, ge=1, le=50),
                               usuario: Usuario = Depends(comprador), d: Datos = Depends(datos)):
    items, siguiente = d.consultar("PUB#" + cultivo + "#" + departamento, "", limite, cursor, adelante=True, indice="publicadas-por-cultivo")
    return lista([vista_campana_publica(c) for c in items], siguiente)


@app.get("/api/v1/campanas/{campaniaId}")
def obtener_campana(campaniaId: uuid.UUID, usuario: Usuario = Depends(cualquiera), d: Datos = Depends(datos)):
    c = campana_o_404(d, str(campaniaId))
    if c["propietarioSub"] == usuario.sub:
        return vista_campana(c)
    if visible(c, usuario):
        return vista_campana_publica(c)
    raise Problema(404, "la campana no existe o no es visible")


@app.patch("/api/v1/campanas/{campaniaId}")
def actualizar_campana(campaniaId: uuid.UUID, cuerpo: m.CampanaActualizar, usuario: Usuario = Depends(agricultor), d: Datos = Depends(datos)):
    #decision 66: update directo y condicional, solo sin ofertas
    campania_id = str(campaniaId)
    enviados = cuerpo.model_dump(exclude_none=True)
    if not enviados:
        raise Problema(422, "envia al menos un campo: volumenKg, capital, precioAhoraPorKg o precioContraentregaPorKg")
    nombres = {"capital": "capitalCentimos", "precioAhoraPorKg": "precioAhoraCentimosPorKg",
               "precioContraentregaPorKg": "precioContraentregaCentimosPorKg"}
    cambios = {}
    for campo, valor in enviados.items():
        if campo in nombres:
            centimos = a_centimos(valor)
            if campo != "capital" and centimos <= 0:
                raise Problema(422, "los precios deben ser mayores a 0")
            cambios[nombres[campo]] = centimos
        else:
            cambios[campo] = valor
    c = campana_o_404(d, campania_id)
    if c["propietarioSub"] != usuario.sub:
        raise Problema(403, "la campana es de otro agricultor")
    if c.get("numeroOfertas", 0) > 0:
        raise Problema(409, "la campana ya tiene ofertas: no se puede modificar")
    actualizada = d.actualizar_campana(campania_id, usuario.sub, cambios)
    if actualizada is None:
        #llego una oferta entre la lectura y la escritura: la condicion de dynamodb lo detiene
        raise Problema(409, "la campana ya tiene ofertas: no se puede modificar")
    return vista_campana(actualizada)


@app.post("/api/v1/campanas/{campaniaId}/fotos/url")
def pedir_url_foto(campaniaId: uuid.UUID, cuerpo: m.FotoUrlSolicitud, usuario: Usuario = Depends(agricultor), d: Datos = Depends(datos)):
    campania_id = str(campaniaId)
    c = d.obtener("CAMP#" + campania_id, "META")
    if c and c["propietarioSub"] != usuario.sub:
        raise Problema(403, "la campana es de otro agricultor")
    foto_id = str(cuerpo.fotoId)
    clave = "entrada/" + usuario.sub + "/" + campania_id + "/" + foto_id + "." + EXT[cuerpo.tipoContenido]
    firmado = d.url_subida(clave, cuerpo.tipoContenido)
    expira = (datetime.now(timezone.utc) + timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"fotoId": foto_id, "url": firmado["url"], "campos": firmado["fields"], "expiraEn": expira}


@app.get("/api/v1/campanas/{campaniaId}/fotos")
def listar_fotos(campaniaId: uuid.UUID, usuario: Usuario = Depends(cualquiera), d: Datos = Depends(datos)):
    campania_id = str(campaniaId)
    c = d.obtener("CAMP#" + campania_id, "META")
    if c:
        if not visible(c, usuario):
            raise Problema(404, "la campana no existe o no es visible")
        dueno = c["propietarioSub"]
    elif usuario.rol == "agricultor":
        #la foto puede subirse antes de publicar: el agricultor ve las suyas
        dueno = usuario.sub
    else:
        raise Problema(404, "la campana no existe o aun se esta procesando")
    salida = []
    for f in d.todos("CAMP#" + campania_id, "FOTO#"):
        if f.get("propietarioSub") != dueno:
            continue
        procesada = f.get("estado") in ("ETIQUETADA", "SIN_ETIQUETA") and f.get("s3Key")
        salida.append({"fotoId": f["fotoId"], "campaniaId": campania_id, "estado": f["estado"], "label": f.get("label"),
                       "url": d.url_lectura(f["s3Key"]) if procesada else None, "creadoEn": f["creadoEn"]})
    return salida


#ofertas
@app.get("/api/v1/campanas/{campaniaId}/ofertas")
def listar_ofertas_de_campana(campaniaId: uuid.UUID, cursor: Optional[str] = None, limite: int = Query(20, ge=1, le=50),
                              usuario: Usuario = Depends(cualquiera), d: Datos = Depends(datos)):
    c = campana_o_404(d, str(campaniaId))
    if not visible(c, usuario):
        raise Problema(404, "la campana no existe o no es visible")
    items, siguiente = d.consultar("CAMP#" + str(campaniaId), "OFFER#", limite, cursor)
    if c["propietarioSub"] != usuario.sub:
        items = [o for o in items if o["compradorSub"] == usuario.sub]
    return lista([vista_oferta(o) for o in items], siguiente)


@app.post("/api/v1/campanas/{campaniaId}/ofertas", status_code=202)
def crear_oferta(campaniaId: uuid.UUID, cuerpo: m.OfertaCrear, usuario: Usuario = Depends(comprador), d: Datos = Depends(datos)):
    campania_id = str(campaniaId)
    oferta_id = str(cuerpo.ofertaId)
    consultar = "/api/v1/campanas/" + campania_id + "/ofertas"
    c = campana_o_404(d, campania_id)
    if c["estado"] != "PUBLICADA":
        raise Problema(404, "la campana no esta publicada")
    if c["propietarioSub"] == usuario.sub:
        raise Problema(403, "no puedes ofertar sobre tu propia campana")
    existente = d.obtener("CAMP#" + campania_id, "OFFER#" + oferta_id)
    if existente:
        if existente["compradorSub"] != usuario.sub:
            raise Problema(409, "el identificador de oferta ya existe")
        return aceptado(oferta_id, consultar)
    if cuerpo.volumenKg > c["volumenKg"]:
        raise Problema(422, "el volumen supera el de la campana (" + str(c["volumenKg"]) + " kg)")
    precio = a_centimos(cuerpo.precioPorKg)
    if precio <= 0:
        raise Problema(422, "el precio debe ser mayor a 0")
    if cuerpo.fechaEntrega < hoy_lima():
        raise Problema(422, "la fecha de entrega no puede estar en el pasado")
    perfil = perfil_o_403(d, usuario)
    creado = ahora_iso()
    item = {
        "PK": "CAMP#" + campania_id, "SK": "OFFER#" + oferta_id, "entidad": "OFERTA", "ofertaId": oferta_id,
        "campaniaId": campania_id, "compradorSub": usuario.sub, "compradorNombre": perfil.get("razonSocial", ""),
        "volumenKg": cuerpo.volumenKg, "precioCentimosPorKg": precio, "modalidad": cuerpo.modalidad,
        "logistica": cuerpo.logistica, "fechaEntrega": cuerpo.fechaEntrega.isoformat(),
        "totalCentimos": cuerpo.volumenKg * precio, "estado": "PENDIENTE", "creadoEn": creado,
        "cultivo": c["cultivo"], "productorNombre": c["productorNombre"], "departamento": c["departamento"],
        "usuarioClave": "USER#" + usuario.sub, "usuarioOrden": "OFFER#" + creado + "#" + oferta_id,
    }
    d.encolar("oferta", item)
    return aceptado(oferta_id, consultar)


@app.get("/api/v1/ofertas")
def listar_mis_ofertas(cursor: Optional[str] = None, limite: int = Query(20, ge=1, le=50),
                       usuario: Usuario = Depends(comprador), d: Datos = Depends(datos)):
    items, siguiente = d.consultar("USER#" + usuario.sub, "OFFER#", limite, cursor, adelante=False, indice="por-usuario")
    return lista([vista_oferta(o) for o in items], siguiente)
