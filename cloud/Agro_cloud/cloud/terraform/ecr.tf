#repositorios privados de imagenes (fase 1 de desplegar los crea con -target)
#escaneo de imagenes apagado por costo: limitacion documentada
locals {
  servicios = toset(["web", "api"])
}

resource "aws_ecr_repository" "repo" {
  for_each = local.servicios

  name                 = "${var.prefijo}${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }
}

#se conservan las 5 imagenes mas recientes
resource "aws_ecr_lifecycle_policy" "repo" {
  for_each = local.servicios

  repository = aws_ecr_repository.repo[each.key].name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "conservar 5 imagenes"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}
