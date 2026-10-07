variable "prefijo" {
  description = "prefijo de todos los recursos; destruir --por-prefijo borra todo lo que empiece asi"
  type        = string
  default     = "agro-"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{1,9}-$", var.prefijo))
    error_message = "el prefijo debe ser minusculas y numeros, de 2 a 10 caracteres, y terminar en guion. ejemplo: agro-"
  }
}

variable "region" {
  description = "region de aws; el learner lab solo permite us-east-1"
  type        = string
  default     = "us-east-1"

  validation {
    condition     = var.region == "us-east-1"
    error_message = "el learner lab solo permite us-east-1"
  }
}

variable "tareas_por_servicio" {
  description = "replicas de cada servicio ecs (web y api), una por zona como minimo"
  type        = number
  default     = 2

  validation {
    condition     = var.tareas_por_servicio >= 1 && var.tareas_por_servicio <= 4
    error_message = "tareas_por_servicio debe estar entre 1 y 4"
  }
}

variable "horas_apagado" {
  description = "horas despues de cada despliegue en que las tareas se apagan solas"
  type        = number
  default     = 2

  validation {
    condition     = var.horas_apagado >= 1 && var.horas_apagado <= 4
    error_message = "horas_apagado debe estar entre 1 y 4 (la sesion del lab dura unas 4 h)"
  }
}

variable "cidr_vpc" {
  description = "rango de la red propia; se parte en subredes /24"
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.cidr_vpc, 0)) && tonumber(split("/", var.cidr_vpc)[1]) <= 20
    error_message = "cidr_vpc debe ser un rango valido de /16 a /20, ejemplo 10.20.0.0/16"
  }
}

#las tres siguientes las pone tareas.py en cada corrida; no van en parametros.tfvars
variable "imagen_web" {
  description = "uri:tag de la imagen web en ecr"
  type        = string
}

variable "imagen_api" {
  description = "uri:tag de la imagen api en ecr"
  type        = string
}

variable "marca_despliegue" {
  description = "marca de tiempo de la corrida; renueva el instante de apagado"
  type        = string
}

variable "token_demo" {
  description = "token del endpoint de caida brusca de la demo; lo genera tareas.py"
  type        = string
  sensitive   = true
}

#zips de las lambdas: los arma tareas.py en cloud/.construccion con el hash del contenido en el nombre
variable "zip_worker" {
  description = "ruta del zip de la lambda worker"
  type        = string
}

variable "zip_etiquetar" {
  description = "ruta del zip de la lambda etiquetar"
  type        = string
}
