#!/usr/bin/env bash
# =============================================================================
# setup_lightpanda_ubuntu.sh
# =============================================================================
# Script de instalacion y configuracion de Lightpanda en Ubuntu / WSL2.
#
# Lightpanda es un navegador headless que expone el Chrome DevTools Protocol
# (CDP) en el puerto 9222. El Motor Core (FastAPI) se conecta a el para
# extraer texto limpio de paginas web.
#
# Uso:
#   chmod +x scripts/setup_lightpanda_ubuntu.sh
#   ./scripts/setup_lightpanda_ubuntu.sh
#
# Requisitos:
#   - Ubuntu 20.04+ (o WSL2 con Ubuntu)
#   - Usuario con sudo
#   - Conexion a internet
# =============================================================================
set -euo pipefail

# -----------------------------------------------------------------------------
# Colores para output
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# -----------------------------------------------------------------------------
# Variables configurables
# -----------------------------------------------------------------------------
LIGHTPANDA_PORT="${LIGHTPANDA_PORT:-9222}"
LIGHTPANDA_HOST="${LIGHTPANDA_HOST:-127.0.0.1}"
NODE_VERSION="${NODE_VERSION:-20}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/lightpanda}"
SERVICE_NAME="lightpanda"

echo "============================================================"
echo "  Instalador de Lightpanda para Ubuntu / WSL2"
echo "============================================================"
echo ""

# -----------------------------------------------------------------------------
# 0. Verificar que estamos en Ubuntu / Debian
# -----------------------------------------------------------------------------
if ! command -v apt-get >/dev/null 2>&1; then
  log_error "Este diseno esta pensado para Ubuntu/Debian (apt-get)."
  exit 1
fi

log_info "Paso 1/7 - Actualizando paquetes del sistema..."
sudo apt-get update -y
sudo apt-get install -y curl wget gnupg ca-certificates git build-essential
log_ok "Dependencias del sistema instaladas."

# -----------------------------------------------------------------------------
# 1. Instalar Node.js (Lightpanda requiere Node)
# -----------------------------------------------------------------------------
log_info "Paso 2/7 - Instalando Node.js v${NODE_VERSION}..."
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | sudo -E bash -
  sudo apt-get install -y nodejs
else
  log_warn "Node.js ya esta instalado: $(node --version)"
fi
log_ok "Node.js $(node --version) listo."

# -----------------------------------------------------------------------------
# 2. Instalar Lightpanda via npm
# -----------------------------------------------------------------------------
log_info "Paso 3/7 - Instalando Lightpanda (npm)..."
mkdir -p "${INSTALL_DIR}"
cd "${INSTALL_DIR}"

if [ ! -f package.json ]; then
  npm init -y >/dev/null 2>&1 || true
fi

# Instalar lightpanda (paquete oficial)
npm install lightpanda@latest --save >/dev/null 2>&1 || {
  log_warn "No se pudo instalar lightpanda@latest via npm. Intentando alternativa..."
  npm install lightpanda --save >/dev/null 2>&1 || true
}

log_ok "Lightpanda instalado en ${INSTALL_DIR}."

# -----------------------------------------------------------------------------
# 3. Crear script de arranque de Lightpanda
# -----------------------------------------------------------------------------
log_info "Paso 4/7 - Creando script de arranque de Lightpanda..."
cat > "${INSTALL_DIR}/start_lightpanda.sh" <<EOF
#!/usr/bin/env bash
# Arranca Lightpanda exponiendo CDP en ${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}
cd "${INSTALL_DIR}"
export LIGHTPANDA_PORT=${LIGHTPANDA_PORT}
export LIGHTPANDA_HOST=${LIGHTPANDA_HOST}
node node_modules/lightpanda/dist/server.js \
  --host "${LIGHTPANDA_HOST}" \
  --port "${LIGHTPANDA_PORT}" \
  --headless \
  --no-sandbox \
  --disable-gpu
EOF
chmod +x "${INSTALL_DIR}/start_lightpanda.sh"
log_ok "Script de arranque creado en ${INSTALL_DIR}/start_lightpanda.sh."

# -----------------------------------------------------------------------------
# 4. Crear servicio systemd (para que corra en segundo plano)
# -----------------------------------------------------------------------------
log_info "Paso 5/7 - Creando servicio systemd '${SERVICE_NAME}'..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service >/dev/null <<EOF
[Unit]
Description=Lightpanda Headless Browser (CDP on port ${LIGHTPANDA_PORT})
After=network.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/start_lightpanda.sh
Restart=always
RestartSec=5
Environment="LIGHTPANDA_PORT=${LIGHTPANDA_PORT}"
Environment="LIGHTPANDA_HOST=${LIGHTPANDA_HOST}"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
log_ok "Servicio systemd '${SERVICE_NAME}' creado y habilitado."

# -----------------------------------------------------------------------------
# 5. Abrir puerto en el firewall (ufw)
# -----------------------------------------------------------------------------
log_info "Paso 6/7 - Configurando firewall (ufw)..."
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow ${LIGHTPANDA_PORT}/tcp || true
  log_ok "Puerto ${LIGHTPANDA_PORT} abierto en ufw."
else
  log_warn "ufw no instalado. Abre manualmente el puerto ${LIGHTPANDA_PORT}/tcp si usas firewall externo."
fi

# -----------------------------------------------------------------------------
# 6. Iniciar Lightpanda
# -----------------------------------------------------------------------------
log_info "Paso 7/7 - Iniciando Lightpanda..."
sudo systemctl start ${SERVICE_NAME} || {
  log_warn "No se pudo iniciar via systemd. Intentando arranque manual..."
  nohup "${INSTALL_DIR}/start_lightpanda.sh" > "${INSTALL_DIR}/lightpanda.log" 2>&1 &
  echo $! > "${INSTALL_DIR}/lightpanda.pid"
  sleep 3
}

# Esperar a que Lightpanda responda
log_info "Esperando a que Lightpanda este disponible en http://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}..."
for i in $(seq 1 30); do
  if curl -sf "http://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}/json/version" >/dev/null 2>&1; then
    log_ok "Lightpanda esta corriendo y responde en http://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}"
    break
  fi
  if [ "$i" -eq 30 ]; then
    log_error "Lightpanda no responde despues de 30 intentos."
    echo ""
    echo "Logs de Lightpanda:"
    cat "${INSTALL_DIR}/lightpanda.log" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done

# -----------------------------------------------------------------------------
# Resumen final
# -----------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  Instalacion de Lightpanda completada"
echo "============================================================"
echo ""
echo "  Endpoint CDP:  http://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}"
echo "  WebSocket:     ws://${LIGHTPANDA_HOST}:${LIGHTPANDA_PORT}/"
echo "  Logs:          ${INSTALL_DIR}/lightpanda.log"
echo "  Servicio:      systemctl status ${SERVICE_NAME}"
echo ""
echo "  Para detener:    sudo systemctl stop ${SERVICE_NAME}"
echo "  Para reiniciar:  sudo systemctl restart ${SERVICE_NAME}"
echo ""
echo "  Siguiente paso:"
echo "    1. En el worktree feature/panda-core, copia .env.example a .env"
echo "    2. Pon tu OPENCODE_API_KEY real en .env"
echo "    3. Ejecuta: pip install -r requirements-core.txt"
echo "    4. Ejecuta: python -m uvicorn core.main:app --host 0.0.0.0 --port 8000"
echo ""
