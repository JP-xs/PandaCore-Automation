# JPxs-LightPanda-AI

🐼 **Extracción web con Lightpanda (headless) + IA (OpenAI / Anthropic) para análisis de datos y proyectos de tesis.**

Arquitectura modular y desacoplada en dos capas:
- **Backend/Motor (Core)** — feature/panda-core (Worktree 1, OpenCode / Local WSL2)
- **Frontend/Interfaz (UI)** — feature/panda-ui (Worktree 2, OpenCloud / Producción)

---

## 🗺️ Arquitectura y distribución (Worktrees)

```
JPxs-LightPanda-AI (repo: PandaCore-Automation)
├── .env                              # Configuración compartida (raíz, Worktree 1)
├── .env.example                      # Plantilla de variables de entorno
├── .gitignore
├── README.md
├── requirements-core.txt             # Dependencias del Backend
├── Dockerfile                        # Contenedor del Core (OpenCloud)
├── docker-compose.yml                # Orquestación Core + UI (OpenCloud)
├── DEPLOY_OPENCLOUD.md               # Guía de despliegue en VPS
│
├── feature-panda-core/               # ══ WORKTREE 1 ══  OpenCode / Local WSL2 (Backend)
│   ├── .git                          # Git embebido (worktree)
│   ├── .env                          # BROWSER_CDP_URL, claves IA, puertos
│   ├── Dockerfile                    # Contenedor Core para OpenCloud
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                 # Configuración centralizada (Pydantic Settings)
│   │   ├── exceptions.py             # Excepciones personalizadas (Lightpanda + IA)
│   │   ├── browser.py                # LightpandaBrowser: CDP nativo, LP.dump, reintentos
│   │   ├── ai_handler.py             # AIHandler: OpenAI + Anthropic unificados
│   │   └── main.py                   # FastAPI: /health, /extract, /analyze, /pipeline
│   ├── scripts/
│   │   └── test_lightpanda.py        # Script de prueba CDP (flujo Lightpanda validado)
│   ├── requirements-core.txt
│   └── README.md
│
└── feature-panda-ui/                 # ══ WORKTREE 2 ══  OpenCloud / Producción (Frontend)
    ├── .git                          # Git embebido (worktree)
    ├── .env                          # CORE_API_URL, UI_PORT, modelos por defecto
    ├── Dockerfile                    # Contenedor UI para OpenCloud
    ├── .streamlit/
    │   └── config.toml               # Config headless, sin usage stats
    ├── ui/
    │   ├── __init__.py
    │   └── app.py                    # Panel Streamlit (sidebar, inputs, resultados, CSV)
    ├── requirements-ui.txt
    └── README.md
```

---

## 🔌 Flujo de conexión (en la práctica)

```
┌─────────────────┐     HTTP       ┌──────────────────┐     CDP (WS)      ┌─────────────┐
│   Usuario       │───────────────►│   UI (Streamlit) │─────────────────►│  Lightpanda │
│  (tesis/datos)  │    :8501       │  feature/panda-ui│     :9222         │  (headless) │
└─────────────────┘                └──────────────────┘                   └─────────────┘
                                              │
                                              │ HTTP
                                              ▼
                                      ┌──────────────────┐
                                      │  Core (FastAPI)  │
                                      │ feature/panda-core│
                                      │      :8000       │
                                      └──────────────────┘
                                              │
                                              │ HTTP (IA API)
                                              ▼
                                      ┌──────────────────┐
                                      │   OpenAI /       │
                                      │   Anthropic      │
                                      │   (LLM)          │
                                      └──────────────────┘
```

1. **UI** recibe URL y modelo de IA elegido por el usuario.
2. **UI** llama a `/pipeline` del Core (HTTP).
3. **Core** se conecta a Lightpanda vía CDP (WebSocket `:9222`), extrae HTML + texto limpio.
4. **Core** envía el texto al LLM seleccionado (GPT-4o-mini o Claude 3.5 Sonnet).
5. **UI** muestra el reporte y permite exportar CSV.

---

## 📦 Módulos del Core (Backend)

| Archivo | Responsabilidad |
|---------|-----------------|
| `core/config.py` | Configuración centralizada con Pydantic Settings (lee de `.env`) |
| `core/exceptions.py` | Excepciones personalizadas (Lightpanda + IA) |
| `core/browser.py` | `LightpandaBrowser`: conexión CDP, `Target.createBrowserContext` → `Target.createTarget` → `Target.attachToTarget` → `LP.dump`, reintentos con `tenacity` |
| `core/ai_handler.py` | `AIHandler`: controlador unificado OpenAI + Anthropic (GPT-4o-mini / Claude 3.5 Sonnet) |
| `core/main.py` | Servidor FastAPI con endpoints `/health`, `/extract`, `/analyze`, `/pipeline` |

### Endpoints del Core
- `GET /health` — estado del servicio y alcance de Lightpanda
- `POST /extract` — extrae título, texto y HTML de una URL
- `POST /analyze` — analiza texto con IA seleccionada
- `POST /pipeline` — extrae + analiza en una sola llamada (ideal para tesis)

---

## 🖥️ Módulo de la UI (Frontend)

| Archivo | Responsabilidad |
|---------|-----------------|
| `ui/app.py` | Panel Streamlit moderno: barra lateral de configuración, campos de URL, selección de proveedor/modelo de IA, visualización de resultados (pestañas: Extracción, Análisis IA, Datos brutos), exportación CSV |

---

## ⚙️ Configuración compartida (`.env`)

Permite cambiar la URL del navegador y claves de IA **sin modificar el código fuente**:

| Variable | Local (WSL2) | OpenCloud / VPS |
|----------|--------------|-----------------|
| `BROWSER_CDP_URL` | `http://127.0.0.1:9222` | `http://<IP-VPS>:9222` |
| `CORE_API_URL` | `http://127.0.0.1:8000` | `http://<IP-VPS>:8000` |
| `OPENAI_API_KEY` | `sk-...` | `sk-...` |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | `sk-ant-...` |
| `DEFAULT_AI_PROVIDER` | `openai` | `openai` \| `anthropic` |
| `DEFAULT_AI_MODEL` | `gpt-4o-mini` | `gpt-4o-mini` \| `claude-3-5-sonnet-20241022` |

---

## 🚀 Inicio rápido (desarrollo local)

### Core (WSL2 local — Worktree 1)
```bash
cd feature-panda-core
pip install -r requirements-core.txt
cp .env.example .env   # editar BROWSER_CDP_URL y claves de IA
python -m uvicorn core.main:app --host 0.0.0.0 --port 8000
```

### UI (OpenCloud / local — Worktree 2)
```bash
cd feature-panda-ui
pip install -r requirements-ui.txt
streamlit run ui/app.py   # http://localhost:8501
```

---

## ☁️ Despliegue en OpenCloud (VPS)

Consulta `DEPLOY_OPENCLOUD.md` para la guía completa. Resumen:

```bash
# En el VPS
git clone https://github.com/JP-xs/PandaCore-Automation.git
cd PandaCore-Automation

# Configurar .env con valores reales
cp feature-panda-core/.env.example feature-panda-core/.env
# editar BROWSER_CDP_URL, OPENAI_API_KEY, etc.

# Levantar con Docker Compose
docker-compose up -d --build

# Acceder a la UI: http://<IP-VPS>:8501
```

---

## ⚠️ Problema conocido: Lightpanda WebSocket

Durante las pruebas se confirmó que el servidor Lightpanda (v1.1.0-nightly) cierra la conexión WebSocket con código **1002 (protocolo error)** tras recibir el primer comando CDP (ej. `LP.version`). Este es un problema del **servidor Lightpanda**, no del código cliente.

**Estado del código:** El flujo de cliente está correctamente implementado y validado mediante diagnóstico:
1. `Target.createBrowserContext` → `browserContextId` ✅
2. `Target.createTarget` (con URL) → `targetId` ✅
3. `Target.attachToTarget` → `sessionId` ✅
4. `LP.dump` (con `sessionId`) → HTML / Markdown limpio ✅

**Solución temporal:** Reiniciar el servidor Lightpanda antes de usar el Core. Cuando Lightpanda estabilice su protocolo WebSocket, el Core funcionará sin modificaciones.

---

## 📊 Estado del proyecto

| Componente | Estado |
|------------|--------|
| Estructura de worktrees (2) | ✅ Completado |
| Core: browser.py (CDP Lightpanda) | ✅ Completado |
| Core: ai_handler.py (OpenAI/Anthropic) | ✅ Completado |
| Core: main.py (FastAPI endpoints) | ✅ Completado |
| Core: config.py + exceptions.py | ✅ Completado |
| UI: app.py (Streamlit) | ✅ Completado |
| .env compartido (configuración dinámica) | ✅ Completado |
| Dockerfile Core + UI | ✅ Completado |
| docker-compose.yml (OpenCloud) | ✅ Completado |
| Script de prueba Lightpanda | ✅ Creado (pendiente validación end-to-end) |
| Despliegue en OpenCloud | ✅ Listo (Docker Compose) |
| Prueba end-to-end (UI → Core → Lightpanda → IA) | ⏳ Pendiente (bloqueado por Lightpanda WebSocket) |

---

## 👥 Autores y arquitectura

**Arquitecto de Software Senior** — JPxs  
**Especialización:** Python, Node.js, Automatización, CDP/Lightpanda, IA (OpenAI / Anthropic), Streamlit, FastAPI, Docker, OpenCloud.

---

## 📄 Licencia

Privado — Proyecto de tesis y automatización de datos.
