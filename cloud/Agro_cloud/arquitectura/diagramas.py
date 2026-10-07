#genera los diagramas con iconos oficiales de aws (decision 63)
#uso (desde arquitectura/): docker build -t agro-diagramas:0.25.1 -f diagramas.Dockerfile .
#  docker run --rm -v "$PWD":/trabajo agro-diagramas:0.25.1 python diagramas.py
import base64
import re
from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, Fargate, Lambda
from diagrams.aws.database import DynamodbTable
from diagrams.aws.general import Users
from diagrams.aws.integration import EventbridgeScheduler, SQS
from diagrams.aws.management import CloudformationStack, CloudwatchLogs, ParameterStore
from diagrams.aws.ml import Rekognition
from diagrams.aws.network import ElbApplicationLoadBalancer, InternetGateway
from diagrams.aws.security import Cognito
from diagrams.aws.storage import S3

AQUI = Path(__file__).resolve().parent

GRAFO = {"fontsize": "22", "fontname": "DejaVu Sans", "pad": "0.6", "nodesep": "0.7",
         "ranksep": "1.1", "splines": "spline", "labelloc": "t"}
NODO = {"fontsize": "12", "fontname": "DejaVu Sans"}
ARISTA = {"fontsize": "11", "fontname": "DejaVu Sans"}

#colores de la marca v05
VERDE = "#135C40"
HOJA = "#418E49"
GRIS = "#7A7A7A"
ROJO = "#B3261E"


def incrustar_iconos(svg: Path) -> None:
    #el svg de graphviz enlaza los png del contenedor: se incrustan en base64 para que sea portable
    texto = svg.read_text(encoding="utf-8")

    def a_datos(m):
        ruta = Path(m.group(2))
        if not ruta.exists():
            return m.group(0)
        datos = base64.b64encode(ruta.read_bytes()).decode("ascii")
        return f'{m.group(1)}="data:image/png;base64,{datos}"'

    texto = re.sub(r'(xlink:href|href)="(/[^"]+\.png)"', a_datos, texto)
    svg.write_text(texto, encoding="utf-8")


def arquitectura() -> str:
    nombre = "agrocredit-arquitectura-aws"
    with Diagram("AgroCredit - arquitectura de despliegue en AWS (us-east-1)", filename=str(AQUI / nombre),
                 outformat=["png", "svg"], show=False, direction="LR",
                 graph_attr=GRAFO, node_attr=NODO, edge_attr=ARISTA):
        usuarios = Users("Agricultor y comprador\n(navegador, celular o PC)")

        with Cluster("Cuenta AWS Learner Lab - region us-east-1 - todo con prefijo agro- y LabRole"):
            cognito = Cognito("Cognito agro-usuarios\nusuario = DNI/RUC, PIN\nSRP, JWT, custom:rol")

            with Cluster("VPC agro-red 10.20.0.0/16 (sin NAT)"):
                igw = InternetGateway("Internet Gateway")
                alb = ElbApplicationLoadBalancer("ALB agro-alb\nHTTP 80\n/api/* -> api ; /* -> web")
                with Cluster("Subred publica us-east-1a"):
                    web_a = Fargate("agro-web A\nnginx ARM64")
                    api_a = Fargate("agro-api A\nFastAPI ARM64")
                with Cluster("Subred publica us-east-1b"):
                    web_b = Fargate("agro-web B\nnginx ARM64")
                    api_b = Fargate("agro-api B\nFastAPI ARM64")

            with Cluster("Datos (DynamoDB on-demand)"):
                datos = DynamodbTable("agro-datos\n+ por-usuario\n+ publicadas-por-cultivo")
                padron = DynamodbTable("agro-padron-personas\nagro-padron-empresas")

            with Cluster("Escritura asincrona"):
                cola = SQS("SQS agro-insercion\n(+DLQ)")
                worker = Lambda("Lambda agro-worker\nidempotente")

            with Cluster("Fotos"):
                bucket = S3("S3 agro-fotos-<cuenta>\nprivado, AES256, CORS al ALB")
                cola_fotos = SQS("SQS agro-fotos\n(+DLQ)")
                etiquetar = Lambda("Lambda agro-etiquetar")
                rekog = Rekognition("Rekognition\nDetectLabels")

            with Cluster("Operacion (soporte del despliegue)"):
                ecr = ECR("ECR agro-web, agro-api\nimagenes que bajan las tareas")
                logs = CloudwatchLogs("CloudWatch Logs\ntareas y lambdas, 1 dia")
                apagado = EventbridgeScheduler("Scheduler agro-apagado\n+2 h: servicios ECS a 0")
                ssm = ParameterStore("SSM /agro-/registro\nids para destruir")
                cfn = CloudformationStack("CloudFormation agro-fotos\ncrea el bucket (SCP)")

        usuarios >> Edge(label="HTTP 80", color=VERDE, penwidth="2") >> igw >> Edge(color=VERDE, penwidth="2") >> alb
        alb >> Edge(label="/*", color=VERDE) >> [web_a, web_b]
        alb >> Edge(label="/api/*", color=VERDE) >> [api_a, api_b]
        usuarios >> Edge(label="registro y login\n(SRP directo)", color=HOJA, style="dashed") >> cognito
        usuarios >> Edge(label="subida y lectura de fotos\n(URL prefirmada)", color=HOJA, style="dashed") >> bucket

        for api in (api_a, api_b):
            api >> Edge(color=GRIS) >> datos
            api >> Edge(color=GRIS) >> padron
            api >> Edge(color=GRIS) >> cola
        api_b >> Edge(label="valida JWT (JWKS)", color=GRIS, style="dotted") >> cognito

        cola >> Edge(label="lotes de 10") >> worker >> Edge(label="Put condicional\n+ contador") >> datos
        bucket >> Edge(label="ObjectCreated entrada/") >> cola_fotos >> etiquetar
        etiquetar >> Edge(label="DetectLabels") >> rekog
        etiquetar >> Edge(label="copia y borra") >> bucket
        etiquetar >> Edge(label="FOTO#") >> datos
        #operacion sin aristas para no cruzar el diagrama; la relacion va en cada etiqueta
        ecr - Edge(style="invis") - logs - Edge(style="invis") - apagado
        ssm - Edge(style="invis") - cfn
        usuarios - Edge(style="invis") - ecr
    return nombre


def flujo() -> str:
    nombre = "agrocredit-flujo-tecnico"
    with Diagram("AgroCredit - flujo tecnico de los tres casos del corte vertical", filename=str(AQUI / nombre),
                 outformat=["png", "svg"], show=False, direction="LR",
                 graph_attr=GRAFO, node_attr=NODO, edge_attr=ARISTA):

        #graphviz apila los bloques en orden inverso: se declaran 3, 2, 1 para que el 1 quede arriba
        with Cluster("3. Oferta (comprador)"):
            u3 = Users("Comprador")
            a3 = ElbApplicationLoadBalancer("ALB")
            api3 = Fargate("agro-api")
            d3r = DynamodbTable("publicadas-por-cultivo\n(indice disperso)")
            q3 = SQS("SQS agro-insercion")
            w3 = Lambda("agro-worker")
            d3 = DynamodbTable("agro-datos\nOFFER# + numeroOfertas")
            u3 >> Edge(label="1 GET /campanas/publicadas", color=VERDE) >> a3 >> api3
            api3 >> Edge(label="2 Query", color=VERDE) >> d3r
            api3 >> Edge(label="3 POST /campanas/{id}/ofertas -> 202", color=VERDE) >> q3
            q3 >> Edge(label="4") >> w3
            w3 >> Edge(label="5 transaccion Put oferta\n+ Update contador (idempotente)") >> d3
            u3 >> Edge(label="6 GET /ofertas (mis ofertas)", style="dashed", color=GRIS) >> a3

        with Cluster("2. Campana con foto (agricultor)"):
            u2 = Users("Agricultor")
            a2 = ElbApplicationLoadBalancer("ALB")
            api2 = Fargate("agro-api")
            s2 = S3("S3 agro-fotos\nentrada/<sub>/...")
            q2 = SQS("SQS agro-fotos")
            l2 = Lambda("agro-etiquetar")
            r2 = Rekognition("Rekognition")
            qi2 = SQS("SQS agro-insercion")
            w2 = Lambda("agro-worker")
            d2 = DynamodbTable("agro-datos\nCAMP# META / FOTO#")
            u2 >> Edge(label="1 POST /campanas/{id}/fotos/url", color=VERDE) >> a2 >> api2
            u2 >> Edge(label="2 POST prefirmado (jpg/png)", color=HOJA) >> s2
            s2 >> Edge(label="3 ObjectCreated") >> q2 >> Edge(label="4") >> l2
            l2 >> Edge(label="5 DetectLabels -> slug") >> r2
            l2 >> Edge(label="6 registra FOTO#, copia y borra original") >> d2
            api2 >> Edge(label="7 POST /campanas -> 202\nmensaje a la cola", color=VERDE) >> qi2
            qi2 >> Edge(label="8") >> w2 >> Edge(label="9 Put si no existe") >> d2
            u2 >> Edge(label="10 GET /campanas/{id} hasta 200", style="dashed", color=GRIS) >> a2

        with Cluster("1. Registro e inicio de sesion (agricultor o comprador)"):
            u1 = Users("Usuario")
            c1 = Cognito("Cognito")
            a1 = ElbApplicationLoadBalancer("ALB")
            api1 = Fargate("agro-api")
            d1 = DynamodbTable("agro-datos\nPROFILE")
            p1 = DynamodbTable("agro-padron-*\n(solo comprador)")
            u1 >> Edge(label="1 documento + correo + PIN (signUp)", color=HOJA) >> c1
            c1 >> Edge(label="2 codigo por correo", color=HOJA, style="dashed") >> u1
            u1 >> Edge(label="3 login SRP -> ID token", color=HOJA) >> c1
            u1 >> Edge(label="4 POST /padron/consulta\nPOST /perfil (bearer)", color=VERDE) >> a1 >> api1
            api1 >> Edge(label="5 TransactWriteItems\nDelete padron + Put asignacion", color=VERDE) >> p1
            api1 >> Edge(label="6 Put PROFILE (201)", color=VERDE) >> d1
    return nombre


if __name__ == "__main__":
    for nombre in (arquitectura(), flujo()):
        incrustar_iconos(AQUI / f"{nombre}.svg")
        print("generado:", f"{nombre}.png", f"{nombre}.svg")
