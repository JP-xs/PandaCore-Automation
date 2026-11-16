# =============================================================================
# run_core.ps1 — Script de arranque del Motor Core (FastAPI)
# Worktree: feature/panda-core  (Windows PowerShell)
# =============================================================================
$ErrorActionPreference = "Stop"

$WORKDIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $WORKDIR

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  JPxs-LightPanda-AI — Motor Core (FastAPI)" -ForegroundColor Cyan
Write-Host "  Directorio: $WORKDIR" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Verificar que existe .env; si no, copiar desde .env.example
if (!(Test-Path ".env")) {
    Write-Host "[INFO] No se encontro .env. Copiando desde .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "[INFO] Edita .env con tus API keys reales antes de seguir." -ForegroundColor Yellow
}

# 2. Instalar dependencias si no estan presentes
$moduleFound = $false
try {
    $moduleFound = (Get-Module -ListAvailable -Name fastapi) -ne $null
} catch {}

if (-not $moduleFound) {
    Write-Host "[INFO] Instalando dependencias de Python..." -ForegroundColor Yellow
    pip install -r requirements-core.txt
}

# 3. Mostrar configuracion clave
$envLine = Select-String -Path ".env" -Pattern "^LIGHT_PANDA_URL=" | Select-Object -First 1
if ($envLine) {
    $lightpandaUrl = $envLine.Line.Split("=")[1]
    Write-Host "[INFO] LIGHT_PANDA_URL=$lightpandaUrl" -ForegroundColor Green
}
Write-Host "[INFO] Puerto Core: 8000" -ForegroundColor Green

# 4. Arrancar el servidor
Write-Host "[INFO] Iniciando servidor en http://0.0.0.0:8000 ..." -ForegroundColor Green
Write-Host "[INFO] Documentacion: http://0.0.0.0:8000/docs" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

python -m uvicorn core.main:app --host 0.0.0.0 --port 8000 --reload
