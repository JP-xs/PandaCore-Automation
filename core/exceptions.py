"""
core/exceptions.py
==================

Excepciones personalizadas del Motor Core (feature/panda-core).

Cada excepción está diseñada para ser capturada en los endpoints de FastAPI
y traducirse a respuestas HTTP apropiadas.
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# Excepciones de Lightpanda (navegador headless)
# --------------------------------------------------------------------------- #

class LightpandaError(Exception):
    """Excepción base para errores relacionados con Lightpanda."""


class LightpandaConnectionError(LightpandaError):
    """No se pudo conectar con Lightpanda (CDP) o el servidor está inaccesible."""


class LightpandaNavigationError(LightpandaError):
    """Error al navegar a una URL o crear un target en Lightpanda."""


class LightpandaExtractionError(LightpandaError):
    """Error al extraer contenido (HTML/texto) de una página mediante LP.dump."""


# --------------------------------------------------------------------------- #
# Excepciones de IA (OpenAI / Anthropic)
# --------------------------------------------------------------------------- #

class AIError(Exception):
    """Excepción base para errores de proveedores de IA."""


class AIProviderError(AIError):
    """Error relacionado con un proveedor de IA específico."""


class AIConfigurationError(AIProviderError):
    """Falta configuración (API key, modelo) para el proveedor de IA seleccionado."""


class AIRequestError(AIProviderError):
    """Error al realizar una petición al proveedor de IA (timeout, respuesta inválida, etc.)."""
