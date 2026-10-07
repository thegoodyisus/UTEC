#validacion del id token con una clave rsa local (sin cognito real)
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.errores import Problema
from app.seguridad import Verificador

CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
POOL, CLIENTE = "us-east-1_prueba", "cliente-prueba"
EMISOR = "https://cognito-idp.us-east-1.amazonaws.com/" + POOL


class JwksFalso:
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=CLAVE.public_key())


def token(**cambios):
    ahora = int(time.time())
    datos = {"sub": "u-1", "aud": CLIENTE, "iss": EMISOR, "exp": ahora + 600, "iat": ahora, "token_use": "id", "custom:rol": "comprador"}
    datos.update(cambios)
    return jwt.encode(datos, CLAVE, algorithm="RS256")


def verificar(t):
    return Verificador(POOL, CLIENTE, "us-east-1", jwks=JwksFalso()).verificar(t)


def test_token_valido():
    u = verificar(token())
    assert u.sub == "u-1" and u.rol == "comprador"


@pytest.mark.parametrize("cambios,estado", [
    ({"aud": "otro-cliente"}, 401),
    ({"iss": "https://otro-emisor"}, 401),
    ({"exp": int(time.time()) - 10}, 401),
    ({"token_use": "access"}, 401),
    ({"custom:rol": "admin"}, 403),
    ({"custom:rol": None}, 403),
])
def test_tokens_rechazados(cambios, estado):
    with pytest.raises(Problema) as e:
        verificar(token(**cambios))
    assert e.value.estado == estado


def test_firma_de_otra_clave():
    otra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    t = jwt.encode({"sub": "u", "aud": CLIENTE, "iss": EMISOR, "exp": int(time.time()) + 60, "iat": int(time.time()), "token_use": "id"}, otra, algorithm="RS256")
    with pytest.raises(Problema) as e:
        verificar(t)
    assert e.value.estado == 401
