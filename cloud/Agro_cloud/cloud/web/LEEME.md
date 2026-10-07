# cloud/web

- `Dockerfile`, `nginx.conf`, `40-salud.sh`, `.dockerignore`: imagen nginx de la web.
- La web que se despliega es `web/` en la raiz del proyecto (v05). `tareas.py desplegar` arma el contexto de Docker en `cloud/.construccion/contexto-web` con estos archivos + `web/` como `sitio/`.
