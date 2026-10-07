#estimacion de costos mensuales de agrocredit a 1000 usuarios activos (decision 63)
#precios: lista publica de aws (pricing.us-east-1.amazonaws.com), sin credenciales ni acceso a la cuenta
#uso (desde docs/costos/): python3 estimar.py   -> escribe costos.md y calculadora.csv
import csv
import json
import re
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CACHE = Path(tempfile.gettempdir()) / "agro-precios"
URL = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/{s}/current/us-east-1/index.json"
HORAS = 730  #horas por mes que usa la calculadora de aws

#clave -> (servicio, usagetype exacto, texto que debe tener la descripcion, inicio del tramo)
SKUS = {
    "fargate_vcpu": ("AmazonECS", "USE1-Fargate-ARM-vCPU-Hours:perCPU", "", "0"),
    "fargate_gb": ("AmazonECS", "USE1-Fargate-ARM-GB-Hours", "", "0"),
    "alb_hora": ("AWSELB", "LoadBalancerUsage", "Application LoadBalancer-hour", "0"),
    "alb_lcu": ("AWSELB", "LCUUsage", "used Application load balancer", "0"),
    "ipv4": ("AmazonVPC", "USE1-PublicIPv4:InUseAddress", "", "0"),
    "ddb_lectura": ("AmazonDynamoDB", "ReadRequestUnits", "", "0"),
    "ddb_escritura": ("AmazonDynamoDB", "WriteRequestUnits", "", "0"),
    "ddb_gb": ("AmazonDynamoDB", "TimedStorage-ByteHrs", "", "25"),
    "sqs": ("AWSQueueService", "Requests-RBP", "", "0"),
    "lambda_gbs": ("AWSLambda", "Lambda-GB-Second-ARM", "", "0"),
    "lambda_req": ("AWSLambda", "Request-ARM", "", "0"),
    "s3_gb": ("AmazonS3", "TimedStorage-ByteHrs", "first 50 TB", "0"),
    "s3_put": ("AmazonS3", "Requests-Tier1", "", "0"),
    "s3_get": ("AmazonS3", "Requests-Tier2", "", "0"),
    "rekognition": ("AmazonRekognition", "USE1-Group2-ImagesProcessed", "", "0"),
    "cognito": ("AmazonCognito", "USE1-CognitoEssentialsMAU", "", "0"),
    "logs_gb": ("AmazonCloudWatch", "DataProcessing-Bytes", "Standard log class", "0"),
    "logs_alm": ("AmazonCloudWatch", "TimedStorage-ByteHrs", "log storage", "0"),
    "ecr_gb": ("AmazonECR", "TimedStorage-ByteHrs", "", "0"),
    "dto": ("AWSDataTransfer", "DataTransfer-Out-Bytes", "first 10 TB", "0"),
}

#capa gratuita permanente (always free) que aplica a esta arquitectura; las de 12 meses no se cuentan
GRATIS = {
    "lambda_req": 1_000_000, "lambda_gbs": 400_000, "sqs": 1_000_000, "cognito": 10_000,
    "dto": 100, "logs_gb": 5,
}

COMUN = {
    "tareas": 4, "vcpu": 0.25, "memoria_gb": 0.5, "ips_publicas": 6,
    "pagina_kb": 176, "archivos_pagina": 10, "api_respuesta_kb": 2, "foto_mb": 1.5,
    "meses_fotos": 12, "lecturas_por_llamada": 3,
    "log_web_b": 250, "log_api_b": 300, "log_salud_b": 200, "chequeos_por_hora": 4 * 720,
    "worker_s": 0.2, "etiquetar_s": 1.5, "lambda_gb": 0.25,
    "sondeos_sqs": 2 * 5 * (3600 * HORAS // 20), "ecr_gb": 0.7,
}

ESCENARIOS = [
    {"nombre": "moderado", "usuarios": 1000, "pct_agricultor": 0.70, "sesiones": 15, "paginas_sesion": 8,
     "api_sesion": 25, "campanas_agricultor": 1, "fotos_campana": 3, "ofertas_comprador": 5,
     "lotes_vistos_sesion": 3, "perfiles_nuevos": 100},
    {"nombre": "alto", "usuarios": 1000, "pct_agricultor": 0.70, "sesiones": 30, "paginas_sesion": 12,
     "api_sesion": 40, "campanas_agricultor": 2, "fotos_campana": 5, "ofertas_comprador": 15,
     "lotes_vistos_sesion": 6, "perfiles_nuevos": 200},
]


def lista_precios(servicio):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{servicio}.json"
    if not f.exists() or f.stat().st_size < 1000:
        urllib.request.urlretrieve(URL.format(s=servicio), f)
    return json.loads(f.read_text(encoding="utf-8"))


def precios():
    datos, salida = {}, {}
    for clave, (serv, uso, texto, inicio) in SKUS.items():
        d = datos.setdefault(serv, lista_precios(serv))
        hallados = set()
        for sku, prod in d["products"].items():
            a = prod.get("attributes", {})
            if a.get("usagetype") != uso or a.get("regionCode", "us-east-1") != "us-east-1":
                continue
            if serv == "AWSDataTransfer" and a.get("toLocation") != "External":
                continue
            for t in d["terms"].get("OnDemand", {}).get(sku, {}).values():
                for dim in t["priceDimensions"].values():
                    if dim.get("beginRange") == inicio and texto in dim["description"]:
                        hallados.add((float(dim["pricePerUnit"]["USD"]), dim["unit"], dim["description"].strip()))
        if len(hallados) != 1:
            raise SystemExit(f"precio ambiguo o ausente para {clave}: {hallados}")
        salida[clave] = hallados.pop()
    return salida


def uso(e):
    c = COMUN
    agri = round(e["usuarios"] * e["pct_agricultor"])
    comp = e["usuarios"] - agri
    sesiones = e["usuarios"] * e["sesiones"]
    paginas = sesiones * e["paginas_sesion"]
    llamadas = sesiones * e["api_sesion"]
    campanas = agri * e["campanas_agricultor"]
    fotos = campanas * e["fotos_campana"]
    ofertas = comp * e["ofertas_comprador"]
    fotos_vistas = comp * e["sesiones"] * e["lotes_vistos_sesion"] * e["fotos_campana"] + fotos
    gb_web = paginas * c["pagina_kb"] / 1024 / 1024
    gb_api = llamadas * c["api_respuesta_kb"] / 1024 / 1024
    gb_fotos = fotos_vistas * c["foto_mb"] / 1024
    #escrituras: campana con 2 indices (x3), foto (put + update), oferta en transaccion (x2) de 2 items con indice
    wru = campanas * 3 + fotos * 2 + ofertas * 8 + e["perfiles_nuevos"] * 2 + 50
    mensajes = campanas + ofertas + fotos
    peticiones_web = paginas * c["archivos_pagina"]
    gb_logs = (peticiones_web * c["log_web_b"] + llamadas * c["log_api_b"]
               + c["chequeos_por_hora"] * HORAS * c["log_salud_b"] + mensajes * 1000) / 1024 ** 3
    return {
        "agricultores": agri, "compradores": comp, "sesiones": sesiones, "paginas": paginas,
        "peticiones_web": peticiones_web, "llamadas_api": llamadas, "campanas": campanas, "fotos": fotos,
        "ofertas": ofertas, "fotos_vistas": fotos_vistas, "gb_web": gb_web, "gb_api": gb_api, "gb_fotos": gb_fotos,
        "rru": llamadas * c["lecturas_por_llamada"], "wru": wru, "mensajes": mensajes,
        "sqs_peticiones": c["sondeos_sqs"] + mensajes * 3,
        "lambda_inv": mensajes, "lambda_gbs": ((campanas + ofertas) * c["worker_s"] + fotos * c["etiquetar_s"]) * c["lambda_gb"],
        "s3_gb": fotos * c["foto_mb"] / 1024 * c["meses_fotos"], "s3_put": fotos * 2, "s3_get": fotos_vistas + fotos,
        "gb_logs": gb_logs, "gb_alb": gb_web + gb_api, "gb_salida": gb_web + gb_api + gb_fotos,
        "req_s": (peticiones_web + llamadas) / (HORAS * 3600), "conexiones_s": paginas / (HORAS * 3600),
    }


def lineas(e, p):
    c, u = COMUN, uso(e)
    lcu = max(u["gb_alb"] / HORAS, u["conexiones_s"] / 25, u["req_s"] / 25)
    filas = [
        #(servicio, componente, campos de la calculadora, cantidad, clave de precio)
        ("AWS Fargate (ECS)", "vCPU ARM", f"Linux, ARM, {c['tareas']} tareas, 730 h, {c['vcpu']} vCPU", c["tareas"] * c["vcpu"] * HORAS, "fargate_vcpu"),
        ("AWS Fargate (ECS)", "memoria ARM", f"{c['memoria_gb']} GB por tarea, almacenamiento efimero 20 GB (incluido)", c["tareas"] * c["memoria_gb"] * HORAS, "fargate_gb"),
        ("Elastic Load Balancing (ALB)", "hora de ALB", "1 Application Load Balancer, 730 h", HORAS, "alb_hora"),
        ("Elastic Load Balancing (ALB)", "LCU", f"bytes procesados {u['gb_alb']:.1f} GB/mes, {u['conexiones_s']:.3f} conexiones nuevas/s, duracion 30 s, {u['req_s']:.2f} peticiones/s, 2 reglas", lcu * HORAS, "alb_lcu"),
        ("Amazon VPC", "IPv4 publicas en uso", f"{c['ips_publicas']} IP (4 tareas + 2 del ALB), 730 h", c["ips_publicas"] * HORAS, "ipv4"),
        ("Amazon DynamoDB", "lecturas on-demand", f"{u['rru']:,} unidades de lectura/mes (3 tablas, clase Standard)", u["rru"], "ddb_lectura"),
        ("Amazon DynamoDB", "escrituras on-demand", f"{u['wru']:,} unidades de escritura/mes", u["wru"], "ddb_escritura"),
        ("Amazon DynamoDB", "almacenamiento", "1 GB (los primeros 25 GB son gratis en la lista)", 0, "ddb_gb"),
        ("Amazon SQS", "peticiones estandar", f"{u['sqs_peticiones']:,} peticiones/mes (sondeo de Lambda en 2 colas + {u['mensajes']:,} mensajes x3)", u["sqs_peticiones"], "sqs"),
        ("AWS Lambda", "peticiones ARM", f"2 funciones arm64, {u['lambda_inv']:,} invocaciones/mes", u["lambda_inv"], "lambda_req"),
        ("AWS Lambda", "computo ARM", f"256 MB, worker {c['worker_s']} s, etiquetar {c['etiquetar_s']} s", u["lambda_gbs"], "lambda_gbs"),
        ("Amazon S3", "almacenamiento Standard", f"{u['s3_gb']:.0f} GB (fotos acumuladas a {c['meses_fotos']} meses)", u["s3_gb"], "s3_gb"),
        ("Amazon S3", "PUT, COPY, POST", f"{u['s3_put']:,} peticiones/mes (subida + copia)", u["s3_put"], "s3_put"),
        ("Amazon S3", "GET", f"{u['s3_get']:,} peticiones/mes (lectura + Rekognition)", u["s3_get"], "s3_get"),
        ("Amazon Rekognition", "DetectLabels (grupo 2)", f"{u['fotos']:,} imagenes/mes", u["fotos"], "rekognition"),
        ("Amazon Cognito", "MAU plan Essentials", f"{e['usuarios']:,} usuarios activos al mes", e["usuarios"], "cognito"),
        ("Amazon CloudWatch", "ingesta de logs", f"{u['gb_logs']:.2f} GB/mes (incluye chequeos de salud cada 5 s)", u["gb_logs"], "logs_gb"),
        ("Amazon CloudWatch", "almacenamiento de logs", "retencion 1 dia", u["gb_logs"] / 30, "logs_alm"),
        ("Amazon ECR", "almacenamiento", f"{c['ecr_gb']} GB (5 imagenes por repositorio)", c["ecr_gb"], "ecr_gb"),
        ("Transferencia de datos", "salida a internet", f"{u['gb_salida']:.0f} GB/mes (web {u['gb_web']:.0f}, api {u['gb_api']:.1f}, fotos {u['gb_fotos']:.0f})", u["gb_salida"], "dto"),
    ]
    salida = []
    for serv, comp, campos, cant, clave in filas:
        precio, unidad, _ = p[clave]
        lista = cant * precio
        con_gratis = max(cant - GRATIS.get(clave, 0), 0) * precio
        salida.append({"escenario": e["nombre"], "servicio": serv, "componente": comp, "calculadora": campos,
                       "cantidad": round(cant, 3), "unidad": unidad, "precio_usd": precio,
                       "costo_lista_usd": round(lista, 2), "costo_con_gratis_usd": round(con_gratis, 2)})
    return salida, u


def tabla_md(cabecera, filas):
    out = ["| " + " | ".join(cabecera) + " |", "|" + "---|" * len(cabecera)]
    out += ["| " + " | ".join(str(x) for x in f) + " |" for f in filas]
    return "\n".join(out)


def main():
    p = precios()
    todas, usos = [], {}
    for e in ESCENARIOS:
        filas, u = lineas(e, p)
        todas += filas
        usos[e["nombre"]] = u
    with open(AQUI / "calculadora.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(todas[0].keys()))
        w.writeheader()
        w.writerows(todas)

    lima = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d %H:%M")
    nombres = [e["nombre"] for e in ESCENARIOS]

    def total(esc, campo):
        return sum(f[campo] for f in todas if f["escenario"] == esc)

    def por_servicio(esc, campo):
        r = {}
        for f in todas:
            if f["escenario"] == esc:
                r[f["servicio"]] = r.get(f["servicio"], 0) + f[campo]
        return r

    fijos = {"AWS Fargate (ECS)", "Elastic Load Balancing (ALB)", "Amazon VPC", "Amazon ECR"}
    servicios = list(dict.fromkeys(f["servicio"] for f in todas))
    filas_res = []
    for s in servicios:
        fila = [s]
        for n in nombres:
            fila += [f"{por_servicio(n, 'costo_lista_usd')[s]:.2f}", f"{por_servicio(n, 'costo_con_gratis_usd')[s]:.2f}"]
        filas_res.append(fila)
    filas_res.append(["**Total mensual**"] + sum(([f"**{total(n, 'costo_lista_usd'):.2f}**", f"**{total(n, 'costo_con_gratis_usd'):.2f}**"] for n in nombres), []))

    sup = [("Usuarios activos al mes", "usuarios"), ("Agricultores / compradores", None), ("Sesiones por usuario al mes", "sesiones"),
           ("Paginas por sesion", "paginas_sesion"), ("Llamadas a la api por sesion", "api_sesion"),
           ("Campanas por agricultor al mes", "campanas_agricultor"), ("Fotos por campana", "fotos_campana"),
           ("Ofertas por comprador al mes", "ofertas_comprador"), ("Lotes vistos por sesion de comprador", "lotes_vistos_sesion"),
           ("Perfiles nuevos al mes", "perfiles_nuevos")]
    filas_sup = []
    for etiqueta, k in sup:
        if k is None:
            filas_sup.append([etiqueta] + [f"{usos[n]['agricultores']} / {usos[n]['compradores']}" for n in nombres])
        else:
            filas_sup.append([etiqueta] + [str(e[k]) for e in ESCENARIOS])
    derivados = [("Sesiones al mes", "sesiones", "{:,}"), ("Paginas vistas", "paginas", "{:,}"), ("Peticiones web (html, css, js)", "peticiones_web", "{:,}"),
                 ("Llamadas a la api", "llamadas_api", "{:,}"), ("Campanas", "campanas", "{:,}"), ("Fotos subidas (Rekognition)", "fotos", "{:,}"),
                 ("Ofertas", "ofertas", "{:,}"), ("Fotos vistas", "fotos_vistas", "{:,}"), ("Salida a internet (GB)", "gb_salida", "{:.0f}"),
                 ("Bytes que procesa el ALB (GB)", "gb_alb", "{:.1f}"), ("Logs (GB)", "gb_logs", "{:.2f}")]
    filas_der = [[et] + [fmt.format(usos[n][k]) for n in nombres] for et, k, fmt in derivados]

    filas_fijo = []
    for n in nombres:
        ps = por_servicio(n, "costo_lista_usd")
        fijo = sum(v for s, v in ps.items() if s in fijos)
        tot = total(n, "costo_lista_usd")
        filas_fijo.append([n, f"{fijo:.2f}", f"{tot - fijo:.2f}", f"{fijo / tot * 100:.0f}%", f"{tot / 1000:.3f}"])

    filas_precio = [[k, SKUS[k][0], SKUS[k][1], f"{v[0]:.10g}", v[1]] for k, v in p.items()]

    md = f"""# Estimacion de costos AgroCredit a 1000 usuarios activos

Version: {lima} (hora Lima). Generado por `docs/costos/estimar.py` (decision 63). **Estimacion con supuestos, no costo medido**: el gasto real del lab se ve en Cost Explorer (pendiente 9.1).

- Arquitectura: la desplegada hoy (`arquitectura/agrocredit-arquitectura-aws.png`), sin cambios de produccion (sigue HTTP, subredes publicas, sin NAT, sin WAF, sin PITR, logs 1 dia).
- Region us-east-1. Servicio 24x7 (sin el apagado automatico del lab). 2 tareas por servicio en 2 zonas.
- Precios: lista publica de AWS (On-Demand, us-east-1) descargada al generar este archivo; tabla al final.
- Dos columnas por escenario: **lista** (sin capa gratuita) y **con gratis** (solo la capa gratuita permanente: Lambda 1M peticiones y 400k GB-s, SQS 1M, Cognito Essentials 10.000 MAU, 100 GB de salida a internet, 5 GB de logs). No se cuenta la capa gratuita de 12 meses (ALB, S3, Rekognition).

## 1. Supuestos de uso

{tabla_md(["Supuesto"] + nombres, filas_sup)}

Fijos en ambos: pagina promedio {COMUN['pagina_kb']} KB y {COMUN['archivos_pagina']} archivos (medido en `web/`, sin gzip y con `no-store`, se descarga entero en cada pagina); respuesta de api 2 KB; foto 1.5 MB promedio (limite de la api 5 MB, sin redimensionar); fotos acumuladas 12 meses; 3 unidades de lectura por llamada; Lambda 256 MB (worker 0.2 s, etiquetar 1.5 s); sondeo de SQS por Lambda (5 sondeos largos de 20 s por cola, 2 colas).

Derivados:

{tabla_md(["Volumen mensual"] + nombres, filas_der)}

## 2. Resultado mensual (USD)

{tabla_md(["Servicio"] + sum(([f"{n} lista", f"{n} con gratis"] for n in nombres), []), filas_res)}

Costo fijo (Fargate, ALB, IPv4, ECR) frente a variable, precio de lista:

{tabla_md(["Escenario", "Fijo", "Variable", "% fijo", "USD por usuario"], filas_fijo)}

Detalle por componente con los campos para la calculadora: `docs/costos/calculadora.csv`.

## 3. Como cargarlo en calculator.aws

Crear una estimacion por escenario (region US East N. Virginia) y agregar estos servicios con los valores de la columna `calculadora` del CSV:

| Servicio en la calculadora | Que elegir |
|---|---|
| AWS Fargate | Linux, ARM, 4 tareas, 730 h al mes, 0.25 vCPU, 0.5 GB, 20 GB efimero |
| Elastic Load Balancing | Application Load Balancer: 1; bytes procesados, conexiones nuevas/s, duracion, peticiones/s y reglas del CSV |
| Amazon VPC | Public IPv4 addresses: 6 en uso, 730 h (no hay NAT Gateway ni VPN) |
| Amazon DynamoDB | On-Demand, clase Standard, almacenamiento 1 GB, lecturas y escrituras del CSV; sin backups ni streams |
| Amazon SQS | Standard queue, peticiones del CSV |
| AWS Lambda | arm64, 2 funciones: invocaciones y duracion del CSV, 256 MB, efimero 512 MB |
| Amazon S3 | S3 Standard: GB del CSV, PUT/COPY/POST y GET del CSV |
| Amazon Rekognition | Image: DetectLabels (grupo 2), imagenes del CSV |
| Amazon Cognito | User pool, plan Essentials, 1000 MAU |
| Amazon CloudWatch | Logs: ingesta Standard del CSV, retencion 1 dia |
| Amazon ECR | almacenamiento 0.7 GB |
| Data Transfer | Internet (outbound) desde us-east-1, GB del CSV |

Sin costo y fuera de la calculadora: EventBridge Scheduler (solo se usa en el lab; 14M invocaciones gratis), SSM Parameter Store estandar, CloudFormation (sin extensiones de terceros), VPC, subredes, Internet Gateway, grupos de seguridad.

## 4. Lectura y costos ocultos

- A 1000 usuarios **domina el costo fijo**: Fargate, ALB y las IPv4 publicas cuestan lo mismo con 10 o con 1000 usuarios. Las 2 tareas por servicio existen por resiliencia (decision 4), no por carga.
- **IPv4 publicas** (6 x USD 3.65) cuestan mas que la hora del ALB: es el costo de no tener NAT (decision 9). Con NAT seria peor (~USD 33/mes por zona mas datos); la alternativa barata para produccion son subredes privadas con VPC endpoints.
- **Fotos sin miniaturas**: en el escenario alto la salida a internet de fotos es el mayor costo variable. Miniaturas al etiquetar o CloudFront (1 TB/mes gratis) lo bajarian; no se implementa (cambio de diseno).
- **Web sin compresion ni cache** (`no-store`): cada pagina baja ~176 KB. gzip y cache de css/js reducirian la salida y las peticiones al ALB.
- **Sondeo de SQS**: Lambda sondea las colas aunque no haya mensajes (~1.3M peticiones/mes); con la capa gratuita es casi gratis, sin ella ~USD 0.5.
- **Chequeos de salud cada 5 s** (decision 46) llenan logs: ~0.4 GB/mes sin trafico de usuarios.
- **Cognito**: gratis hasta 10.000 MAU en Essentials; en plan Plus no hay capa gratuita (USD 0.02/MAU). El correo por defecto de Cognito (~50/dia) no alcanza para produccion: SES tendria costo propio.
- No incluido: impuestos, soporte de AWS, dominio y certificado (HTTPS), WAF, backups/PITR, CMK de KMS, entornos de prueba y desarrollo, mano de obra. Un entorno regulado agregaria varios de estos (ver `docs/seguridad.md`, pendiente 9.6).
- Capacidad: que 2 tareas de 0.25 vCPU basten para el escenario alto (~{usos['alto']['req_s']:.1f} peticiones/s promedio, picos estimados x10) es **supuesto sin prueba de carga**.

## 5. Precios unitarios usados (lista publica de AWS, us-east-1)

{tabla_md(["Clave", "Servicio", "Usage type", "USD", "Unidad"], filas_precio)}
"""
    (AQUI / "costos.md").write_text(md, encoding="utf-8")
    for n in nombres:
        print(f"{n}: lista USD {total(n, 'costo_lista_usd'):.2f}/mes, con gratis USD {total(n, 'costo_con_gratis_usd'):.2f}/mes")
    print("escrito: costos.md, calculadora.csv")


if __name__ == "__main__":
    main()
