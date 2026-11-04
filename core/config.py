"""
core/config.py
==============

Configuración centralizada del Motor Core (feature/panda-core).

Todas las variables se leen del entorno o del archivo .env. Esto permite cambiar
la URL del navegador (localhost vs IP de VPS en OpenCloud), los puertos y las
claves de IA SIN modificar el código fuente.

Uso:
    from core.config import settings
    print(settings.LIGHTPANDA_URL)
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuración del Core. Los valores por defecto están orientados a
    desarrollo local en WSL2. Para OpenCloud, edita .env o las variables
    de entorno antes de arrancar el servicio.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Lightpanda (navegador headless - CDP)
    # ------------------------------------------------------------------ #
    LIGHTPANDA_URL: str = Field(
        default="http://127.0.0.1:9222",
        description="Endpoint HTTP de Lightpanda. Local: http://127.0.0.1:9222 | OpenCloud: http://<IP-VPS>:9222",
    )

    # ------------------------------------------------------------------ #
    # Core API (FastAPI)
    # ------------------------------------------------------------------ #
    CORE_API_URL: str = Field(default="http://127.0.0.1:8000")
    CORE_PORT: int = Field(default=8000)
    CORE_RELOAD: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO")

    # ------------------------------------------------------------------ #
    # Tiempos de espera y reintentos
    # ------------------------------------------------------------------ #
    CDP_CONNECT_TIMEOUT: float = Field(default=15.0)
    NAVIGATION_TIMEOUT: float = Field(default=30.0)
    NAVIGATION_WAIT: float = Field(default=4.0)
    MAX_RETRIES: int = Field(default=3)
    RETRY_BACKOFF: float = Field(default=2.0)

    # ------------------------------------------------------------------ #
    # Claves de proveedores de IA
    # ------------------------------------------------------------------ #
    OPENAI_API_KEY: str = Field(default="")
    ANTHROPIC_API_KEY: str = Field(default="")

    # ------------------------------------------------------------------ #
    # Modelo de IA por defecto
    # ------------------------------------------------------------------ #
    DEFAULT_AI_PROVIDER: str = Field(default="openai")
    DEFAULT_AI_MODEL: str = Field(default="gpt-4o-mini")


# Instancia singleton de configuración
settings = Settings()
