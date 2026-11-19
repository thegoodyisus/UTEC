"""Cliente minimo de Groq con urllib (patron de S11 y S12), SIN historial: cada llamada lleva solo su mensaje.

Diferencias con el ejemplo del curso (a proposito):
- No imprime cabeceras ni el contenido (el ejemplo imprimia el Bearer con la clave en CloudWatch).
- No reintenta adentro: lanza GroqReintentable (429, 5xx, timeout) y Step Functions hace el Retry.
- Mantiene el User-Agent de navegador del ejemplo (el de urllib puede ser bloqueado; inferencia no probada).
"""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://api.groq.com/openai/v1/chat/completions"
MODELO = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")


class GroqReintentable(Exception):
    """429, 5xx o falla de red: Step Functions reintenta."""


class GroqRespuestaInvalida(Exception):
    """Groq respondio, pero no con el JSON esperado: Step Functions reintenta."""


class GroqError(Exception):
    """Error no reintentable (por ejemplo 400 o 401)."""


def _llamar(mensajes, max_tokens, timeout, json_obj, temperatura):
    clave = os.environ.get("GROQ_API_KEY", "")
    if not clave:
        raise GroqError("GROQ_API_KEY no configurada")
    payload = {"model": MODELO, "messages": mensajes, "temperature": temperatura,
               "max_completion_tokens": max_tokens, "reasoning_effort": "low"}
    if json_obj:
        payload["response_format"] = {"type": "json_object"}
    req = Request(URL, data=json.dumps(payload).encode("utf-8"), method="POST",
                  headers={"Authorization": "Bearer " + clave, "Content-Type": "application/json", "User-Agent": UA})
    try:
        with urlopen(req, timeout=timeout) as r:
            datos = json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 429 or e.code >= 500:
            raise GroqReintentable("HTTP %d" % e.code)
        raise GroqError("HTTP %d" % e.code)
    except (URLError, TimeoutError) as e:
        raise GroqReintentable(type(e).__name__)
    contenido = ((datos.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return contenido.strip(), (datos.get("usage") or {}).get("total_tokens")


def completar_json(sistema, usuario, max_tokens=1500, timeout=20):
    contenido, tokens = _llamar([{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                                max_tokens, timeout, True, 0)
    try:
        obj = json.loads(contenido)
    except json.JSONDecodeError:
        raise GroqRespuestaInvalida("no es JSON")
    if not isinstance(obj, dict):
        raise GroqRespuestaInvalida("no es objeto")
    return obj, tokens


def completar_texto(sistema, usuario, max_tokens=800, timeout=15):
    return _llamar([{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
                   max_tokens, timeout, False, 0.3)
