#!/usr/bin/env bash
# =============================================================================
# run_core.sh — Script de arranque del Motor Core (FastAPI)
# Worktree: feature/panda-core  (WSL2 / Linux)
# =============================================================================
set -euo pipefail

WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORKDIR"

echo "============================================================"
echo "  JPxs-LightPanda-AI — Motor Core (FastAPI)"
echo "  Directorio: $WORKDIR"
echo "============================================================"

# 1. Verificar que existe .env; si no, copiar desde .env.example
if [ ! -f .env ]; then
    echo "[INFO] No se encontro .env. Copiando desde .env.example..."
    cp .env.example .env
    echo "[INFO] Edita .env con tus API keys reales antes de seguir."
fi

# 2. Instalar dependencias si no estan presentes
if ! python -c "import fastapi" 2>/dev/null; then
    echo "[INFO] Instalando dependencias de Python..."
    pip install -r requirements-core.txt
fi

# 3. Mostrar configuracion clave
echo "[INFO] LIGHT_PANDA_URL=$(grep '^LIGHT_PANDA_URL=' .env | cut -d= -f2)"
echo "[INFO] Puerto Core: 8000"

# 4. Arrancar el servidor
echo "[INFO] Iniciando servidor en http://0.0.0.0:8000 ..."
echo "[INFO] Documentacion: http://0.0.0.0:8000/docs"
echo "============================================================"

python -m uvicorn core.main:app --host 0.0.0.0 --port 8000 --reload
