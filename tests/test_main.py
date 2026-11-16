"""
tests/test_main.py
==================

Pruebas unitarias de los endpoints FastAPI del Motor Core.

Uso:
    pip install pytest pytest-asyncio httpx
    pytest tests/test_main.py -v
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.main import app

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Fixtures y mocks
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_browser() -> MagicMock:
    """Mock de LightpandaBrowser que devuelve un ExtractionResult simulado."""
    mock = MagicMock()
    mock.navigate_and_extract = AsyncMock(
        return_value=MagicMock(
            url="https://example.com",
            title="Ejemplo",
            html="<html><body>Hola mundo</body></html>",
            text="Hola mundo",
            status_code=200,
        )
    )
    return mock


@pytest.fixture
def mock_ai_handler() -> MagicMock:
    """Mock de AIHandler que devuelve un resultado de IA simulado."""

    async def _analyze(
        text: str,
        provider: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        return {
            "provider": provider or "openai",
            "model": model or "gpt-4o-mini",
            "content": "Analisis simulado del texto extraído.",
            "usage": None,
        }

    mock = MagicMock()
    mock.analyze = _analyze
    return mock


# --------------------------------------------------------------------------- #
# Pruebas de /health
# --------------------------------------------------------------------------- #


def test_health_returns_ok_structure() -> None:
    """GET /health debe devolver un JSON con al menos la clave 'status'."""
    with patch("core.main.AIHandler") as mock_ai:
        mock_instance = MagicMock()
        mock_instance.available_providers = ["openai"]
        mock_ai.return_value = mock_instance

        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] in ("ok", "degraded")


# --------------------------------------------------------------------------- #
# Pruebas de /extract
# --------------------------------------------------------------------------- #


def test_extract_success(mock_browser: MagicMock) -> None:
    """POST /extract devuelve los datos extraídos cuando todo sale bien."""
    with patch("core.main.AppState") as mock_state_class:
        mock_state = MagicMock()
        mock_state.browser = mock_browser
        mock_state_class.return_value = mock_state

        # Sobrescribimos app.state para usar nuestro mock
        app.state = mock_state  # type: ignore[attr-defined]

        try:
            response = client.post(
                "/extract", json={"url": "https://example.com"}
            )
        finally:
            app.state = None  # type: ignore[assignment]

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com"
    assert data["title"] == "Ejemplo"
    assert data["text"] == "Hola mundo"
    assert data["status_code"] == 200


def test_extract_lightpanda_down() -> None:
    """POST /extract devuelve 503 cuando Lightpanda no está disponible."""
    from core.exceptions import LightpandaConnectionError

    mock_browser = MagicMock()
    mock_browser.navigate_and_extract = AsyncMock(
        side_effect=LightpandaConnectionError(
            "No se pudo contactar con Lightpanda"
        )
    )

    with patch("core.main.AppState") as mock_state_class:
        mock_state = MagicMock()
        mock_state.browser = mock_browser
        mock_state_class.return_value = mock_state

        app.state = mock_state  # type: ignore[attr-defined]
        try:
            response = client.post("/extract", json={"url": "https://example.com"})
        finally:
            app.state = None  # type: ignore[assignment]

    assert response.status_code == 503
    data = response.json()
    assert "Lightpanda" in data["detail"]


# --------------------------------------------------------------------------- #
# Pruebas de /pipeline
# --------------------------------------------------------------------------- #


def test_pipeline_success(mock_browser: MagicMock, mock_ai_handler: MagicMock) -> None:
    """POST /pipeline ejecuta extraccion + analisis con exito."""
    mock_state = MagicMock()
    mock_state.browser = mock_browser

    with patch("core.main.AppState", return_value=mock_state), patch(
        "core.main.AIHandler", return_value=mock_ai_handler
    ):
        app.state = mock_state  # type: ignore[attr-defined]
        try:
            response = client.post(
                "/pipeline",
                json={
                    "url": "https://example.com",
                    "prompt": "Analiza esta pagina para mi tesis",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
        finally:
            app.state = None  # type: ignore[assignment]

    assert response.status_code == 200
    data = response.json()
    assert "extraction" in data
    assert "analysis" in data
    assert data["extraction"]["url"] == "https://example.com"
    assert data["analysis"]["provider"] == "openai"
    assert data["analysis"]["content"] == "Analisis simulado del texto extraído."


def test_pipeline_lightpanda_down() -> None:
    """POST /pipeline devuelve 503 cuando Lightpanda no está disponible."""
    from core.exceptions import LightpandaConnectionError

    mock_browser = MagicMock()
    mock_browser.navigate_and_extract = AsyncMock(
        side_effect=LightpandaConnectionError("Lightpanda no disponible")
    )
    mock_state = MagicMock()
    mock_state.browser = mock_browser

    with patch("core.main.AppState", return_value=mock_state):
        app.state = mock_state  # type: ignore[attr-defined]
        try:
            response = client.post(
                "/pipeline",
                json={
                    "url": "https://example.com",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
        finally:
            app.state = None  # type: ignore[assignment]

    assert response.status_code == 503


def test_pipeline_invalid_provider() -> None:
    """POST /pipeline con proveedor no soportado devuelve 422."""
    mock_browser = MagicMock()
    mock_browser.navigate_and_extract = AsyncMock(
        return_value=MagicMock(
            url="https://example.com",
            title="Ejemplo",
            html="<html></html>",
            text="texto",
            status_code=200,
        )
    )
    mock_state = MagicMock()
    mock_state.browser = mock_browser

    with patch("core.main.AppState", return_value=mock_state):
        app.state = mock_state  # type: ignore[attr-defined]
        try:
            response = client.post(
                "/pipeline",
                json={
                    "url": "https://example.com",
                    "provider": "proveedor_inexistente",
                    "model": "modelo",
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
            )
        finally:
            app.state = None  # type: ignore[assignment]

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Pruebas de /analyze
# --------------------------------------------------------------------------- #


def test_analyze_success(mock_ai_handler: MagicMock) -> None:
    """POST /analyze devuelve el resultado de IA simulado."""
    with patch("core.main.AIHandler", return_value=mock_ai_handler):
        response = client.post(
            "/analyze",
            json={
                "text": "Texto de prueba",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "temperature": 0.5,
                "max_tokens": 1000,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "anthropic"
    assert data["content"] == "Analisis simulado del texto extraído."


def test_analyze_empty_text() -> None:
    """POST /analyze con texto vacio devuelve 422."""
    response = client.post(
        "/analyze",
        json={
            "text": "",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "max_tokens": 2000,
        },
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Validacion de esquemas de request
# --------------------------------------------------------------------------- #


def test_pipeline_request_validation() -> None:
    """POST /pipeline con campos faltantes devuelve 422 de validacion."""
    response = client.post(
        "/pipeline",
        json={
            # Falta 'url' requerido
            "provider": "openai",
        },
    )
    assert response.status_code == 422


def test_temperature_out_of_range() -> None:
    """temperature fuera de [0.0, 1.0] devuelve 422."""
    mock_browser = MagicMock()
    mock_browser.navigate_and_extract = AsyncMock(
        return_value=MagicMock(
            url="https://example.com",
            title="Ejemplo",
            html="<html></html>",
            text="texto",
            status_code=200,
        )
    )
    mock_state = MagicMock()
    mock_state.browser = mock_browser

    with patch("core.main.AppState", return_value=mock_state):
        app.state = mock_state  # type: ignore[attr-defined]
        try:
            response = client.post(
                "/pipeline",
                json={
                    "url": "https://example.com",
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "temperature": 1.5,  # fuera de rango
                    "max_tokens": 2000,
                },
            )
        finally:
            app.state = None  # type: ignore[assignment]

    assert response.status_code == 422
