#lambdas del corte (decisiones 5 y 6): python 3.12 arm64 con labrole; el zip lo arma tareas.py (hash de contenido)
locals {
  lambdas = {
    worker = {
      zip     = var.zip_worker
      cola    = "insercion"
      lote    = 10
      timeout = 30
      entorno = { TABLA = aws_dynamodb_table.datos.name }
    }
    etiquetar = {
      zip     = var.zip_etiquetar
      cola    = "fotos"
      lote    = 5
      timeout = 30
      entorno = { TABLA = aws_dynamodb_table.datos.name, MIN_CONFIANZA = "70" }
    }
  }
}

#log groups explicitos para que destruir los borre
resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.lambdas

  name              = "/aws/lambda/${var.prefijo}${each.key}"
  retention_in_days = 1
}

resource "aws_lambda_function" "fn" {
  for_each = local.lambdas

  function_name    = "${var.prefijo}${each.key}"
  role             = data.aws_iam_role.lab.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "app.handler"
  filename         = each.value.zip
  source_code_hash = filebase64sha256(each.value.zip)
  timeout          = each.value.timeout
  memory_size      = 256

  environment {
    variables = each.value.entorno
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

#visibilidad de las colas (180 s) = 6 veces el timeout (30 s), recomendacion de aws
resource "aws_lambda_event_source_mapping" "cola" {
  for_each = local.lambdas

  event_source_arn                   = aws_sqs_queue.cola[each.value.cola].arn
  function_name                      = aws_lambda_function.fn[each.key].arn
  batch_size                         = each.value.lote
  maximum_batching_window_in_seconds = 0
  function_response_types            = ["ReportBatchItemFailures"]
}
