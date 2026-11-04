# feature/panda-core - Motor Core de JPxs-LightPanda-AI

## Descripcion

Este worktree contiene el **Motor Core** del sistema de extraccion de datos orientado
a tesis y software. Es el motor backend que:

1. Se conecta al navegador headless **Lightpanda** (ejecutandose en WSL2 o OpenCloud)
   mediante **Chrome DevTools Protocol (CDP)** en `LIGHTPANDA_URL` (por defecto
   `http://127.0.0.1:9222`).
2. Extrae el **texto plano y el HTML estructurado** de cualquier URL.
3. Envía ese contenido a **Modelos de Lenguaje (OpenAI / Anthropic)** para su analisis.

El Core es **agnostico a la interfaz**: no conoce botones ni pantallas visuales. La UI
(Worktree 2, `feature/panda-ui`, Streamlit) se comunica con este motor exclusivamente
por **HTTP** a traves de la API FastAPI expuesta en `core/main.py`.

## Estructura

```
feature-panda-core/
├── .env.example              # Plantilla de variables de entorno
├── .gitignore
├── README.md
├── requirements-core.txt     # Dependencias de Python
└── core/
    ├── __init__.py
    ├── config.py             # Carga tipada de .env (pydantic-settings)
    ├── exceptions.py         # Excepciones personalizadas
    ├── browser.py            # Conexion CDP, navegacion y extraccion (con reintentos)
    ├── ai_handler.py         # Controlador IA (OpenAI GPT-4o-mini / Claude 3.5 Sonnet)
    └── main.py               # Servidor FastAPI (/health, /extract, /analyze, /pipeline)
```

## Variables de entorno (.env)

Copie `.env.example` a `.env` y ajuste segun el entorno:

| Variable | Valor por defecto | Descripcion |
|----------|-------------------|-------------|
| `LIGHTPANDA_URL` | `http://127.0.0.1:9222` | URL de Lightpanda (CDP). Local WSL2 o OpenCloud. |
| `OPENAI_API_KEY` | (vacío) | Clave de API de OpenAI. |
| `ANTHROPIC_API_KEY` | (vacío) | Clave de API de Anthropic. |
| `CORE_API_HOST` | `0.0.0.0` | Host del servidor FastAPI. |
| `CORE_API_PORT` | `8000` | Puerto del servidor FastAPI. |
| `DEFAULT_AI_PROVIDER` | `openai` | `openai` o `anthropic`. |
| `DEFAULT_AI_MODEL` | `gpt-4o-mini` | Modelo por defecto. |
| `MAX_RETRIES` | `3` | Reintentos ante fallos de red/servidor. |
| `LOG_LEVEL` | `INFO` | Nivel de logging. |

## Como ejecutar el Motor Core

```bash
# 1. Entrar al worktree del Core
cd feature-panda-core

# 2. Instalar dependencias
pip install -r requirements-core.txt

# 3. Copiar y configurar .env
cp .env.example .env
# Editar .env con LIGHTPANDA_URL y las claves de IA

# 4. Ejecutar el servidor (puerto 8000 por defecto)
uvicorn core.main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints de la API

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| `GET` | `/health` | Estado del servicio y alcance de Lightpanda. |
| `POST` | `/extract` | Extrae titulo/texto/HTML de una URL (sin IA). |
| `POST` | `/analyze` | Analiza texto con IA (sin extraccion). |
| `POST` | `/pipeline` | Extraccion + analisis IA en un solo llamado. |

Ejemplo `/pipeline`:

```json
{
  "url": "https://ejemplo.com/tesis",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "system_prompt": "Eres un asistente experto en analisis de tesis academicas.",
  "temperature": 0.3,
  "max_tokens": 2000
}
```

## Conexion con Worktree 2 (feature/panda-ui)

La UI de Streamlit **no importa** este codigo. Llama por HTTP a los endpoints del Core
usando la variable `CORE_API_URL` de su propio `.env` (ej. `http://127.0.0.1:8000`).
Esto permite desplegar la UI en OpenCloud y el Core en WSL2 (o viceversa) sin tocar el
codigo, solo cambiando el `.env`.

Endpoints consumidos por la UI:
- `POST /pipeline`  -> extrae + analiza
- `POST /extract`   -> solo extrae
- `POST /analyze`   -> solo analiza con IA
- `GET  /health`    -> estado del servicio

## Manejo de errores y reintentos

- **Conexion CDP / navegación / extracción**: reintentos con backoff exponencial
  (`tenencia`) ante `LightpandaConnectionError`, `LightpandaNavigationError`,
  `ConnectionError`, `OSError` y `TimeoutError`.
- **Llamadas a IA**: reintentos con backoff exponencial ante fallos transitorios de
  OpenAI / Anthropic.
- Si se agotan los reintentos, la excepcion se propaga y la API devuelve
  `HTTP 500` (o `422` para errores de validacion/IA).

## Proveedores de IA soportados

- **openai**: `gpt-4o-mini` (economico, ideal para scraping masivo de software).
- **anthropic**: `claude-3-5-sonnet-20241022` (avanzado, ideal para analisis juridico
  profundo de tesis).

Seleccionar el proveedor y modelo por peticion o usar los valores por defecto de `.env`.
