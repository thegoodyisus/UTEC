output "cuenta" {
  value = data.aws_caller_identity.actual.account_id
}

output "vpc" {
  value = aws_vpc.red.id
}

output "subredes" {
  value = [for s in aws_subnet.publica : s.id]
}

output "zonas" {
  value = local.zonas
}

output "sg_alb" {
  value = aws_security_group.alb.id
}

output "sg_tareas" {
  value = aws_security_group.tareas.id
}

output "registro" {
  value = aws_ssm_parameter.registro.name
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.usuarios.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.web.id
}

output "tabla" {
  value = aws_dynamodb_table.datos.name
}

output "tablas_padron" {
  value = { for k, t in aws_dynamodb_table.padron : k => t.name }
}

output "bucket_fotos" {
  value = aws_cloudformation_stack.fotos.outputs["Nombre"]
}

output "colas" {
  value = { for k, q in aws_sqs_queue.cola : k => q.url }
}

output "alb_dns" {
  value = aws_lb.alb.dns_name
}

output "url" {
  value = "http://${aws_lb.alb.dns_name}/"
}

output "cluster" {
  value = aws_ecs_cluster.cluster.name
}

output "servicios" {
  value = { for k, s in aws_ecs_service.servicio : k => s.name }
}

output "repos" {
  value = { for k, r in aws_ecr_repository.repo : k => r.repository_url }
}

output "apagado_utc" {
  value = local.apagado_utc
}

output "lambdas" {
  value = { for k, f in aws_lambda_function.fn : k => f.function_name }
}
