# feature/panda-ui - Interfaz Streamlit de JPxs-LightPanda-AI

## Descripción
Panel visual para gestionar URLs, elegir modelos de IA y visualizar reportes y tablas
generadas por el Motor Core (feature/panda-core).

## Cómo ejecutar

```bash
# 1. Entrar al worktree de UI
cd feature-panda-ui

# 2. Instalar dependencias
pip install -r requirements-ui.txt

# 3. Copiar y configurar .env
# El .env se comparte conceptualmente con el Core.
cp ../feature-panda-core/.env.example .env   # o crear uno propio
# Editar CORE_API_URL según dónde esté el Motor Core

# 4. Ejecutar Streamlit
streamlit run ui/app.py
```

## Comunicación con el Core
Esta UI NO importa el Core. Llama por HTTP a los endpoints expuestos por
`core/main.py` (FastAPI):
- POST /pipeline   -> extrae + analiza
- POST /extract    -> solo extrae
- POST /analyze    -> solo analiza con IA
- GET  /health     -> estado del servicio

La URL del Core se lee de la variable `CORE_API_URL` en `.env`, lo que permite
desplegar la UI en OpenCloud y el Core en WSL2 (u otro VPS) sin tocar el código.

## Variables de entorno relevantes (.env)
- CORE_API_URL=http://127.0.0.1:8000
- UI_PORT=8501
