"""
core/main.py
============

Motor Core de JPxs-LightPanda-AI (FastAPI).

Expone una API HTTP desacoplada que la UI (Streamlit, Worktree 2) consume para:
  - Verificar el estado del servicio:          GET  /health
  - Extraer HTML/texto de una URL:             POST /extract
  - Analizar texto con IA:                     POST /analyze
  - Pipeline completo (extraer + analizar):    POST /pipeline

El Core NO sabe nada de botones ni pantallas visuales. Solo habla con Lightpanda
(CDP) y con las APIs de IA (OpenAI / Anthropic).

Endpoints esperados por la UI (ui/app.py de feature/panda-ui):
  - POST /pipeline  -> {url, provider, model, system_prompt, temperature, max_tokens}
                       -> {extraction: {title, text, status_code}, analysis: {provider, model, content}}
  - POST /extract   -> {url}                      -> {url, title, text, html, status_code}
  - POST /analyze   -> {text, provider, model, system_prompt, temperature, max_tokens}
                      -> {provider, model, content}
  - GET  /health    -> {status, lightpanda_reachable, ...}
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from core.ai_handler import AIHandler
from core.browser import ExtractionResult, LightpandaBrowser
from core.config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Modelos de solicitud / respuesta
# --------------------------------------------------------------------------- #
class ExtractRequest(BaseModel):
    url: str = Field(..., description="URL de la pagina a extraer")


class AnalyzeRequest(BaseModel):
    text: str = Field(..., description="Texto a analizar con IA")
    provider: Optional[str] = Field(None, description="openai | anthropic")
    model: Optional[str] = Field(None, description="Modelo concreto del proveedor")
    system_prompt: Optional[str] = Field(None, description="Prompt de sistema opcional")
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_tokens: int = Field(2000, ge=256, le=8192)


class PipelineRequest(AnalyzeRequest):
    url: str = Field(..., description="URL de la pagina a extraer y analizar")


# --------------------------------------------------------------------------- #
# Estado de la aplicacion (cargado en el lifespan)
# --------------------------------------------------------------------------- #
class AppState:
    browser: LightpandaBrowser
    ai: AIHandler


@asynccontextmanager
async def lifespan(app: FastAPI):
    state = AppState()
    state.browser = LightpandaBrowser()
    state.ai = AIHandler()
    # Conexion perezosa: el servidor arranca aunque Lightpanda este temporalmente
    # inaccesible. La primera peticion a /extract o /pipeline se encargara de
    # conectar (con reintentos) y /health reportara el estado real.
    logger.info(
        "Motor Core listo. Lightpanda configurada en: %s (conexion bajo demanda)",
        settings.LIGHTPANDA_URL,
    )
    yield
    await state.browser.stop()
    logger.info("Motor Core detenido.")


app = FastAPI(
    title="JPxs-LightPanda-AI - Motor Core",
    version="1.0.0",
    description=(
        "Extraccion web con Lightpanda (CDP) + analisis con IA "
        "(OpenAI / Anthropic). Arquitectura desacoplada para tesis y datos."
    ),
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["Estado"])
async def health() -> Dict[str, Any]:
    """Estado del servicio y de la conexion con Lightpanda."""
    lightpanda_ok = False
    try:
        async with httpx.AsyncClient(timeout=settings.CDP_CONNECT_TIMEOUT) as client:
            resp = await client.get(f"{settings.LIGHTPANDA_URL}/json/version")
            lightpanda_ok = resp.is_success
    except Exception as exc:  # noqa: BLE001
        logger.warning("Health check de Lightpanda fallo: %s", exc)

    return {
        "status": "ok" if lightpanda_ok else "degraded",
        "lightpanda_url": settings.LIGHTPANDA_URL,
        "lightpanda_reachable": lightpanda_ok,
        "ai_providers": AIHandler().available_providers,
    }


@app.post("/extract", tags=["Extraccion"])
async def extract(request: ExtractRequest, fastapi_request: Request) -> Dict[str, Any]:
    """Extrae titulo, texto plano y HTML de una URL (sin IA)."""
    state: AppState = fastapi_request.app.state
    result: ExtractionResult = await state.browser.navigate_and_extract(request.url)
    return {
        "url": result.url,
        "title": result.title,
        "text": result.text,
        "html": result.html,
        "status_code": result.status_code,
    }


@app.post("/analyze", tags=["IA"])
async def analyze(request: AnalyzeRequest) -> Dict[str, Any]:
    """Analiza un texto con el proveedor y modelo de IA indicados."""
    ai = AIHandler()
    try:
        outcome = await ai.analyze(
            text=request.text,
            provider=request.provider,
            model=request.model,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except AIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Error inesperado en /analyze: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return outcome


@app.post("/pipeline", tags=["Pipeline"])
async def pipeline(request: PipelineRequest, fastapi_request: Request) -> Dict[str, Any]:
    """Pipeline completo: extrae el contenido de la URL y lo analiza con IA."""
    state: AppState = fastapi_request.app.state

    # 1. Extraccion con Lightpanda
    result: ExtractionResult = await state.browser.navigate_and_extract(request.url)

    # 2. Analisis con IA sobre el texto extraido
    ai = AIHandler()
    try:
        outcome = await ai.analyze(
            text=result.text,
            provider=request.provider,
            model=request.model,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except AIError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Error inesperado en /pipeline: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "extraction": {
            "url": result.url,
            "title": result.title,
            "text": result.text,
            "html": result.html,
            "status_code": result.status_code,
        },
        "analysis": outcome,
    }
