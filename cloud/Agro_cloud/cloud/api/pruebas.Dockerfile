#imagen para correr las pruebas de la api (el codigo se monta al ejecutar, no se copia)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt requirements-pruebas.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-pruebas.txt
CMD ["pytest", "-q", "-p", "no:cacheprovider", "pruebas"]
