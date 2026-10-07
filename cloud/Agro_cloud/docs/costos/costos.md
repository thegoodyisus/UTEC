# Estimacion de costos AgroCredit a 1000 usuarios activos

Version: 2026-10-06 14:28 (hora Lima). Generado por `docs/costos/estimar.py` (decision 63). **Estimacion con supuestos, no costo medido**: el gasto real del lab se ve en Cost Explorer (pendiente 9.1).

- Arquitectura: la desplegada hoy (`arquitectura/agrocredit-arquitectura-aws.png`), sin cambios de produccion (sigue HTTP, subredes publicas, sin NAT, sin WAF, sin PITR, logs 1 dia).
- Region us-east-1. Servicio 24x7 (sin el apagado automatico del lab). 2 tareas por servicio en 2 zonas.
- Precios: lista publica de AWS (On-Demand, us-east-1) descargada al generar este archivo; tabla al final.
- Dos columnas por escenario: **lista** (sin capa gratuita) y **con gratis** (solo la capa gratuita permanente: Lambda 1M peticiones y 400k GB-s, SQS 1M, Cognito Essentials 10.000 MAU, 100 GB de salida a internet, 5 GB de logs). No se cuenta la capa gratuita de 12 meses (ALB, S3, Rekognition).

## 1. Supuestos de uso

| Supuesto | moderado | alto |
|---|---|---|
| Usuarios activos al mes | 1000 | 1000 |
| Agricultores / compradores | 700 / 300 | 700 / 300 |
| Sesiones por usuario al mes | 15 | 30 |
| Paginas por sesion | 8 | 12 |
| Llamadas a la api por sesion | 25 | 40 |
| Campanas por agricultor al mes | 1 | 2 |
| Fotos por campana | 3 | 5 |
| Ofertas por comprador al mes | 5 | 15 |
| Lotes vistos por sesion de comprador | 3 | 6 |
| Perfiles nuevos al mes | 100 | 200 |

Fijos en ambos: pagina promedio 176 KB y 10 archivos (medido en `web/`, sin gzip y con `no-store`, se descarga entero en cada pagina); respuesta de api 2 KB; foto 1.5 MB promedio (limite de la api 5 MB, sin redimensionar); fotos acumuladas 12 meses; 3 unidades de lectura por llamada; Lambda 256 MB (worker 0.2 s, etiquetar 1.5 s); sondeo de SQS por Lambda (5 sondeos largos de 20 s por cola, 2 colas).

Derivados:

| Volumen mensual | moderado | alto |
|---|---|---|
| Sesiones al mes | 15,000 | 30,000 |
| Paginas vistas | 120,000 | 360,000 |
| Peticiones web (html, css, js) | 1,200,000 | 3,600,000 |
| Llamadas a la api | 375,000 | 1,200,000 |
| Campanas | 700 | 1,400 |
| Fotos subidas (Rekognition) | 2,100 | 7,000 |
| Ofertas | 1,500 | 4,500 |
| Fotos vistas | 42,600 | 277,000 |
| Salida a internet (GB) | 83 | 468 |
| Bytes que procesa el ALB (GB) | 20.9 | 62.7 |
| Logs (GB) | 0.78 | 1.58 |

## 2. Resultado mensual (USD)

| Servicio | moderado lista | moderado con gratis | alto lista | alto con gratis |
|---|---|---|---|---|
| AWS Fargate (ECS) | 28.84 | 28.84 | 28.84 | 28.84 |
| Elastic Load Balancing (ALB) | 16.60 | 16.60 | 16.93 | 16.93 |
| Amazon VPC | 21.90 | 21.90 | 21.90 | 21.90 |
| Amazon DynamoDB | 0.15 | 0.15 | 0.48 | 0.48 |
| Amazon SQS | 0.53 | 0.13 | 0.54 | 0.14 |
| AWS Lambda | 0.01 | 0.00 | 0.04 | 0.00 |
| Amazon S3 | 0.89 | 0.89 | 3.01 | 3.01 |
| Amazon Rekognition | 2.10 | 2.10 | 7.00 | 7.00 |
| Amazon Cognito | 15.00 | 0.00 | 15.00 | 0.00 |
| Amazon CloudWatch | 0.39 | 0.00 | 0.79 | 0.00 |
| Amazon ECR | 0.07 | 0.07 | 0.07 | 0.07 |
| Transferencia de datos | 7.49 | 0.00 | 42.16 | 33.16 |
| **Total mensual** | **93.97** | **70.68** | **136.76** | **111.53** |

Costo fijo (Fargate, ALB, IPv4, ECR) frente a variable, precio de lista:

| Escenario | Fijo | Variable | % fijo | USD por usuario |
|---|---|---|---|---|
| moderado | 67.41 | 26.56 | 72% | 0.094 |
| alto | 67.74 | 69.02 | 50% | 0.137 |

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
- Capacidad: que 2 tareas de 0.25 vCPU basten para el escenario alto (~1.8 peticiones/s promedio, picos estimados x10) es **supuesto sin prueba de carga**.

## 5. Precios unitarios usados (lista publica de AWS, us-east-1)

| Clave | Servicio | Usage type | USD | Unidad |
|---|---|---|---|---|
| fargate_vcpu | AmazonECS | USE1-Fargate-ARM-vCPU-Hours:perCPU | 0.03238 | hours |
| fargate_gb | AmazonECS | USE1-Fargate-ARM-GB-Hours | 0.00356 | hours |
| alb_hora | AWSELB | LoadBalancerUsage | 0.0225 | Hrs |
| alb_lcu | AWSELB | LCUUsage | 0.008 | LCU-Hrs |
| ipv4 | AmazonVPC | USE1-PublicIPv4:InUseAddress | 0.005 | Hrs |
| ddb_lectura | AmazonDynamoDB | ReadRequestUnits | 1.25e-07 | ReadRequestUnits |
| ddb_escritura | AmazonDynamoDB | WriteRequestUnits | 6.25e-07 | WriteRequestUnits |
| ddb_gb | AmazonDynamoDB | TimedStorage-ByteHrs | 0.25 | GB-Mo |
| sqs | AWSQueueService | Requests-RBP | 4e-07 | Requests |
| lambda_gbs | AWSLambda | Lambda-GB-Second-ARM | 1.33334e-05 | Lambda-GB-Second |
| lambda_req | AWSLambda | Request-ARM | 2e-07 | Requests |
| s3_gb | AmazonS3 | TimedStorage-ByteHrs | 0.023 | GB-Mo |
| s3_put | AmazonS3 | Requests-Tier1 | 5e-06 | Requests |
| s3_get | AmazonS3 | Requests-Tier2 | 4e-07 | Requests |
| rekognition | AmazonRekognition | USE1-Group2-ImagesProcessed | 0.001 | Images Processed |
| cognito | AmazonCognito | USE1-CognitoEssentialsMAU | 0.015 | CognitoUserPoolsMAU |
| logs_gb | AmazonCloudWatch | DataProcessing-Bytes | 0.5 | GB |
| logs_alm | AmazonCloudWatch | TimedStorage-ByteHrs | 0.03 | GB-Mo |
| ecr_gb | AmazonECR | TimedStorage-ByteHrs | 0.1 | GB-Mo |
| dto | AWSDataTransfer | DataTransfer-Out-Bytes | 0.09 | GB |
