#genera docs/base-datos/agrocredit-base-datos.md con los graficos er-relacional.png y dynamodb-modelo.png
#uso (desde docs/base-datos/, con docker; reutiliza la imagen de arquitectura/diagramas.Dockerfile):
#  docker run --rm -v "$PWD/../..":/trabajo -w /trabajo/docs/base-datos agro-diagramas:0.25.1 python generar.py
import html
import json
from pathlib import Path

from graphviz import Digraph

AQUI = Path(__file__).resolve().parent
API_TABLAS = AQUI.parent / "api" / "thunder" / "api-tablas.json"
e = html.escape

#colores v05
OSCURO, PRIMARIO, HOJA, MENTA, SUAVE = "#0A3C37", "#135C40", "#418E49", "#D8F9E1", "#A5D1C2"

#modelo conceptual relacional: entidad -> (origen, [(campo, tipo, marca)])
ENTIDADES = {
    "USUARIO": ("Cognito", [("sub", "uuid", "PK"), ("documento", "varchar(11)", "UK"), ("correo", "varchar", ""), ("rol", "agricultor|comprador", "")]),
    "PERFIL_AGRICULTOR": ("agro-datos", [("sub", "uuid", "PK FK"), ("nombres", "varchar", ""), ("apellidos", "varchar", ""), ("tipoDoc", "DNI", ""),
                                          ("documento", "char(8)", ""), ("celular", "char(9)", ""), ("correo", "varchar", ""),
                                          ("departamento", "varchar", ""), ("provincia", "varchar", ""), ("distrito", "varchar", ""), ("creadoEn", "timestamp", "")]),
    "PERFIL_COMPRADOR": ("agro-datos", [("sub", "uuid", "PK FK"), ("tipoDoc", "RUC|DNI", ""), ("documento", "varchar(11)", ""),
                                         ("razonSocial", "varchar", ""), ("contactoNombre", "varchar", ""), ("contactoCelular", "char(9)", ""),
                                         ("contactoCorreo", "varchar", ""), ("contactoCargo", "varchar", ""), ("cuentaCargoId", "varchar", "FK"),
                                         ("modalidadPago", "recibir", ""), ("creadoEn", "timestamp", "")]),
    "AGRICULTOR_CULTIVO": ("agro-datos", [("sub", "uuid", "PK FK"), ("slug", "varchar", "PK FK")]),
    "CULTIVO": ("agro-datos", [("slug", "varchar", "PK"), ("nombre", "varchar", ""), ("orden", "int", ""),
                               ("referenciaMercadoCentimosPorKg", "int", ""), ("etiquetasRekognition", "varchar[]", "")]),
    "CAMPANA": ("agro-datos", [("campaniaId", "uuid", "PK"), ("propietarioSub", "uuid", "FK"), ("cultivo", "varchar", "FK"),
                               ("departamento", "varchar", ""), ("provincia", "varchar", ""), ("distrito", "varchar", ""),
                               ("cosecha", "date", ""), ("volumenKg", "int", ""), ("logistica", "Recojo|Envio", ""),
                               ("capitalCentimos", "bigint", ""), ("precioAhoraCentimosPorKg", "int", ""),
                               ("precioContraentregaCentimosPorKg", "int", ""), ("estado", "PUBLICADA", ""),
                               ("numeroOfertas", "int", ""), ("creadoEn", "timestamp", "")]),
    "FOTO": ("agro-datos + S3", [("fotoId", "uuid", "PK"), ("campaniaId", "uuid", "FK"), ("propietarioSub", "uuid", "FK"),
                                 ("s3Key", "varchar", ""), ("label", "varchar", ""), ("labelConfianza", "numeric", ""),
                                 ("estado", "varchar", ""), ("creadoEn", "timestamp", "")]),
    "OFERTA": ("agro-datos", [("ofertaId", "uuid", "PK"), ("campaniaId", "uuid", "FK"), ("compradorSub", "uuid", "FK"),
                              ("volumenKg", "int", ""), ("precioCentimosPorKg", "int", ""), ("totalCentimos", "bigint", ""),
                              ("modalidad", "varchar", ""), ("logistica", "varchar", ""), ("fechaEntrega", "date", ""),
                              ("estado", "PENDIENTE", ""), ("creadoEn", "timestamp", "")]),
    "CUENTA_DEMO": ("agro-datos", [("id", "varchar", "PK"), ("titulo", "varchar", ""), ("descripcion", "varchar", ""), ("orden", "int", "")]),
    "ASIGNACION_PADRON": ("agro-datos", [("sub", "uuid", "PK FK"), ("uso", "comprador|representante", "PK"), ("tipoDoc", "RUC|DNI", "PK"),
                                          ("origen", "varchar", "FK"), ("datos", "json", ""), ("creadoEn", "timestamp", "")]),
    "PADRON_EMPRESA": ("agro-padron-empresas", [("id", "varchar", "PK"), ("razonSocial", "varchar", ""), ("direccionFiscal", "varchar", ""),
                                                 ("actividad", "varchar", ""), ("estado", "varchar", "")]),
    "PADRON_PERSONA": ("agro-padron-personas", [("id", "varchar", "PK"), ("nombres", "varchar", ""), ("apellidos", "varchar", ""),
                                                 ("celular", "char(9)", ""), ("correo", "varchar", "")]),
}

#(desde, hacia, cardinalidad del lado desde, del lado hacia, etiqueta)
RELACIONES = [
    ("USUARIO", "PERFIL_AGRICULTOR", "1", "0..1", "tiene"),
    ("USUARIO", "PERFIL_COMPRADOR", "1", "0..1", "tiene"),
    ("PERFIL_AGRICULTOR", "AGRICULTOR_CULTIVO", "1", "1..N", "siembra"),
    ("CULTIVO", "AGRICULTOR_CULTIVO", "1", "0..N", ""),
    ("PERFIL_AGRICULTOR", "CAMPANA", "1", "0..N", "registra"),
    ("CULTIVO", "CAMPANA", "1", "0..N", "de"),
    ("CAMPANA", "FOTO", "1", "0..N", "tiene"),
    ("CAMPANA", "OFERTA", "1", "0..N", "recibe"),
    ("PERFIL_COMPRADOR", "OFERTA", "1", "0..N", "envia"),
    ("CUENTA_DEMO", "PERFIL_COMPRADOR", "1", "0..N", "cuenta de cargo"),
    ("USUARIO", "ASIGNACION_PADRON", "1", "0..2", "recibe"),
    ("PADRON_EMPRESA", "ASIGNACION_PADRON", "1", "0..1", "se asigna"),
    ("PADRON_PERSONA", "ASIGNACION_PADRON", "1", "0..1", "se asigna"),
]

FLECHA = {"1": "tee", "0..1": "teeodot", "1..N": "crowtee", "0..N": "crowodot", "0..2": "crowodot"}


def diagrama_er():
    g = Digraph("er", format="svg")
    g.attr(rankdir="LR", splines="spline", nodesep="0.5", ranksep="1.0", fontname="DejaVu Sans", bgcolor="white", pad="0.3")
    g.attr("node", shape="plaintext", fontname="DejaVu Sans", fontsize="10")
    g.attr("edge", fontname="DejaVu Sans", fontsize="9", color=PRIMARIO, dir="both")
    for nombre, (origen, campos) in ENTIDADES.items():
        color = SUAVE if origen == "Cognito" else (MENTA if origen.startswith("agro-padron") else "#FFFFFF")
        filas = "".join(
            '<TR><TD ALIGN="LEFT" PORT="%s">%s%s</TD><TD ALIGN="LEFT"><FONT COLOR="#5f6368">%s</FONT></TD></TR>'
            % (c, ("<B>%s</B> " % m if m else ""), e(c), e(t)) for c, t, m in campos)
        g.node(nombre, "<<TABLE BORDER=\"1\" CELLBORDER=\"0\" CELLSPACING=\"0\" CELLPADDING=\"3\" BGCOLOR=\"%s\" COLOR=\"%s\">"
                       "<TR><TD COLSPAN=\"2\" BGCOLOR=\"%s\"><FONT COLOR=\"white\"><B>%s</B></FONT></TD></TR>"
                       "<TR><TD COLSPAN=\"2\"><FONT POINT-SIZE=\"8\" COLOR=\"%s\">%s</FONT></TD></TR>%s</TABLE>>"
               % (color, OSCURO, OSCURO, nombre, HOJA, e(origen), filas))
    for a, b, ca, cb, etq in RELACIONES:
        g.edge(a, b, arrowtail=FLECHA[ca], arrowhead=FLECHA[cb], label=" %s %s:%s " % (etq, ca, cb))
    (AQUI / "er-relacional.svg").write_bytes(g.pipe(format="svg"))
    g.render(filename=str(AQUI / "er-relacional"), format="png", cleanup=True)


def diagrama_dynamo():
    #modelo real: 3 tablas, claves, indices y tipos de item de la tabla unica
    g = Digraph("dynamo", format="png")
    g.attr(rankdir="LR", nodesep="0.4", ranksep="0.9", fontname="DejaVu Sans", bgcolor="white", pad="0.3", dpi="140")
    g.attr("node", shape="plaintext", fontname="DejaVu Sans", fontsize="10")
    g.attr("edge", fontname="DejaVu Sans", fontsize="9", color=PRIMARIO)

    def caja(nombre, subtitulo, filas, fondo="#FFFFFF"):
        cuerpo = "".join('<TR><TD ALIGN="LEFT">%s</TD><TD ALIGN="LEFT"><FONT COLOR="#5f6368">%s</FONT></TD></TR>' % (e(a), e(b)) for a, b in filas)
        return ("<<TABLE BORDER=\"1\" CELLBORDER=\"0\" CELLSPACING=\"0\" CELLPADDING=\"4\" BGCOLOR=\"%s\" COLOR=\"%s\">"
                "<TR><TD COLSPAN=\"2\" BGCOLOR=\"%s\"><FONT COLOR=\"white\"><B>%s</B></FONT></TD></TR>"
                "<TR><TD COLSPAN=\"2\"><FONT POINT-SIZE=\"8\" COLOR=\"%s\">%s</FONT></TD></TR>%s</TABLE>>"
                % (fondo, OSCURO, OSCURO, e(nombre), HOJA, e(subtitulo), cuerpo))

    g.node("datos", caja("agro-datos", "on-demand, PK + SK (texto), cifrado de AWS", [
        ("USER#<sub> / PROFILE", "perfil agricultor o comprador"),
        ("USER#<sub> / PADRON#<uso>#<tipoDoc>", "asignacion del padron"),
        ("CAMP#<id> / META", "campana"),
        ("CAMP#<id> / FOTO#<fotoId>", "foto etiquetada"),
        ("CAMP#<id> / OFFER#<ofertaId>", "oferta"),
        ("CATALOGO / CULTIVO#<slug>", "catalogo de cultivos"),
        ("CUENTA_DEMO / CUENTA#<id>", "cuentas de prueba"),
        ("SIEMBRA / PADRON", "marca de carga inicial")]))
    g.node("gsi1", caja("indice por-usuario", "GSI, proyeccion ALL", [
        ("usuarioClave (HASH)", "USER#<sub>"), ("usuarioOrden (RANGE)", "CAMP#<fecha>#<id> u OFFER#<fecha>#<id>"),
        ("uso", "mis campanas, mis ofertas")], MENTA))
    g.node("gsi2", caja("indice publicadas-por-cultivo", "GSI disperso, proyeccion ALL", [
        ("publicadaClave (HASH)", "PUB#<cultivo>#<departamento>"), ("publicadaOrden (RANGE)", "<cosecha>#<id>"),
        ("uso", "busqueda del comprador")], MENTA))
    g.node("empresas", caja("agro-padron-empresas", "on-demand, clave id", [("id (HASH)", "e01..e10"), ("razonSocial, direccionFiscal", "ficticios, sin RUC")], SUAVE))
    g.node("personas", caja("agro-padron-personas", "on-demand, clave id", [("id (HASH)", "p01..p10"), ("nombres, apellidos, celular", "ficticios, sin DNI")], SUAVE))
    g.edge("datos", "gsi1", label=" campanas y ofertas ")
    g.edge("datos", "gsi2", label=" solo PUBLICADA ")
    g.edge("empresas", "datos", label=" TransactWriteItems:\n Delete + Put PADRON# ", style="dashed")
    g.edge("personas", "datos", label=" TransactWriteItems:\n Delete + Put PADRON# ", style="dashed")
    g.render(filename=str(AQUI / "dynamodb-modelo"), format="png", cleanup=True)


DDL = """-- equivalente relacional (PostgreSQL) solo para explicar el modelo; NO se despliega
CREATE TABLE usuario (            -- vive en Amazon Cognito, no en la base
  sub uuid PRIMARY KEY, documento varchar(11) UNIQUE NOT NULL, correo varchar NOT NULL,
  rol varchar(10) NOT NULL CHECK (rol IN ('agricultor','comprador')));
CREATE TABLE cultivo (slug varchar PRIMARY KEY, nombre varchar NOT NULL, orden int,
  referencia_mercado_centimos_por_kg int NOT NULL, etiquetas_rekognition varchar[]);
CREATE TABLE cuenta_demo (id varchar PRIMARY KEY, titulo varchar, descripcion varchar, orden int);
CREATE TABLE perfil_agricultor (sub uuid PRIMARY KEY REFERENCES usuario, nombres varchar NOT NULL,
  apellidos varchar NOT NULL, tipo_doc char(3) DEFAULT 'DNI', documento char(8) NOT NULL, celular char(9) NOT NULL,
  correo varchar, departamento varchar NOT NULL, provincia varchar NOT NULL, distrito varchar NOT NULL,
  creado_en timestamptz NOT NULL);
CREATE TABLE agricultor_cultivo (sub uuid REFERENCES perfil_agricultor, slug varchar REFERENCES cultivo,
  PRIMARY KEY (sub, slug));
CREATE TABLE perfil_comprador (sub uuid PRIMARY KEY REFERENCES usuario, tipo_doc varchar(3) NOT NULL,
  documento varchar(11) NOT NULL, razon_social varchar NOT NULL, contacto_nombre varchar NOT NULL,
  contacto_celular char(9) NOT NULL, contacto_correo varchar, contacto_cargo varchar,
  cuenta_cargo_id varchar REFERENCES cuenta_demo, modalidad_pago varchar, creado_en timestamptz NOT NULL);
CREATE TABLE campana (campania_id uuid PRIMARY KEY, propietario_sub uuid NOT NULL REFERENCES perfil_agricultor,
  cultivo varchar NOT NULL REFERENCES cultivo, departamento varchar, provincia varchar, distrito varchar,
  cosecha date NOT NULL, volumen_kg int NOT NULL CHECK (volumen_kg > 0), logistica varchar,
  capital_centimos bigint, precio_ahora_centimos_por_kg int, precio_contraentrega_centimos_por_kg int,
  estado varchar NOT NULL, numero_ofertas int DEFAULT 0, creado_en timestamptz NOT NULL);
CREATE INDEX campana_publicadas ON campana (cultivo, departamento, cosecha) WHERE estado = 'PUBLICADA';
CREATE TABLE foto (foto_id uuid PRIMARY KEY, campania_id uuid NOT NULL, propietario_sub uuid NOT NULL,
  s3_key varchar, label varchar, label_confianza numeric, estado varchar, creado_en timestamptz);
CREATE TABLE oferta (oferta_id uuid PRIMARY KEY, campania_id uuid NOT NULL REFERENCES campana,
  comprador_sub uuid NOT NULL REFERENCES perfil_comprador, volumen_kg int NOT NULL, precio_centimos_por_kg int NOT NULL,
  total_centimos bigint NOT NULL, modalidad varchar, logistica varchar, fecha_entrega date, estado varchar,
  creado_en timestamptz NOT NULL);
CREATE INDEX oferta_por_comprador ON oferta (comprador_sub, creado_en DESC);
CREATE TABLE padron_empresa (id varchar PRIMARY KEY, razon_social varchar, direccion_fiscal varchar, actividad varchar, estado varchar);
CREATE TABLE padron_persona (id varchar PRIMARY KEY, nombres varchar, apellidos varchar, celular char(9), correo varchar);
CREATE TABLE asignacion_padron (sub uuid REFERENCES usuario, uso varchar, tipo_doc varchar, origen varchar NOT NULL,
  datos jsonb NOT NULL, creado_en timestamptz NOT NULL, PRIMARY KEY (sub, uso, tipo_doc));
"""

#vista agregada de agro-datos: como se ve la tabla unica (valores ficticios)
FILAS_TABLA = [
    ("USUARIO (agricultor)", "USER#a1b2...0001", "PROFILE", "", "", "", "", "rol=agricultor, nombres, apellidos, documento, celular, cultivos=[papa], departamento..."),
    ("USUARIO (comprador)", "USER#a1b2...0002", "PROFILE", "", "", "", "", "rol=comprador, tipoDoc=RUC, documento, razonSocial, contacto*, cuentaCargoId"),
    ("PADRON_ASIGNADO", "USER#a1b2...0002", "PADRON#comprador#RUC", "", "", "", "", "origen=EMPRESA#e03, datos{razonSocial...}"),
    ("CAMPANA", "CAMP#6f1c...9e11", "META", "USER#a1b2...0001", "CAMP#2026-10-06T...#6f1c...", "PUB#papa#Cusco", "2027-06-15#6f1c...", "cultivo, volumenKg=2000, precios en centimos, estado=PUBLICADA, numeroOfertas=1"),
    ("FOTO", "CAMP#6f1c...9e11", "FOTO#0b7e...", "", "", "", "", "s3Key=<sub>/papa_20261006_150000.jpg, label=papa, labelConfianza=99, estado=ETIQUETADA"),
    ("OFERTA", "CAMP#6f1c...9e11", "OFFER#9d8e...", "USER#a1b2...0002", "OFFER#2026-10-06T...#9d8e...", "", "", "volumenKg=1200, precioCentimosPorKg=185, totalCentimos=222000, estado=PENDIENTE"),
    ("CULTIVO", "CATALOGO", "CULTIVO#papa", "", "", "", "", "nombre=Papa, referenciaMercadoCentimosPorKg=120, etiquetasRekognition=[Potato]"),
    ("CUENTA_DEMO", "CUENTA_DEMO", "CUENTA#cc-8830", "", "", "", "", "titulo, descripcion=Cuenta ficticia de prueba"),
    ("MARCA", "SIEMBRA", "PADRON", "", "", "", "", "creadoEn, tablasPadron (fecha de creacion de cada tabla)"),
]

EQUIVALENCIA = [
    ("usuario", "Amazon Cognito (username = DNI o RUC, atributo custom:rol)", "La identidad no se guarda en la base; el sub enlaza todo."),
    ("perfil_agricultor, perfil_comprador", "agro-datos: PK=USER#&lt;sub&gt;, SK=PROFILE", "Un solo item por usuario; el atributo rol distingue el subtipo."),
    ("agricultor_cultivo (N:M)", "atributo lista cultivos en el PROFILE", "La tabla intermedia desaparece: la lista se lee con el perfil."),
    ("campana", "agro-datos: PK=CAMP#&lt;id&gt;, SK=META", "La FK propietario_sub pasa a la clave del indice por-usuario."),
    ("foto, oferta (1:N de campana)", "mismo PK CAMP#&lt;id&gt; con SK FOTO#... y OFFER#...", "Coleccion de items: una sola Query trae la campana y lo que cuelga de ella (sin JOIN)."),
    ("indice oferta_por_comprador", "indice global por-usuario (usuarioClave=USER#&lt;sub&gt;)", "El mismo indice sirve para mis campanas y mis ofertas."),
    ("indice parcial campana_publicadas", "indice global disperso publicadas-por-cultivo", "Solo las campanas publicadas llevan publicadaClave: el indice no guarda las demas."),
    ("JOIN oferta - campana - perfil", "copias en la oferta: cultivo, productorNombre, departamento, compradorNombre", "Desnormalizacion controlada: se copia al crear, nunca se actualiza."),
    ("numero de ofertas (COUNT)", "atributo numeroOfertas en META", "Lo incrementa el worker en la misma transaccion que crea la oferta."),
    ("cultivo, cuenta_demo", "agro-datos: PK=CATALOGO y PK=CUENTA_DEMO", "Datos de referencia pequenos; la API cachea el catalogo 60 s."),
    ("padron_empresa, padron_persona", "tablas propias agro-padron-empresas y agro-padron-personas", "Simulan SUNAT y RENIEC; el registro se borra al asignarse."),
    ("asignacion_padron", "agro-datos: PK=USER#&lt;sub&gt;, SK=PADRON#&lt;uso&gt;#&lt;tipoDoc&gt;", "Se crea en la misma transaccion que borra el registro del padron."),
]

PATRONES = [
    ("AP1", "Perfil del usuario", "GetItem", "agro-datos", "USER#<sub> / PROFILE"),
    ("AP2", "Campana por id", "GetItem", "agro-datos", "CAMP#<id> / META"),
    ("AP3", "Mis campanas", "Query", "agro-datos . por-usuario", "usuarioClave=USER#<sub>, usuarioOrden empieza con CAMP#"),
    ("AP4", "Mis ofertas", "Query", "agro-datos . por-usuario", "usuarioClave=USER#<sub>, usuarioOrden empieza con OFFER#"),
    ("AP5", "Ofertas de una campana", "Query", "agro-datos", "PK=CAMP#<id>, SK empieza con OFFER#"),
    ("AP6", "Fotos de una campana", "Query", "agro-datos", "PK=CAMP#<id>, SK empieza con FOTO#"),
    ("AP7", "Publicadas por cultivo y zona", "Query", "agro-datos . publicadas-por-cultivo", "publicadaClave=PUB#<cultivo>#<departamento>"),
    ("AP8", "Crear perfil, campana, oferta, foto", "PutItem condicional", "agro-datos", "attribute_not_exists(PK)"),
    ("AP9", "Catalogo de cultivos", "Query", "agro-datos", "PK=CATALOGO"),
    ("AP10", "Tomar un registro del padron", "Scan + TransactWriteItems", "agro-padron-* + agro-datos", "Delete en padron + Put PADRON#..."),
    ("AP11", "Asignacion de padron del usuario", "GetItem", "agro-datos", "USER#<sub> / PADRON#<uso>#<tipoDoc>"),
    ("AP12", "Cuentas de prueba", "Query", "agro-datos", "PK=CUENTA_DEMO"),
]

LAMBDAS = [
    ("Lambda agro-worker", "Escrituras asincronas (campanas y ofertas)", "SQS agro-insercion -> agro-datos",
     "PutItem CAMP#/META condicional; oferta: TransactWriteItems Put OFFER# + Update numeroOfertas"),
    ("Lambda agro-etiquetar", "Fotos", "S3 agro-fotos -> SQS agro-fotos -> Rekognition -> agro-datos",
     "copia la foto a <sub>/<slug>_<fecha>.<ext>, PutItem CAMP#/FOTO#, borra el original"),
]

COMPARACION = [
    ("Costo con poco uso", "Pago por peticion (on-demand); a 1000 usuarios ~USD 0.15 a 0.5 al mes (docs/costos)", "Instancia encendida 24x7: db.t4g.micro ~USD 12/mes + disco; Aurora Serverless v2 cobra por ACU (precios de lista aproximados, verificar)"),
    ("Red", "Endpoint regional por HTTPS; las Lambdas no necesitan estar en la VPC", "Vive en la VPC: subredes privadas, grupos de seguridad y las Lambdas dentro de la VPC (sin NAT el diseno se complica)"),
    ("Operacion", "Sin servidor, sin parches, sin conexiones que administrar", "Parches, versiones, tamano de instancia, pool de conexiones (RDS Proxy)"),
    ("Escalado", "Automatico por particion", "Vertical o replicas de lectura"),
    ("Transacciones", "TransactWriteItems hasta 100 items (oferta + contador, padron entre tablas)", "ACID completo con SQL"),
    ("Consultas", "Solo por clave e indices disenados para patrones de acceso conocidos (AP1-AP12)", "SQL ad hoc, JOIN, agregaciones, reportes"),
    ("Integridad", "Sin claves foraneas: la API y las condiciones de escritura la garantizan", "FOREIGN KEY, CHECK, UNIQUE en la base"),
    ("Learner Lab", "Cabe en USD 50 y se crea y destruye en segundos con Terraform", "Mas lento de crear y destruir; costo fijo aunque no se use"),
]


def consultas():
    #consultas por tabla: (tabla, titulo, cli, partiql)
    return [
        ("agro-datos", "Paso previo: el sub de cada usuario con perfil (solo demo: scan con filtro)",
         'aws dynamodb scan --region us-east-1 --table-name agro-datos \\\n  --filter-expression "SK = :p" --expression-attribute-values \'{":p":{"S":"PROFILE"}}\' \\\n  --projection-expression "#s, rol, documento, PK" --expression-attribute-names \'{"#s":"sub"}\' --output table',
         "SELECT \"sub\", \"rol\", \"documento\", \"PK\" FROM \"agro-datos\" WHERE \"SK\" = 'PROFILE';"),
        ("Cognito agro-usuarios", "Paso previo: el sub de todas las cuentas, aunque no tengan perfil (el user pool id sale de GET /config)",
         'aws cognito-idp list-users --region us-east-1 --user-pool-id <userPoolId> \\\n  --query "Users[].{documento:Username,sub:Attributes[?Name==\'sub\']|[0].Value,rol:Attributes[?Name==\'custom:rol\']|[0].Value,estado:UserStatus}" \\\n  --output table',
         "-- PartiQL no aplica a Cognito: usar la consola de Cognito > Grupos de usuarios > agro-usuarios > Usuarios (columna sub)"),
        ("agro-datos", "Todo lo de una campana (evidencia del insert de campana y de la oferta)",
         'aws dynamodb query --region us-east-1 --table-name agro-datos \\\n  --key-condition-expression "PK = :pk" \\\n  --expression-attribute-values \'{":pk":{"S":"CAMP#<campaniaId>"}}\'',
         "SELECT * FROM \"agro-datos\" WHERE \"PK\" = 'CAMP#<campaniaId>';"),
        ("agro-datos", "Perfil de un usuario (AP1)",
         'aws dynamodb get-item --region us-east-1 --table-name agro-datos \\\n  --key \'{"PK":{"S":"USER#<sub>"},"SK":{"S":"PROFILE"}}\'',
         "SELECT * FROM \"agro-datos\" WHERE \"PK\" = 'USER#<sub>' AND \"SK\" = 'PROFILE';"),
        ("agro-datos", "Ofertas de una campana (AP5)",
         'aws dynamodb query --region us-east-1 --table-name agro-datos \\\n  --key-condition-expression "PK = :pk AND begins_with(SK, :o)" \\\n  --expression-attribute-values \'{":pk":{"S":"CAMP#<campaniaId>"},":o":{"S":"OFFER#"}}\'',
         "SELECT * FROM \"agro-datos\" WHERE \"PK\" = 'CAMP#<campaniaId>' AND begins_with(\"SK\", 'OFFER#');"),
        ("agro-datos", "Catalogo de cultivos (AP9) y cuentas de prueba (AP12)",
         'aws dynamodb query --region us-east-1 --table-name agro-datos \\\n  --key-condition-expression "PK = :pk" --expression-attribute-values \'{":pk":{"S":"CATALOGO"}}\'',
         "SELECT * FROM \"agro-datos\" WHERE \"PK\" = 'CATALOGO';\nSELECT * FROM \"agro-datos\" WHERE \"PK\" = 'CUENTA_DEMO';"),
        ("agro-datos", "Ultimas campanas creadas (solo demo: es un scan con filtro)",
         'aws dynamodb scan --region us-east-1 --table-name agro-datos \\\n  --filter-expression "entidad = :e" --expression-attribute-values \'{":e":{"S":"CAMPANA"}}\' \\\n  --projection-expression "PK, cultivo, departamento, volumenKg, numeroOfertas, creadoEn"',
         "SELECT \"PK\", \"cultivo\", \"departamento\", \"volumenKg\", \"numeroOfertas\", \"creadoEn\"\nFROM \"agro-datos\" WHERE \"entidad\" = 'CAMPANA';"),
        ("agro-datos . por-usuario", "Mis campanas (AP3)",
         'aws dynamodb query --region us-east-1 --table-name agro-datos --index-name por-usuario \\\n  --key-condition-expression "usuarioClave = :u AND begins_with(usuarioOrden, :p)" \\\n  --expression-attribute-values \'{":u":{"S":"USER#<sub>"},":p":{"S":"CAMP#"}}\'',
         "SELECT * FROM \"agro-datos\".\"por-usuario\"\nWHERE \"usuarioClave\" = 'USER#<sub>' AND begins_with(\"usuarioOrden\", 'CAMP#');"),
        ("agro-datos . por-usuario", "Mis ofertas (AP4)",
         'aws dynamodb query --region us-east-1 --table-name agro-datos --index-name por-usuario \\\n  --key-condition-expression "usuarioClave = :u AND begins_with(usuarioOrden, :p)" \\\n  --expression-attribute-values \'{":u":{"S":"USER#<sub>"},":p":{"S":"OFFER#"}}\' --no-scan-index-forward',
         "SELECT * FROM \"agro-datos\".\"por-usuario\"\nWHERE \"usuarioClave\" = 'USER#<sub>' AND begins_with(\"usuarioOrden\", 'OFFER#');"),
        ("agro-datos . publicadas-por-cultivo", "Campanas publicadas de papa en Cusco (AP7)",
         'aws dynamodb query --region us-east-1 --table-name agro-datos --index-name publicadas-por-cultivo \\\n  --key-condition-expression "publicadaClave = :c" \\\n  --expression-attribute-values \'{":c":{"S":"PUB#papa#Cusco"}}\'',
         "SELECT \"PK\", \"productorNombre\", \"cosecha\", \"volumenKg\", \"numeroOfertas\"\nFROM \"agro-datos\".\"publicadas-por-cultivo\" WHERE \"publicadaClave\" = 'PUB#papa#Cusco';"),
        ("agro-padron-empresas", "Empresas que quedan en el padron",
         "aws dynamodb scan --region us-east-1 --table-name agro-padron-empresas --consistent-read \\\n  --projection-expression \"id, razonSocial\" --output table",
         "SELECT \"id\", \"razonSocial\", \"actividad\" FROM \"agro-padron-empresas\";"),
        ("agro-padron-personas", "Personas que quedan en el padron",
         "aws dynamodb scan --region us-east-1 --table-name agro-padron-personas --consistent-read \\\n  --projection-expression \"id, nombres, apellidos\" --output table",
         "SELECT \"id\", \"nombres\", \"apellidos\" FROM \"agro-padron-personas\";"),
        ("agro-datos", "Asignaciones del padron hechas (solo demo: scan con filtro)",
         'aws dynamodb scan --region us-east-1 --table-name agro-datos \\\n  --filter-expression "entidad = :e" --expression-attribute-values \'{":e":{"S":"PADRON_ASIGNADO"}}\'',
         "SELECT \"PK\", \"SK\", \"origen\", \"creadoEn\" FROM \"agro-datos\" WHERE \"entidad\" = 'PADRON_ASIGNADO';"),
    ]


def celda(x):
    #texto seguro para una celda markdown: < > como entidades y | escapado
    return e(html.unescape(str(x)), quote=False).replace("|", "\\|").replace("\n", " ")


def tabla(cabecera, filas):
    return "\n".join(["| " + " | ".join(cabecera) + " |", "|" + "---|" * len(cabecera)] +
                     ["| " + " | ".join(celda(x) for x in f) + " |" for f in filas])


def bloque(lenguaje, texto):
    return "```" + lenguaje + "\n" + texto.strip("\n") + "\n```"


def generar():
    diagrama_er()
    diagrama_dynamo()
    api = json.loads(API_TABLAS.read_text(encoding="utf-8"))
    filas_api = [(k, v["microservicio"], v["tipo"], v["destino"], v["operacion"]) for k, v in api.items()]
    filas_api += [(a, b, "escritura asincrona", c, d) for a, b, c, d in LAMBDAS]
    filas_dueno = [
        ("Identidad y perfil", "agro-datos: items USER#<sub> / PROFILE", "Cognito (identidad)"),
        ("Campanas y fotos", "agro-datos: items CAMP#<id> / META y FOTO#; S3 agro-fotos", "SQS agro-insercion, Lambdas agro-worker y agro-etiquetar"),
        ("Ofertas", "agro-datos: items CAMP#<id> / OFFER#; contador numeroOfertas", "SQS agro-insercion, Lambda agro-worker"),
        ("Padron y catalogos", "tablas agro-padron-empresas y agro-padron-personas; agro-datos: CATALOGO, CUENTA_DEMO, PADRON#", "-"),
    ]
    #el paso previo va en la seccion 1; aqui solo las consultas que usan el sub o el id de campana
    lista = [c for c in consultas() if not c[1].startswith("Paso previo")]
    partes_consulta = []
    for tb, titulo, cli, sql in lista:
        partes_consulta += ["### " + titulo + " (`" + tb + "`)", "", "PartiQL:", "", bloque("sql", sql), "", "AWS CLI:", "", bloque("bash", cli), ""]

    md = [
        "# AgroCredit - diseno de base de datos",
        "",
        "Modelo entidad relacion, modelo real en Amazon DynamoDB y consultas por tabla. Datos ficticios (Ley 29733).",
        "Generado por `docs/base-datos/generar.py` (decisiones 18, 58 y 64). Detalle de atributos y ejemplos JSON: `docs/modelo-datos.md`.",
        "",
        "## 1. Antes de consultar: insertar datos y obtener los sub",
        "",
        "Las tablas arrancan solo con el catalogo, las cuentas de prueba y el padron. Para que las consultas devuelvan algo:",
        "",
        "1. **Insertar un agricultor y un comprador**: crear la cuenta y el perfil de cada uno en la web (registro y alta) o con Thunder Client "
        "(`docs/api/thunder/`: peticion 03 *Crear mi perfil (agricultor)* y 14 *Crear mi perfil (comprador)*).",
        "2. Para las consultas de campanas y ofertas: registrar una campana (peticion 06) y enviar una oferta (peticion 17), o hacerlo desde la web.",
        "3. **Obtener el `sub` de cada usuario** (identificador de Cognito con el que se arman las claves `USER#<sub>`):",
        "",
        "PartiQL (consola de DynamoDB > Editor de PartiQL):",
        "",
        bloque("sql", "SELECT \"sub\", \"rol\", \"documento\", \"PK\" FROM \"agro-datos\" WHERE \"SK\" = 'PROFILE';"),
        "",
        "AWS CLI (desde `Conexion`: `source ./conectar.sh` y `source .venv/bin/activate`; en Windows `. .\\conectar.ps1` y `.venv\\Scripts\\Activate.ps1`, "
        "y cambiar el `\\` de fin de linea por `` ` ``). `sub` es palabra reservada de DynamoDB: va con el alias `#s`.",
        "",
        bloque("bash", 'aws dynamodb scan --region us-east-1 --table-name agro-datos \\\n  --filter-expression "SK = :p" --expression-attribute-values \'{":p":{"S":"PROFILE"}}\' \\\n'
                       '  --projection-expression "#s, rol, documento, PK" --expression-attribute-names \'{"#s":"sub"}\' --output table'),
        "",
        "Si la cuenta existe pero aun no tiene perfil, no aparece en DynamoDB: su `sub` esta en Cognito (consola: Cognito > Grupos de usuarios > agro-usuarios > Usuarios). "
        "Por CLI, con el `userPoolId` que devuelve `GET /api/v1/config`:",
        "",
        bloque("bash", 'aws cognito-idp list-users --region us-east-1 --user-pool-id <userPoolId> \\\n'
                       '  --query "Users[].{documento:Username,sub:Attributes[?Name==\'sub\']|[0].Value,rol:Attributes[?Name==\'custom:rol\']|[0].Value}" \\\n  --output table'),
        "",
        "Con el `sub` se reemplaza `<sub>` en las consultas de la seccion 6. El `<campaniaId>` sale de la respuesta 202 de *Registrar campana* (`recursoId`) "
        "o de la columna `PK` de las consultas de campanas (sin el prefijo `CAMP#`). La consulta del `sub` es un scan con filtro: valido para la demo, no para produccion.",
        "",
        "## 2. Por que DynamoDB y no una base relacional",
        "",
        "Se eligio **Amazon DynamoDB on-demand** (decision 3). Comparacion con una base relacional (Amazon RDS PostgreSQL o Aurora):",
        "",
        tabla(["Criterio", "DynamoDB (elegido)", "Relacional (RDS / Aurora)"], COMPARACION),
        "",
        "**Lo que se pierde**: SQL ad hoc, JOIN y claves foraneas. Se compensa con patrones de acceso disenados antes (AP1-AP12), escrituras condicionales "
        "(idempotencia), transacciones y copias controladas de datos. Para reportes, en produccion se exportaria a S3 y se consultaria con Athena.",
        "",
        "## 3. Modelo entidad relacion (vista relacional equivalente)",
        "",
        "Asi se veria el mismo negocio en una base relacional normalizada. Es la vista conceptual: **no se despliega**. "
        "Celeste = vive en Cognito; menta = tablas de padron; blanco = items de `agro-datos`.",
        "",
        "![Modelo entidad relacion](er-relacional.png)",
        "",
        "DDL equivalente (PostgreSQL, solo explicativo):",
        "",
        bloque("sql", DDL),
        "",
        "## 4. Modelo real en DynamoDB",
        "",
        "![Modelo real en DynamoDB](dynamodb-modelo.png)",
        "",
        "### Tablas desplegadas",
        "",
        tabla(["Tabla", "Clave", "Indices", "Modo y cifrado", "Que guarda"], [
            ("agro-datos", "PK (texto) + SK (texto)", "por-usuario (usuarioClave, usuarioOrden); publicadas-por-cultivo (publicadaClave, publicadaOrden), disperso",
             "on-demand; cifrado de AWS; sin PITR", "perfiles, campanas, fotos, ofertas, catalogo, cuentas de prueba, asignaciones del padron"),
            ("agro-padron-empresas", "id (texto)", "-", "on-demand; sin PITR", "10 empresas ficticias (simula SUNAT), sin RUC"),
            ("agro-padron-personas", "id (texto)", "-", "on-demand; sin PITR", "10 personas ficticias (simula RENIEC), sin DNI"),
        ]),
        "",
        "### Vista agregada de agro-datos (diseno de tabla unica)",
        "",
        "Cada fila es un item; el tipo lo dicen el prefijo de la clave y el atributo `entidad`.",
        "",
        tabla(["entidad", "PK", "SK", "usuarioClave", "usuarioOrden", "publicadaClave", "publicadaOrden", "Atributos principales"], FILAS_TABLA),
        "",
        "### De la tabla relacional al item de DynamoDB",
        "",
        tabla(["Relacional", "DynamoDB", "Por que"], EQUIVALENCIA),
        "",
        "### Patrones de acceso",
        "",
        tabla(["#", "Patron", "Operacion", "Tabla o indice", "Clave"], PATRONES),
        "",
        "## 5. Cada microservicio y sus datos",
        "",
        "La API (FastAPI en ECS Fargate) se organiza en cuatro dominios, mas dos Lambdas. Cada dominio es dueno de sus items (prefijo de clave) y solo el padron "
        "tiene tablas fisicas propias. Ningun dominio escribe los items de otro, salvo el contador `numeroOfertas`, que el worker actualiza en la misma transaccion que crea la oferta.",
        "",
        tabla(["Microservicio", "Datos de los que es dueno", "Servicios que usa"], filas_dueno),
        "",
        "**Limitacion conocida**: los dominios comparten la tabla `agro-datos` (diseno de tabla unica). Separarlos en una tabla por servicio es posible, "
        "pero la transaccion oferta + contador cruzaria tablas y se perderia la Query unica de una campana con sus fotos y ofertas.",
        "",
        "### Que tabla o servicio toca cada API",
        "",
        tabla(["API o funcion", "Microservicio", "Tipo", "Tabla o servicio", "Operacion"], filas_api),
        "",
        "Coleccion para probarlas en orden (Thunder Client o Postman): `docs/api/thunder/LEEME.md`.",
        "",
        "## 6. Consultas por tabla (solo lectura)",
        "",
        "Reemplazar `<sub>` y `<campaniaId>` con lo obtenido en la seccion 1.",
        "",
        *partes_consulta,
        "Un SELECT de PartiQL sin condicion sobre la clave de particion es un **scan** completo: en la demo es irrelevante, en produccion se evita. "
        "No usar INSERT, UPDATE ni DELETE de PartiQL sobre estas tablas: romperia la idempotencia y el contador que mantiene el worker.",
        "",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    (AQUI / "agrocredit-base-datos.md").write_text(generar(), encoding="utf-8")
    print("generado: agrocredit-base-datos.md, er-relacional.png/svg, dynamodb-modelo.png")
