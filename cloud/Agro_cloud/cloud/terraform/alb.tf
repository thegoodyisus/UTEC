#balanceador publico http (decisiones 8 y 31): /api/* -> api ; todo lo demas -> web
#chequeos rapidos y drenaje corto para que la demo de caida haga el cambio en segundos
resource "aws_lb" "alb" {
  name                       = "${var.prefijo}alb"
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [aws_security_group.alb.id]
  subnets                    = [for s in aws_subnet.publica : s.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = false
}

locals {
  destinos = {
    web = { puerto = local.puerto_web, salud = "/salud-web" }
    api = { puerto = local.puerto_api, salud = "/api/v1/salud" }
  }
}

resource "aws_lb_target_group" "tg" {
  for_each = local.destinos

  name                 = "${var.prefijo}${each.key}"
  port                 = each.value.puerto
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.red.id
  deregistration_delay = 10

  health_check {
    path                = each.value.salud
    matcher             = "200"
    interval            = 5
    timeout             = 3
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.alb.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg["web"].arn
  }
}

resource "aws_lb_listener_rule" "api" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg["api"].arn
  }

  condition {
    path_pattern {
      values = ["/api/*"]
    }
  }
}
