# AgroCredit en AWS — Proyecto Parcial de Cloud Computing (UTEC Posgrado)

**Informe del proyecto: [`docs/PROYECTO-PARCIAL.md`](docs/PROYECTO-PARCIAL.md)** (analisis, diseno, implementacion y evidencia).

PoC academico (curso de cloud computing): web AgroCredit v05 (agricultor y comprador) desplegada en AWS con Terraform, todo automatizado con `cloud/tareas.py`. Datos 100% ficticios (Ley 29733).

## Que hay
| Carpeta | Contenido |
|---|---|
| `web/` | La web que se despliega (v05): pantallas, `assets/agro.js`, logo, design-system propio |
| `cloud/` | API (FastAPI), Lambdas, Terraform, datos semilla y `tareas.py` |
| `Conexion/` | Entorno de Python y credenciales del lab |
| `docs/` | Informe del proyecto, benchmark, catalogo de APIs (`api/agrocredit-api.html`), colecciones Postman y Bruno, base de datos, costos y guia de marca |
| `arquitectura/` | Diagramas de arquitectura en AWS (PNG/SVG con iconos oficiales) y Mermaid |

## Arranque (Mac; en Windows usar `python` y los `.ps1`)
Requisitos: Python 3.9+, Docker Desktop abierto, cuenta AWS Academy Learner Lab.
```bash
cd Conexion
bash ./preparar.sh                          #una vez: crea .venv con awscli y boto3
cp credenciales.ejemplo.txt credenciales.txt
#pega en credenciales.txt el bloque "AWS CLI" de AWS Details (cada sesion del lab)

cd ../cloud
python tareas.py preparar                   #una vez: descarga terraform 1.16.5
python tareas.py init                       #una vez o si cambia la cuenta del lab
python tareas.py desplegar                  #pruebas + imagenes + terraform + datos iniciales
python tareas.py probar                     #imprime la url de la web y del estado del servicio
python tareas.py destruir                   #al terminar; escribir agro-
```
Las tareas se apagan solas 2 horas despues de desplegar (`python tareas.py encender` para volver). El balanceador cobra hasta que corras `destruir`.

## Reglas
- Credenciales solo en `Conexion/credenciales.txt` (no se comparte; esta en `.gitignore`).
- Solo se tocan recursos AWS con prefijo `agro-`.
- Todo cambio de API empieza en `cloud/api/openapi.yaml`.

Detalle completo: [`docs/PROYECTO-PARCIAL.md`](docs/PROYECTO-PARCIAL.md).
