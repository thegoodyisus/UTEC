#fotos (decision 6): bucket privado; subida a entrada/<sub>/ con url prefirmada; evento a sqs
#el bucket se crea con cloudformation y no con aws_s3_bucket: el proveedor lee la configuracion
#de object lock en cada refresh y el learner lab la niega por scp (s3:GetBucketObjectLockConfiguration).
#cloudformation no hace esa lectura. tareas.py vacia el bucket antes de destruir (cfn no borra buckets con objetos)
#cors: solo el origen del alb puede subir fotos desde el navegador
locals {
  bucket_fotos     = "${var.prefijo}fotos-${data.aws_caller_identity.actual.account_id}"
  bucket_fotos_arn = "arn:aws:s3:::${local.bucket_fotos}"
}

resource "aws_cloudformation_stack" "fotos" {
  name = "${var.prefijo}fotos"

  template_body = jsonencode({
    AWSTemplateFormatVersion = "2010-09-09"
    Description              = "bucket de fotos de agrocredit (gestionado por terraform)"
    Resources = {
      Bucket = {
        Type           = "AWS::S3::Bucket"
        DeletionPolicy = "Delete"
        Properties = {
          BucketName = local.bucket_fotos
          OwnershipControls = {
            Rules = [{ ObjectOwnership = "BucketOwnerEnforced" }]
          }
          PublicAccessBlockConfiguration = {
            BlockPublicAcls       = true
            BlockPublicPolicy     = true
            IgnorePublicAcls      = true
            RestrictPublicBuckets = true
          }
          BucketEncryption = {
            ServerSideEncryptionConfiguration = [{
              ServerSideEncryptionByDefault = { SSEAlgorithm = "AES256" }
            }]
          }
          #entrada/ es temporal: si la lambda no la procesa, se borra sola en 1 dia
          LifecycleConfiguration = {
            Rules = [
              {
                Id               = "expira-entrada"
                Status           = "Enabled"
                Prefix           = "entrada/"
                ExpirationInDays = 1
              },
              {
                Id                             = "limpia-subidas-incompletas"
                Status                         = "Enabled"
                AbortIncompleteMultipartUpload = { DaysAfterInitiation = 1 }
              }
            ]
          }
          CorsConfiguration = {
            CorsRules = [{
              AllowedOrigins = ["http://${aws_lb.alb.dns_name}"]
              AllowedMethods = ["POST", "PUT"]
              AllowedHeaders = ["*"]
              MaxAge         = 300
            }]
          }
          NotificationConfiguration = {
            QueueConfigurations = [{
              Event  = "s3:ObjectCreated:*"
              Queue  = aws_sqs_queue.cola["fotos"].arn
              Filter = { S3Key = { Rules = [{ Name = "prefix", Value = "entrada/" }] } }
            }]
          }
        }
      }
      #solo https hacia el bucket
      Politica = {
        Type = "AWS::S3::BucketPolicy"
        Properties = {
          Bucket = { Ref = "Bucket" }
          PolicyDocument = {
            Version = "2012-10-17"
            Statement = [{
              Sid       = "soloHttps"
              Effect    = "Deny"
              Principal = "*"
              Action    = "s3:*"
              Resource  = [local.bucket_fotos_arn, "${local.bucket_fotos_arn}/*"]
              Condition = { Bool = { "aws:SecureTransport" = "false" } }
            }]
          }
        }
      }
    }
    Outputs = {
      Nombre = { Value = { Ref = "Bucket" } }
    }
  })

  #s3 valida que puede escribir en la cola al crear la notificacion
  depends_on = [aws_sqs_queue_policy.fotos]
}
