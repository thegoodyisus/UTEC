#api de agrocredit (fastapi) segun openapi.yaml
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
#los archivos pueden venir con permisos 600 desde el equipo: el usuario 10001 debe poder leerlos
RUN chmod -R a+rX /srv
#usuario sin privilegios; sin --system porque el uid supera el rango de sistema
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "5"]
