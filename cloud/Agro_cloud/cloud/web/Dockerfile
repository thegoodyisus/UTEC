#web estatica de agrocredit servida por nginx (arm64 lo elige docker build --platform)
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY sitio/ /usr/share/nginx/html/
#los archivos pueden venir con permisos 600 desde el equipo: nginx debe poder leerlos
RUN chmod -R a+rX /usr/share/nginx/html /etc/nginx/conf.d
#al arrancar se genera salud-web.json con el id de tarea y la zona
COPY 40-salud.sh /docker-entrypoint.d/40-salud.sh
RUN chmod 755 /docker-entrypoint.d/40-salud.sh
