#identidad (decision 16): usuario = numero de documento, correo obligatorio con codigo, clave = pin de 6 digitos
#el rol se elige al crear la cuenta y no se puede cambiar (custom:rol inmutable)
resource "aws_cognito_user_pool" "usuarios" {
  name                = "${var.prefijo}usuarios"
  deletion_protection = "INACTIVE"
  mfa_configuration   = "OFF"

  username_configuration {
    case_sensitive = false
  }

  auto_verified_attributes = ["email"]

  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  #el pin de 6 digitos se exige en la web; cognito solo permite fijar largo minimo 6
  password_policy {
    minimum_length                   = 6
    require_lowercase                = false
    require_uppercase                = false
    require_numbers                  = false
    require_symbols                  = false
    temporary_password_validity_days = 1
  }

  #correo por defecto de cognito: limite aproximado de 50 por dia por cuenta
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "AgroCredit: tu codigo de verificacion"
    email_message        = "Tu codigo de verificacion de AgroCredit es {####}. Si no creaste una cuenta, ignora este correo."
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 5
      max_length = 254
    }
  }

  schema {
    name                = "rol"
    attribute_data_type = "String"
    required            = false
    mutable             = false

    string_attribute_constraints {
      min_length = 9
      max_length = 11
    }
  }
}

#cliente publico del navegador: sin secreto, solo srp y refresh
resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.prefijo}web"
  user_pool_id = aws_cognito_user_pool.usuarios.id

  generate_secret               = false
  explicit_auth_flows           = ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  id_token_validity      = 60
  access_token_validity  = 60
  refresh_token_validity = 1

  token_validity_units {
    id_token      = "minutes"
    access_token  = "minutes"
    refresh_token = "days"
  }

  read_attributes  = ["email", "email_verified", "custom:rol"]
  write_attributes = ["email", "custom:rol"]
}
