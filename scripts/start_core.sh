#!/usr/bin/env bash
# =============================================================================
# start_core.sh
# Arranque rapido del Motor Core (FastAPI) para JPxs-LightPanda-AI
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Creando .env desde .env.example..."
  cp .env.example .env
  echo "IMPORTANTE: Edita .env y pon tu OPENCODE_API_KEY real antes de continuar."
  echo "Luego vuelve a ejecutar este script."
  exit 1
fi

echo "Instalando dependencias de Python..."
pip install -r requirements-core.txt

echo "Arrancando Motor Core en http://0.0.0.0:8000..."
python -m uvicorn core.main:app --host 0.0.0.0 --port 8000 --reload
