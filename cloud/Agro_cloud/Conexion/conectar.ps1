#uso en windows: . .\conectar.ps1
$cred = Join-Path $PSScriptRoot "credenciales.txt"
$region = "us-east-1"

if (-not (Test-Path $cred)) {
  Set-Content -Path $cred -Value "[default]`naws_access_key_id=PEGAR_AQUI`naws_secret_access_key=PEGAR_AQUI`naws_session_token=PEGAR_AQUI"
}

if (Select-String -Path $cred -Pattern "PEGAR_" -Quiet) {
  Write-Host "credenciales.txt tiene el texto de ejemplo: pega el bloque de AWS CLI del lab"
  return
}

#las credenciales viven solo en este archivo, no en ~/.aws
$env:AWS_SHARED_CREDENTIALS_FILE = $cred
$env:AWS_DEFAULT_REGION = $region
$env:AWS_PAGER = ""
Remove-Item Env:AWS_ACCESS_KEY_ID, Env:AWS_SECRET_ACCESS_KEY, Env:AWS_SESSION_TOKEN, Env:AWS_PROFILE -ErrorAction SilentlyContinue

#usa el aws del .venv si existe
$venvBin = Join-Path $PSScriptRoot ".venv\Scripts"
if (Test-Path (Join-Path $venvBin "aws.exe")) { $env:PATH = "$venvBin;$env:PATH" }

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
  Write-Host "no se encontro aws cli: ejecuta .\preparar.ps1"
  return
}

aws sts get-caller-identity --query "[Account,Arn]" --output text
if ($LASTEXITCODE -eq 0) {
  Write-Host "conexion ok, region $region"
} else {
  Write-Host "credenciales vencidas o invalidas: pega un bloque nuevo en credenciales.txt"
}
