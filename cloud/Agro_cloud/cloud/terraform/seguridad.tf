#puertos de los contenedores: provisionales hasta el paso 7
locals {
  puerto_web = 80
  puerto_api = 8000
}

#alb: entra http 80 desde internet (decision 31); sale solo hacia las tareas
resource "aws_security_group" "alb" {
  name        = "${var.prefijo}alb"
  description = "alb publico http"
  vpc_id      = aws_vpc.red.id

  tags = { Name = "${var.prefijo}alb" }
}

resource "aws_vpc_security_group_ingress_rule" "alb_http" {
  security_group_id = aws_security_group.alb.id
  description       = "http desde internet"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "alb_a_web" {
  security_group_id            = aws_security_group.alb.id
  description                  = "hacia tareas web"
  ip_protocol                  = "tcp"
  from_port                    = local.puerto_web
  to_port                      = local.puerto_web
  referenced_security_group_id = aws_security_group.tareas.id
}

resource "aws_vpc_security_group_egress_rule" "alb_a_api" {
  security_group_id            = aws_security_group.alb.id
  description                  = "hacia tareas api"
  ip_protocol                  = "tcp"
  from_port                    = local.puerto_api
  to_port                      = local.puerto_api
  referenced_security_group_id = aws_security_group.tareas.id
}

#tareas: solo reciben del alb; salen solo por https (ecr, cognito, dynamodb, sqs, s3, logs)
resource "aws_security_group" "tareas" {
  name        = "${var.prefijo}tareas"
  description = "tareas ecs, solo desde el alb"
  vpc_id      = aws_vpc.red.id

  tags = { Name = "${var.prefijo}tareas" }
}

resource "aws_vpc_security_group_ingress_rule" "tareas_web" {
  security_group_id            = aws_security_group.tareas.id
  description                  = "web desde el alb"
  ip_protocol                  = "tcp"
  from_port                    = local.puerto_web
  to_port                      = local.puerto_web
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_ingress_rule" "tareas_api" {
  security_group_id            = aws_security_group.tareas.id
  description                  = "api desde el alb"
  ip_protocol                  = "tcp"
  from_port                    = local.puerto_api
  to_port                      = local.puerto_api
  referenced_security_group_id = aws_security_group.alb.id
}

resource "aws_vpc_security_group_egress_rule" "tareas_https" {
  security_group_id = aws_security_group.tareas.id
  description       = "https hacia servicios de aws"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}
