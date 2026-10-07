#uso en windows: .\preparar.ps1
Set-Location $PSScriptRoot

$py = "python"
if (Get-Command py -ErrorAction SilentlyContinue) { $py = "py" }

#crea el entorno solo si no existe
if (-not (Test-Path ".venv")) { & $py -m venv .venv }

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\aws.exe --version
Write-Host "listo: ahora ejecuta . .\conectar.ps1"
