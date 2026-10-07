# Coleccion de pruebas AgroCredit (Thunder Client y Postman)

Generado por `cloud/api/coleccion.py` desde `cloud/api/openapi.yaml` v1.6.0. No editar a mano: correr `python coleccion.py` en `cloud/api/` (o `python tareas.py documentar` y luego este script).

## Archivos
| Archivo | Para que |
|---|---|
| `thunder-collection_AgroCredit.json`, `thunder-environment_agrocredit.json` | Importar en Thunder Client (**la importacion es de la version de pago**) |
| `agrocredit.postman_collection.json`, `agrocredit.postman_environment.json` | Importar en Postman (gratis) o en Thunder Client de pago |
| `cuerpos/NN.json` | Cuerpo de cada peticion para pegar a mano en Thunder Client gratis (pestana Body > JSON) |

## Antes de empezar
1. Desplegar y correr `python tareas.py probar`; copiar el DNS de la linea `web:` y armar `baseUrl` = `http://<dns>/api/v1`.
2. Crear dos cuentas en la web (agricultor con un DNI y comprador con un RUC, ficticios) e iniciar sesion con cada una.
3. Sacar el ID token de cada sesion: en el navegador, con la web abierta y la sesion iniciada, abrir las herramientas de desarrollador (F12) > Consola y ejecutar:

```js
Object.entries(localStorage).find(([k]) => k.endsWith('.idToken'))[1]
```

   Copiar el texto (sin comillas) en `tokenAgricultor` o `tokenComprador`. Dura 60 minutos. Usar una ventana privada para la segunda cuenta.
4. En Thunder Client gratis: crear el entorno `agrocredit` con las variables de abajo y crear cada peticion a mano con el metodo, la URL, Auth > Bearer `{{tokenAgricultor}}` o `{{tokenComprador}}` y el cuerpo de `cuerpos/`.
5. Ejecutar en orden. Si el perfil ya se creo desde la web, `Crear mi perfil` responde 409 (correcto: no se duplica).

`{{#guid}}` (Thunder) y `{{$guid}}` (Postman) generan un UUID nuevo en cada envio: es el id de idempotencia que en la web genera el navegador. En Thunder gratis, si la prueba no guarda la variable, copiar `recursoId` de la respuesta a `campaniaId` (o `ofertaId`) a mano.

## Variables del entorno
| Variable | Que es |
|---|---|
| `baseUrl` | copiar la linea web: de python tareas.py probar y dejar solo http://<dns>/api/v1 |
| `tokenAgricultor` | ID token de una sesion de agricultor (ver LEEME) |
| `tokenComprador` | ID token de una sesion de comprador (ver LEEME) |
| `dniAgricultor` | DNI con que se creo la cuenta del agricultor (ficticio) |
| `rucComprador` | RUC con que se creo la cuenta del comprador (ficticio) |
| `dniRepresentante` | DNI ficticio del representante del comprador |
| `campaniaId` | lo llena la prueba de Registrar campana |
| `ofertaId` | lo llena la prueba de Enviar oferta |
| `fotoId` | lo llena la prueba de Pedir URL de foto |

## Peticiones en orden
| # | Peticion | API | Token | Cuerpo | Microservicio | Tabla o servicio | Esperado |
|---|---|---|---|---|---|---|---|
| 01 | Chequeo de salud | `GET /salud` | sin token | - | Plataforma | memoria de la tarea ECS (sin tabla) | 200 |
| 02 | Configuracion de inicio de sesion | `GET /config` | sin token | - | Identidad y perfil | variables de entorno de la tarea: ids de Cognito (sin tabla) | 200 |
| 03 | Crear mi perfil (agricultor) | `POST /perfil` | tokenAgricultor | `cuerpos/03.json` | Identidad y perfil | agro-datos | 201 |
| 04 | Consultar mi perfil | `GET /perfil` | tokenAgricultor | - | Identidad y perfil | agro-datos | 200 |
| 05 | Catalogo de cultivos | `GET /catalogo/cultivos` | tokenAgricultor | - | Padron y catalogos | agro-datos | 200 |
| 06 | Registrar campana (insert por cola) | `POST /campanas` | tokenAgricultor | `cuerpos/06.json` | Campanas y fotos | SQS agro-insercion -> Lambda agro-worker -> agro-datos | 202 |
| 07 | Ver campana (repetir hasta 200) | `GET /campanas/{campaniaId}` | tokenAgricultor | - | Campanas y fotos | agro-datos | 200 |
| 08 | Mis campanas | `GET /campanas` | tokenAgricultor | - | Campanas y fotos | agro-datos (indice por-usuario) | 200 |
| 09 | Actualizar campana (update directo, sin ofertas) | `PATCH /campanas/{campaniaId}` | tokenAgricultor | `cuerpos/09.json` | Campanas y fotos | agro-datos | 200 |
| 10 | Pedir URL para subir foto | `POST /campanas/{campaniaId}/fotos/url` | tokenAgricultor | `cuerpos/10.json` | Campanas y fotos | S3 agro-fotos -> SQS agro-fotos -> Lambda agro-etiquetar -> Rekognition -> agro-datos | 200 |
| 11 | Ver fotos de la campana | `GET /campanas/{campaniaId}/fotos` | tokenAgricultor | - | Campanas y fotos | agro-datos + S3 agro-fotos | 200 |
| 12 | Consultar padron (empresa por RUC) | `POST /padron/consulta` | tokenComprador | `cuerpos/12.json` | Padron y catalogos | agro-padron-empresas o agro-padron-personas + agro-datos | 200 |
| 13 | Consultar padron (representante por DNI) | `POST /padron/consulta` | tokenComprador | `cuerpos/13.json` | Padron y catalogos | agro-padron-empresas o agro-padron-personas + agro-datos | 200 |
| 14 | Cuentas de prueba | `GET /cuentas-demo` | tokenComprador | - | Padron y catalogos | agro-datos | 200 |
| 15 | Crear mi perfil (comprador) | `POST /perfil` | tokenComprador | `cuerpos/15.json` | Identidad y perfil | agro-datos | 201 |
| 16 | Buscar campanas publicadas (papa, Cusco) | `GET /campanas/publicadas` | tokenComprador | - | Campanas y fotos | agro-datos (indice publicadas-por-cultivo) | 200 |
| 17 | Ver campana publicada | `GET /campanas/{campaniaId}` | tokenComprador | - | Campanas y fotos | agro-datos | 200 |
| 18 | Enviar oferta (insert por cola) | `POST /campanas/{campaniaId}/ofertas` | tokenComprador | `cuerpos/18.json` | Ofertas | SQS agro-insercion -> Lambda agro-worker -> agro-datos | 202 |
| 19 | Mis ofertas (repetir hasta que aparezca) | `GET /ofertas` | tokenComprador | - | Ofertas | agro-datos (indice por-usuario) | 200 |
| 20 | Ofertas recibidas en mi campana | `GET /campanas/{campaniaId}/ofertas` | tokenAgricultor | - | Ofertas | agro-datos | 200 |
| 21 | Ver campana (numeroOfertas = 1) | `GET /campanas/{campaniaId}` | tokenAgricultor | - | Campanas y fotos | agro-datos | 200 |
| 22 | Actualizar campana con ofertas (debe dar 409) | `PATCH /campanas/{campaniaId}` | tokenAgricultor | `cuerpos/22.json` | Campanas y fotos | agro-datos | 409 |
| 23 | Registrar campana sin token | `POST /campanas` | sin token | `cuerpos/23.json` | Campanas y fotos | SQS agro-insercion -> Lambda agro-worker -> agro-datos | 401 |
| 24 | Comprador intenta registrar campana | `POST /campanas` | tokenComprador | `cuerpos/24.json` | Campanas y fotos | SQS agro-insercion -> Lambda agro-worker -> agro-datos | 403 |
| 25 | Agricultor intenta ofertar | `POST /campanas/{campaniaId}/ofertas` | tokenAgricultor | `cuerpos/25.json` | Ofertas | SQS agro-insercion -> Lambda agro-worker -> agro-datos | 403 |

Las escrituras asincronas (202) no escriben en la tabla al responder: la API deja el mensaje en SQS y la Lambda `agro-worker` escribe en `agro-datos` en 1 a 2 segundos. Por eso `Ver campana` y `Mis ofertas` pueden dar 404 o lista vacia la primera vez: repetir.

## Que tabla o servicio toca cada API
| API | Microservicio | Tipo | Tabla o servicio | Operacion |
|---|---|---|---|---|
| `GET /salud` | Plataforma | lectura | memoria de la tarea ECS (sin tabla) | - |
| `GET /config` | Identidad y perfil | lectura | variables de entorno de la tarea: ids de Cognito (sin tabla) | - |
| `POST /perfil` | Identidad y perfil | escritura directa | agro-datos | PutItem USER#<sub> / PROFILE (condicion attribute_not_exists); lee CATALOGO o CUENTA_DEMO para validar |
| `GET /perfil` | Identidad y perfil | lectura | agro-datos | GetItem USER#<sub> / PROFILE |
| `GET /catalogo/cultivos` | Padron y catalogos | lectura | agro-datos | Query PK=CATALOGO, SK empieza con CULTIVO# |
| `POST /padron/consulta` | Padron y catalogos | escritura directa (transaccion) | agro-padron-empresas o agro-padron-personas + agro-datos | Scan consistente + TransactWriteItems: Delete del registro del padron + Put USER#<sub> / PADRON#<uso>#<tipoDoc> |
| `GET /cuentas-demo` | Padron y catalogos | lectura | agro-datos | Query PK=CUENTA_DEMO |
| `POST /campanas` | Campanas y fotos | escritura asincrona | SQS agro-insercion -> Lambda agro-worker -> agro-datos | la api lee CATALOGO y PROFILE y encola; el worker hace PutItem CAMP#<id> / META con indices por-usuario y publicadas-por-cultivo |
| `GET /campanas/{campaniaId}` | Campanas y fotos | lectura | agro-datos | GetItem CAMP#<id> / META |
| `PATCH /campanas/{campaniaId}` | Campanas y fotos | actualizacion directa | agro-datos | UpdateItem CAMP#<id> / META con condicion attribute_exists(PK) AND propietarioSub = <sub> AND numeroOfertas = 0 |
| `GET /campanas` | Campanas y fotos | lectura | agro-datos (indice por-usuario) | Query usuarioClave=USER#<sub>, usuarioOrden empieza con CAMP# |
| `POST /campanas/{campaniaId}/fotos/url` | Campanas y fotos | escritura asincrona | S3 agro-fotos -> SQS agro-fotos -> Lambda agro-etiquetar -> Rekognition -> agro-datos | la api firma un POST a entrada/<sub>/<campana>/<foto>; la lambda registra CAMP#<id> / FOTO#<fotoId> |
| `GET /campanas/{campaniaId}/fotos` | Campanas y fotos | lectura | agro-datos + S3 agro-fotos | Query PK=CAMP#<id>, SK empieza con FOTO#; URL de lectura temporal |
| `GET /campanas/publicadas` | Campanas y fotos | lectura | agro-datos (indice publicadas-por-cultivo) | Query publicadaClave=PUB#<cultivo>#<departamento> |
| `POST /campanas/{campaniaId}/ofertas` | Ofertas | escritura asincrona | SQS agro-insercion -> Lambda agro-worker -> agro-datos | la api lee META y PROFILE y encola; el worker hace TransactWriteItems: Put CAMP#<id> / OFFER#<id> + Update META numeroOfertas |
| `GET /ofertas` | Ofertas | lectura | agro-datos (indice por-usuario) | Query usuarioClave=USER#<sub>, usuarioOrden empieza con OFFER# |
| `GET /campanas/{campaniaId}/ofertas` | Ofertas | lectura | agro-datos | Query PK=CAMP#<id>, SK empieza con OFFER# |

Evidencia en la base: despues de `Registrar campana` y `Enviar oferta`, consultar `agro-datos` con las consultas de `docs/base-datos/agrocredit-base-datos.md` (PartiQL en la consola de DynamoDB).
