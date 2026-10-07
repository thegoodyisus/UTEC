#apagado automatico de las tareas (decisiones 19, 27 y 32): solo eventbridge scheduler
#el instante se renueva en cada despliegue: tareas.py pasa una marca nueva y time_static se recrea
#respaldo probado y no implementado: application auto scaling con accion programada
#el alb sigue cobrando hasta destruir
resource "time_static" "despliegue" {
  triggers = {
    marca = var.marca_despliegue
  }
}

locals {
  apagado_utc = formatdate("YYYY-MM-DD'T'hh:mm:ss", timeadd(time_static.despliegue.rfc3339, "${var.horas_apagado}h"))
}

resource "aws_scheduler_schedule_group" "apagado" {
  name = "${var.prefijo}apagado"
}

resource "aws_scheduler_schedule" "apagar" {
  for_each = local.servicios

  name                         = "${var.prefijo}apagar-${each.key}"
  group_name                   = aws_scheduler_schedule_group.apagado.name
  schedule_expression          = "at(${local.apagado_utc})"
  schedule_expression_timezone = "UTC"
  action_after_completion      = "NONE"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:updateService"
    role_arn = data.aws_iam_role.lab.arn
    input = jsonencode({
      Cluster      = aws_ecs_cluster.cluster.name
      Service      = aws_ecs_service.servicio[each.key].name
      DesiredCount = 0
    })
  }
}
