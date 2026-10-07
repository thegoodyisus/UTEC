#versiones exactas: todos los companeros usan lo mismo (decision 39)
terraform {
  required_version = "= 1.16.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.67.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "= 0.14.2"
    }
  }
}

#credenciales: las pone tareas.py desde Conexion/credenciales.txt
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      proyecto   = "agrocredit"
      prefijo    = var.prefijo
      gestionado = "terraform"
    }
  }
}

data "aws_caller_identity" "actual" {}

#el lab no deja crear roles: todo usa LabRole
data "aws_iam_role" "lab" {
  name = "LabRole"
}

data "aws_availability_zones" "zonas" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}
