#registro de lo que no se identifica por nombre, para destruir --por-prefijo (decision 38)
#lo escribe el mismo apply, asi nunca queda desactualizado
resource "aws_ssm_parameter" "registro" {
  name        = "/${var.prefijo}/registro"
  description = "recursos de agrocredit sin prefijo en el nombre"
  type        = "String"
  tier        = "Standard"

  value = jsonencode({
    cuenta        = data.aws_caller_identity.actual.account_id
    region        = var.region
    prefijo       = var.prefijo
    vpc           = aws_vpc.red.id
    subredes      = [for s in aws_subnet.publica : s.id]
    igw           = aws_internet_gateway.salida.id
    tablas_rutas  = [aws_route_table.publica.id]
    mapeos_lambda = [for m in aws_lambda_event_source_mapping.cola : m.uuid]
  })
}
