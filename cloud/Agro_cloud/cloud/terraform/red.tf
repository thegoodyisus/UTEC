#red propia: no depende de la vpc por defecto (algunas cuentas no la tienen)
#sin nat gateway por costo: subredes publicas con ip publica (decision 9)
locals {
  zonas = slice(sort(data.aws_availability_zones.zonas.names), 0, 2)
}

resource "aws_vpc" "red" {
  cidr_block           = var.cidr_vpc
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.prefijo}red" }
}

resource "aws_subnet" "publica" {
  for_each = { for i, z in local.zonas : z => i }

  vpc_id                  = aws_vpc.red.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.cidr_vpc, 24 - tonumber(split("/", var.cidr_vpc)[1]), each.value + 1)
  map_public_ip_on_launch = true

  tags = { Name = "${var.prefijo}publica-${each.value + 1}" }
}

resource "aws_internet_gateway" "salida" {
  vpc_id = aws_vpc.red.id

  tags = { Name = "${var.prefijo}igw" }
}

resource "aws_route_table" "publica" {
  vpc_id = aws_vpc.red.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.salida.id
  }

  tags = { Name = "${var.prefijo}rutas-publicas" }
}

resource "aws_route_table_association" "publica" {
  for_each = aws_subnet.publica

  subnet_id      = each.value.id
  route_table_id = aws_route_table.publica.id
}
