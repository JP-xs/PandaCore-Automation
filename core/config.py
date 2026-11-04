"""
core/config.py
==============

Carga tipada de variables de entorno para el Motor Core.

Lee el archivo `.env` (si existe) y las variables de entorno del sistema,
ofreciendo un objeto `settings` de uso global con valores por defecto seguros.

Instrucciones:
    1. Copie `.env.example` a `.env`.
    2. Ajuste los valores según el entorno (desarrollo local en WSL2 o
       producción en OpenCloud).
    3. Nunca suba el archivo `.env` con claves reales al repositorio.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ------------------------------------------------------------------ #
    # Lightpanda (Chrome DevTools Protocol)
    # ------------------------------------------------------------------ #
    LIGHTPANDA_URL: str = Field(
        "http://127.0.0.1:9222",
        description="URL del navegador headless Lightpanda (CDP). Local WSL2 o OpenCloud.",
    )

    # ------------------------------------------------------------------ #
    # Claves de API de IA
    # ------------------------------------------------------------------ #
    OPENAI_API_KEY: Optional[str] = Field(None, description="Clave de API de OpenAI")
    ANTHROPIC_API_KEY: Optional[str] = Field(None, description="Clave de API de Anthropic")

    # ------------------------------------------------------------------ #
    # Servidor del Motor Core (FastAPI)
    # ------------------------------------------------------------------ #
    CORE_API_HOST: str = Field("0.0.0.0", description="Host en el que escucha el Motor Core")
    CORE_API_PORT: int = Field(8000, description="Puerto en el que escucha el Motor Core")

    # ------------------------------------------------------------------ #
    # IA por defecto
    # ------------------------------------------------------------------ #
    DEFAULT_AI_PROVIDER: str = Field("openai", description="Proveedor por defecto: openai o anthropic")
    DEFAULT_AI_MODEL: str = Field(
        "gpt-4o-mini", description="Modelo de IA por defecto"
    )

    # ------------------------------------------------------------------ #
    # Tiempo de espera y reintentos
    # ------------------------------------------------------------------ #
    CDP_CONNECT_TIMEOUT: float = Field(10.0, description="Timeout de conexión CDP (segundos)")
    NAVIGATION_TIMEOUT: float = Field(30.0, description="Timeout de navegación (segundos)")
    NAVIGATION_WAIT: float = Field(
        4.0, description="Segundos de espera para que la página renderice JS tras crear el target"
    )
    MAX_RETRIES: int = Field(3, description="Numero maximo de reintentos")
    RETRY_BACKOFF: float = Field(2.0, description="Factor de backoff exponencial (segundos)")
    REQUEST_TIMEOUT: float = Field(60.0, description="Timeout general de peticion (segundos)")

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    LOG_LEVEL: str = Field("INFO", description="Nivel de logging")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Instancia singleton de configuracion.
settings = Settings()
