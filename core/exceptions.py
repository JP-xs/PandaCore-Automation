"""
core/exceptions.py
==================

Excepciones personalizadas del Motor Core.

Cada capa (navegador, IA, configuración) define sus propias excepciones para
permitir un manejo de errores preciso y reintentos selectivos solo en los casos
que realmente lo ameritan (fallos de red, servidor caído, timeouts).
"""

from __future__ import annotations


class LightpandaError(Exception):
    """Excepción base de errores relacionados con Lightpanda / CDP."""


class LightpandaConnectionError(LightpandaError):
    """No se pudo establecer o mantener la conexión con Lightpanda (servidor caído o red)."""


class LightpandaNavigationError(LightpandaError):
    """Error al navegar a una URL (p. ej. página no responde, timeout de carga)."""


class LightpandaExtractionError(LightpandaError):
    """Error al extraer el contenido (texto / HTML) de una página."""


class AIError(Exception):
    """Excepción base de errores de Inteligencia Artificial."""


class AIProviderError(AIError):
    """Error específico de un proveedor de IA (clave faltante, proveedor desconocido, cuota excedida, etc.)."""


class ConfigurationError(Exception):
    """Error de configuración (variable de entorno requerida ausente o inválida)."""
