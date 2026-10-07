#colas estandar con dlq (decision 5); idempotencia por escritura condicional en dynamodb
#visibilidad = 6 veces el tiempo maximo de la lambda (30 s), recomendacion de aws
locals {
  colas = {
    insercion = "registros de campanas y ofertas que envia la api"
    fotos     = "eventos de s3 por fotos nuevas en entrada/"
  }
}

resource "aws_sqs_queue" "dlq" {
  for_each = local.colas

  name                      = "${var.prefijo}${each.key}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "cola" {
  for_each = local.colas

  name                       = "${var.prefijo}${each.key}"
  visibility_timeout_seconds = 180
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 3
  })
}

#la dlq solo acepta mensajes de su cola
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  for_each = local.colas

  queue_url = aws_sqs_queue.dlq[each.key].id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.cola[each.key].arn]
  })
}

#s3 puede publicar en la cola de fotos, solo desde nuestro bucket y nuestra cuenta
resource "aws_sqs_queue_policy" "fotos" {
  queue_url = aws_sqs_queue.cola["fotos"].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "s3PublicaFotos"
      Effect    = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.cola["fotos"].arn
      Condition = {
        ArnEquals    = { "aws:SourceArn" = local.bucket_fotos_arn }
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.actual.account_id }
      }
    }]
  })
}
