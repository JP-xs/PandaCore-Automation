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
(CDP) y con la API de OpenCode (único proveedor de IA, modelos gratuitos).

Endpoints esperados por la UI (ui/app.py de feature/panda-ui):
  - POST /pipeline  -> {url, prompt, provider, model, temperature, max_tokens}
                       -> {extraction: {title, text, status_code}, analysis: {provider, model, content}}
  - POST /extract   -> {url}                      -> {url, title, text, html, status_code}
  - POST /analyze   -> {text, provider, model, system_prompt, temperature, max_tokens}
                       -> {provider, model, content}
  - GET  /health    -> {status: "ok"}
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from core.ai_handler import AIError, AIHandler
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
    provider: Optional[str] = Field(None, description="open_code")
    model: Optional[str] = Field(None, description="Modelo concreto de OpenCode")
    system_prompt: Optional[str] = Field(None, description="Prompt de sistema opcional")
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_tokens: int = Field(2000, ge=256, le=8192)


class PipelineRequest(BaseModel):
    url: str = Field(..., description="URL de la pagina a extraer y analizar")
    prompt: Optional[str] = Field(
        None, description="Prompt de investigacion para el analisis con IA"
    )
    provider: Optional[str] = Field(None, description="open_code")
    model: Optional[str] = Field(None, description="Modelo concreto de OpenCode")
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_tokens: int = Field(2000, ge=256, le=8192)


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
    app.state = state
    logger.info(
        "Motor Core listo. Lightpanda configurada en: %s (conexion bajo demanda)",
        settings.LIGHTPANDA_URL,
    )
    yield
    await state.browser.stop()
    await state.ai.close()
    logger.info("Motor Core detenido.")


app = FastAPI(
    title="JPxs-LightPanda-AI - Motor Core",
    version="1.0.0",
    description=(
        "Extraccion web con Lightpanda (CDP) + analisis con IA "
        "(OpenCode - modelos gratuitos). Arquitectura desacoplada para tesis y datos."
    ),
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["Estado"])
async def health() -> Dict[str, Any]:
    """Estado del servicio del motor Core."""
    return {"status": "ok"}


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
    """Analiza un texto con OpenCode."""
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
        await ai.close()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        await ai.close()
        logger.error("Error inesperado en /analyze: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    await ai.close()
    return outcome


@app.post("/pipeline", tags=["Pipeline"])
async def pipeline(request: PipelineRequest, fastapi_request: Request) -> Dict[str, Any]:
    """Pipeline completo: extrae el contenido de la URL y lo analiza con IA."""
    state: AppState = fastapi_request.app.state

    # 1. Extraccion con Lightpanda
    result: ExtractionResult = await state.browser.navigate_and_extract(request.url)

    # 2. Analisis con IA sobre el texto extraido
    ai: AIHandler = state.ai
    try:
        outcome = await ai.analyze(
            text=result.text,
            provider=request.provider,
            model=request.model,
            system_prompt=request.prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
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
