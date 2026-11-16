"""
core/ai_handler.py
==================

Controlador modular de Inteligencia Artificial para el proyecto JPxs-LightPanda-AI.

Utiliza exclusivamente OpenCode como proveedor de IA (modelos gratuitos). El
controlador es agnostico a la interfaz y solo expone la funcion `analyze(...)`
que el Motor Core (FastAPI) y cualquier otro consumidor pueden reutilizar.

OpenCode expone una API compatible con OpenAI:
    POST {OPENCODE_BASE_URL}/chat/completions
    Authorization: Bearer {OPENCODE_API_KEY}
    Body: {model, messages, temperature, max_tokens, stream}
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import settings
from core.exceptions import (
    AIConfigurationError,
    AIError,
    AIProviderError,
    AIRequestError,
)

logger = logging.getLogger(__name__)

# Excepciones de red/HTTP que deben disparar reintento automatico.
_RETRYABLE_AI_EXCEPTIONS = (httpx.HTTPError, httpx.RequestError, AIRequestError)

# Modelos gratuitos disponibles en OpenCode (según el listado del usuario).
OPENCODE_MODELS: List[str] = [
    "nemotron-3.5-super-vl-2024-10-22",
    "beam-free",
    "deepseek-v4.1-flash-free",
    "nemotron-3.5-lightning-free",
    "glm-5.3-flash-free",
    "mimo-v2.6-flash-free",
    "crouton-alpha-free",
    "pulse-alpha-free",
    "flint-40b-free",
    "big-pickle",
]

# Alias amigables -> IDs de modelo (opcional, para que la UI pueda usar nombres legibles).
MODEL_ALIASES: Dict[str, str] = {
    "nemotron-3.5-super-vl": "nemotron-3.5-super-vl-2024-10-22",
    "beam": "beam-free",
    "deepseek-v4.1-flash": "deepseek-v4.1-flash-free",
    "nemotron-3.5-lightning": "nemotron-3.5-lightning-free",
    "glm-5.3-flash": "glm-5.3-flash-free",
    "mimo-v2.6-flash": "mimo-v2.6-flash-free",
    "crouton-alpha": "crouton-alpha-free",
    "pulse-alpha": "pulse-alpha-free",
    "flint-40b": "flint-40b-free",
    "big-pickle": "big-pickle",
}


class AIHandler:
    """Controlador de IA que abstrae la llamada a OpenCode."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------ #
    # Cliente HTTP perezoso (se crea solo cuando se necesita)
    # ------------------------------------------------------------------ #
    def _client(self) -> httpx.AsyncClient:
        if not settings.OPENCODE_API_KEY:
            raise AIConfigurationError(
                "OPENCODE_API_KEY no esta configurada en el entorno. "
                "Copia .env.example a .env y agrega tu clave de OpenCode."
            )
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=settings.OPENCODE_BASE_URL,
                timeout=settings.NAVIGATION_TIMEOUT,
                headers={
                    "Authorization": f"Bearer {settings.OPENCODE_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        """Cierra el cliente HTTP (llamar al apagar el servidor)."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------ #
    # API publica
    # ------------------------------------------------------------------ #
    async def analyze(
        self,
        text: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """Envia texto al LLM de OpenCode y devuelve el contenido generado.

        Devuelve un diccionario con: provider, model, content y (opcional) usage.
        """
        if not text or not text.strip():
            raise AIError("El texto a analizar no puede estar vacio.")

        provider = (provider or settings.DEFAULT_AI_PROVIDER).lower()
        if provider != "open_code":
            raise AIProviderError(
                f"Proveedor de IA no soportado: '{provider}'. "
                "Este motor usa exclusivamente 'open_code'."
            )

        model = model or settings.DEFAULT_AI_MODEL
        # Resolver alias si se paso un nombre corto.
        model = MODEL_ALIASES.get(model, model)
        if model not in OPENCODE_MODELS:
            logger.warning(
                "Modelo '%s' no esta en la lista de modelos gratuitos de OpenCode. "
                "Se enviara de todos modos.",
                model,
            )

        return await self._analyze_open_code(
            text=text,
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @property
    def available_providers(self) -> List[str]:
        """Devuelve los proveedores de IA que tienen API key configurada."""
        if settings.OPENCODE_API_KEY:
            return ["open_code"]
        return []

    @property
    def available_models(self) -> List[str]:
        """Devuelve la lista de modelos gratuitos de OpenCode."""
        return list(OPENCODE_MODELS)

    # ------------------------------------------------------------------ #
    # Implementacion OpenCode
    # ------------------------------------------------------------------ #
    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_BACKOFF, min=1, max=60),
        retry=retry_if_exception_type(_RETRYABLE_AI_EXCEPTIONS),
    )
    async def _analyze_open_code(
        self,
        text: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        client = self._client()

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": text})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text if exc.response is not None else str(exc)
            raise AIRequestError(
                f"OpenCode API devolvio error {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.RequestError as exc:
            raise AIRequestError(f"Error de red al contactar OpenCode: {exc}") from exc

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise AIRequestError("OpenCode no devolvio 'choices' en la respuesta.")

        message = choices[0].get("message", {}) or {}
        content = message.get("content", "") or ""

        usage = data.get("usage")
        return {
            "provider": "open_code",
            "model": model,
            "content": content,
            "usage": usage,
        }
