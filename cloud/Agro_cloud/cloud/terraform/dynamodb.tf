#tabla unica (docs/modelo-datos.md): pk/sk + indice por-usuario + indice disperso publicadas-por-cultivo (decision 58)
#en los gsi se usa key_schema: hash_key/range_key estan obsoletos ahi desde aws 6.x
resource "aws_dynamodb_table" "datos" {
  name                        = "${var.prefijo}datos"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "PK"
  range_key                   = "SK"
  deletion_protection_enabled = false

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "usuarioClave"
    type = "S"
  }

  attribute {
    name = "usuarioOrden"
    type = "S"
  }

  attribute {
    name = "publicadaClave"
    type = "S"
  }

  attribute {
    name = "publicadaOrden"
    type = "S"
  }

  #campanas y ofertas de cada usuario
  global_secondary_index {
    name            = "por-usuario"
    projection_type = "ALL"

    key_schema {
      attribute_name = "usuarioClave"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "usuarioOrden"
      key_type       = "RANGE"
    }
  }

  #disperso: solo las campanas publicadas llevan publicadaClave
  global_secondary_index {
    name            = "publicadas-por-cultivo"
    projection_type = "ALL"

    key_schema {
      attribute_name = "publicadaClave"
      key_type       = "HASH"
    }

    key_schema {
      attribute_name = "publicadaOrden"
      key_type       = "RANGE"
    }
  }

  #sin pitr: los datos de la demo se pierden al destruir (decision 28)
  point_in_time_recovery {
    enabled = false
  }
}

#padron de demostracion en tablas propias (decision 58): cada registro se borra al asignarse
resource "aws_dynamodb_table" "padron" {
  for_each = toset(["personas", "empresas"])

  name                        = "${var.prefijo}padron-${each.key}"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "id"
  deletion_protection_enabled = false

  attribute {
    name = "id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = false
  }
}
