"""
core/ai_handler.py
==================

Controlador modular de Inteligencia Artificial para el proyecto JPxs-LightPanda-AI.

Permite enviar el contenido HTML/texto extraído por Lightpanda a distintos
Modelos de Lenguaje (LLM):

  - Proveedor economico (scraping masivo de software): OpenAI GPT-4o-mini.
  - Proveedor avanzado (analisis juridico profundo de tesis): Anthropic Claude 3.5 Sonnet.

El controlador es agnostico a la interfaz y solo expone la funcion `analyze(...)`
que el Motor Core (FastAPI) y cualquier otro consumidor pueden reutilizar.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import settings
from core.exceptions import AIError, AIProviderError

logger = logging.getLogger(__name__)

# Excepciones de los proveedores de IA que deben disparar reintento automatico.
# (se capturan genericamente porque los SDKs lanzan distintos tipos de error;
#  tenencia reintenta y, si fallan todos los intentos, propaga la excepcion).
_RETRYABLE_AI_EXCEPTIONS = (Exception,)


class AIHandler:
    """Controlador de IA que abstrae la llamada a OpenAI y Anthropic."""

    # Modelos por defecto por proveedor.
    DEFAULT_MODELS = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-5-sonnet-20241022",
    }

    def __init__(self) -> None:
        self._openai_client: Any = None
        self._anthropic_client: Any = None

    # ------------------------------------------------------------------ #
    # Clientes perezosos (se instancian solo cuando se necesitan)
    # ------------------------------------------------------------------ #
    def _openai(self) -> Any:
        if not settings.OPENAI_API_KEY:
            raise AIProviderError(
                "OPENAI_API_KEY no esta configurada en el entorno."
            )
        if self._openai_client is None:
            from openai import AsyncOpenAI

            self._openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._openai_client

    def _anthropic(self) -> Any:
        if not settings.ANTHROPIC_API_KEY:
            raise AIProviderError(
                "ANTHROPIC_API_KEY no esta configurada en el entorno."
            )
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic

            self._anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        return self._anthropic_client

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
        """Envia texto a un LLM y devuelve el contenido generado.

        Devuelve un diccionario con: provider, model, content y (opcional) usage.
        """
        if not text or not text.strip():
            raise AIError("El texto a analizar no puede estar vacio.")

        provider = (provider or settings.DEFAULT_AI_PROVIDER).lower()
        model = model or self.DEFAULT_MODELS.get(provider)

        if provider == "openai":
            return await self._analyze_openai(
                text=text,
                model=model or "gpt-4o-mini",
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        if provider == "anthropic":
            return await self._analyze_anthropic(
                text=text,
                model=model or "claude-3-5-sonnet-20241022",
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        raise AIProviderError(
            f"Proveedor de IA no soportado: '{provider}'. Use 'openai' o 'anthropic'."
        )

    @property
    def available_providers(self) -> list[str]:
        """Devuelve los proveedores de IA que tienen API key configurada."""
        providers = []
        if settings.OPENAI_API_KEY:
            providers.append("openai")
        if settings.ANTHROPIC_API_KEY:
            providers.append("anthropic")
        return providers

    # ------------------------------------------------------------------ #
    # Implementacion por proveedor
    # ------------------------------------------------------------------ #
    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_BACKOFF, min=1, max=60),
        retry=retry_if_exception_type(_RETRYABLE_AI_EXCEPTIONS),
    )
    async def _analyze_openai(
        self,
        text: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        client = self._openai()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": text})

        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        usage = None
        if getattr(response, "usage", None) is not None:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        return {"provider": "openai", "model": model, "content": content, "usage": usage}

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_BACKOFF, min=1, max=60),
        retry=retry_if_exception_type(_RETRYABLE_AI_EXCEPTIONS),
    )
    async def _analyze_anthropic(
        self,
        text: str,
        model: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        client = self._anthropic()
        # Anthropic recibe el system prompt como parametro aparte.
        create_kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": text}],
        }
        if system_prompt:
            create_kwargs["system"] = system_prompt

        response = await client.messages.create(**create_kwargs)

        # response.content es una lista de bloques; tomamos los de tipo texto.
        content_parts = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                content_parts.append(block.text)
        content = "\n".join(content_parts)

        usage = None
        if getattr(response, "usage", None) is not None:
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
        return {"provider": "anthropic", "model": model, "content": content, "usage": usage}
