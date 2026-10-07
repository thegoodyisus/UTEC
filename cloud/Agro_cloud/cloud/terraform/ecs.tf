#contenedores fargate arm64 (decisiones 4, 9 y 29): 2 servicios, minimo 2 tareas en 2 zonas
#las imagenes las construye y sube tareas.py (fase 2) y las pasa como variables
resource "aws_ecs_cluster" "cluster" {
  name = "${var.prefijo}cluster"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

#log groups explicitos para que destruir los borre
resource "aws_cloudwatch_log_group" "ecs" {
  for_each = local.servicios

  name              = "/ecs/${var.prefijo}${each.key}"
  retention_in_days = 1
}

locals {
  entorno_api = {
    TABLA                 = aws_dynamodb_table.datos.name
    TABLA_PADRON_PERSONAS = aws_dynamodb_table.padron["personas"].name
    TABLA_PADRON_EMPRESAS = aws_dynamodb_table.padron["empresas"].name
    COLA_INSERCION_URL    = aws_sqs_queue.cola["insercion"].url
    BUCKET_FOTOS          = aws_cloudformation_stack.fotos.outputs["Nombre"]
    USER_POOL_ID          = aws_cognito_user_pool.usuarios.id
    CLIENT_ID             = aws_cognito_user_pool_client.web.id
    REGION_AWS            = var.region
    TAREA_VERSION         = element(split(":", var.imagen_api), length(split(":", var.imagen_api)) - 1)
    DEMO_TOKEN            = var.token_demo
  }
  contenedores = {
    web = { imagen = var.imagen_web, puerto = local.puerto_web, entorno = {} }
    api = { imagen = var.imagen_api, puerto = local.puerto_api, entorno = local.entorno_api }
  }
}

resource "aws_ecs_task_definition" "tarea" {
  for_each = local.contenedores

  family                   = "${var.prefijo}${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = data.aws_iam_role.lab.arn
  task_role_arn            = data.aws_iam_role.lab.arn

  runtime_platform {
    cpu_architecture        = "ARM64"
    operating_system_family = "LINUX"
  }

  container_definitions = jsonencode([{
    name         = each.key
    image        = each.value.imagen
    essential    = true
    stopTimeout  = 10
    portMappings = [{ containerPort = each.value.puerto, protocol = "tcp" }]
    environment  = [for k in sort(keys(each.value.entorno)) : { name = k, value = each.value.entorno[k] }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ecs[each.key].name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = each.key
      }
    }
  }])

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_ecs_service" "servicio" {
  for_each = local.contenedores

  name                               = "${var.prefijo}${each.key}"
  cluster                            = aws_ecs_cluster.cluster.id
  task_definition                    = aws_ecs_task_definition.tarea[each.key].arn
  launch_type                        = "FARGATE"
  desired_count                      = var.tareas_por_servicio
  health_check_grace_period_seconds  = 30
  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
  wait_for_steady_state              = true

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = [for s in aws_subnet.publica : s.id]
    security_groups  = [aws_security_group.tareas.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.tg[each.key].arn
    container_name   = each.key
    container_port   = each.value.puerto
  }

  #el apagado automatico y tareas.py apagar/encender cambian desired_count fuera de terraform
  lifecycle {
    ignore_changes = [desired_count]
  }

  depends_on = [aws_lb_listener_rule.api, aws_lb_listener.http]
}
