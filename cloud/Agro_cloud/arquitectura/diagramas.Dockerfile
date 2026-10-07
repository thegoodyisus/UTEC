#imagen para generar los diagramas con iconos oficiales de aws (libreria diagrams + graphviz)
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends graphviz fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir diagrams==0.25.1
WORKDIR /trabajo
