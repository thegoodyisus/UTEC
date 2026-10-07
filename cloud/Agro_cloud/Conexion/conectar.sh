#!/usr/bin/env bash
#uso en mac/linux: source ./conectar.sh
_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
_cred="$_dir/credenciales.txt"
_region="us-east-1"

if [ ! -f "$_cred" ]; then
  printf "[default]\naws_access_key_id=PEGAR_AQUI\naws_secret_access_key=PEGAR_AQUI\naws_session_token=PEGAR_AQUI\n" > "$_cred"
fi

if grep -q "PEGAR_" "$_cred"; then
  echo "credenciales.txt tiene el texto de ejemplo: pega el bloque de AWS CLI del lab"
  return 1 2>/dev/null || exit 1
fi

#las credenciales viven solo en este archivo, no en ~/.aws
export AWS_SHARED_CREDENTIALS_FILE="$_cred"
export AWS_DEFAULT_REGION="$_region"
export AWS_PAGER=""
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE

#usa el aws del .venv si existe
if [ -x "$_dir/.venv/bin/aws" ]; then
  export PATH="$_dir/.venv/bin:$PATH"
  hash -r 2>/dev/null
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "no se encontro aws cli: ejecuta bash ./preparar.sh"
  return 1 2>/dev/null || exit 1
fi

if aws sts get-caller-identity --query "[Account,Arn]" --output text; then
  echo "conexion ok, region $AWS_DEFAULT_REGION"
else
  echo "credenciales vencidas o invalidas: pega un bloque nuevo en credenciales.txt"
  return 1 2>/dev/null || exit 1
fi
