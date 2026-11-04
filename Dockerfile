# =============================================================================
# Dockerfile - JPxs-LightPanda-AI Core (Backend/Motor)
# Worktree 1: feature/panda-core  ->  OpenCode / Local WSL2 / OpenCloud
# =============================================================================
FROM python:3.12-slim

# Evitar que Python genere archivos .pyc y que bufferize stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema (necesarias para algunos paquetes Python)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias de Python
COPY requirements-core.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-core.txt

# Copiar el código de la aplicación
COPY core/ ./core/
COPY .env .env
COPY .env.example .env.example

# Puerto expuesto por FastAPI/Uvicorn
EXPOSE 8000

# Comando por defecto: iniciar el servidor Core
# La URL de Lightpanda se lee desde .env (BROWSER_CDP_URL)
CMD ["python", "-m", "uvicorn", "core.main:app", "--host", "0.0.0.0", "--port", "8000"]
