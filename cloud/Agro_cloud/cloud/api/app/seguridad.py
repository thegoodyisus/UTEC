#validacion del id token de cognito: firma (jwks), emisor, audiencia, vencimiento, token_use y rol
import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .errores import Problema

ROLES = ("agricultor", "comprador")
portador = HTTPBearer(auto_error=False)


@dataclass
class Usuario:
    sub: str
    rol: str
    correo: str = ""
    documento: str = ""


class Verificador:
    def __init__(self, pool_id, client_id, region, jwks=None):
        self.emisor = "https://cognito-idp." + region + ".amazonaws.com/" + pool_id
        self.client_id = client_id
        self.jwks = jwks or jwt.PyJWKClient(self.emisor + "/.well-known/jwks.json", cache_keys=True, lifespan=3600)

    def verificar(self, token):
        try:
            clave = self.jwks.get_signing_key_from_jwt(token).key
            datos = jwt.decode(token, clave, algorithms=["RS256"], audience=self.client_id, issuer=self.emisor,
                               options={"require": ["exp", "iat", "sub", "token_use"]})
        except (jwt.PyJWTError, ValueError) as e:
            raise Problema(401, "token invalido: " + type(e).__name__)
        if datos.get("token_use") != "id":
            raise Problema(401, "se requiere el id token de cognito")
        rol = datos.get("custom:rol")
        #cognito no restringe el valor de custom:rol: se valida aqui
        if rol not in ROLES:
            raise Problema(403, "rol no permitido")
        return Usuario(sub=datos["sub"], rol=rol, correo=datos.get("email", ""), documento=datos.get("cognito:username", ""))


@lru_cache(maxsize=1)
def verificador():
    pool = os.environ.get("USER_POOL_ID", "")
    cliente = os.environ.get("CLIENT_ID", "")
    if not pool or not cliente:
        raise Problema(503, "configuracion de cognito incompleta")
    return Verificador(pool, cliente, os.environ.get("REGION_AWS", "us-east-1"))


def usuario_actual(credenciales: HTTPAuthorizationCredentials = Depends(portador)) -> Usuario:
    if credenciales is None or credenciales.scheme.lower() != "bearer":
        raise Problema(401, "falta el token bearer")
    return verificador().verificar(credenciales.credentials)


def exigir_rol(*roles):
    def dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if usuario.rol not in roles:
            raise Problema(403, "esta operacion es solo para " + " o ".join(roles))
        return usuario
    return dependencia
