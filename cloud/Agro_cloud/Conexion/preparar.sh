#!/usr/bin/env bash
#uso en mac/linux: bash ./preparar.sh
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "falta python3"
  exit 1
fi

#crea el entorno solo si no existe
[ -d .venv ] || python3 -m venv .venv

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/aws --version
echo "listo: ahora ejecuta source ./conectar.sh"
