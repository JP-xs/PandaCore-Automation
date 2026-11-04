"""
core/browser.py
===============

Modulo de navegacion y conexion hacia el navegador headless Lightpanda
mediante el Chrome DevTools Protocol (CDP) en su variante nativa de Lightpanda.

IMPORTANTE: Lightpanda NO expone el CDP estandar de Chrome. Habla un protocolo
CDP-similar con metodos propios (LP.version, Target.createBrowserContext,
Target.createTarget, Target.attachToTarget, LP.dump). Este modulo implementa
exactamente ese flujo, tal como lo validan los scripts de diagnostico de
referencia del proyecto (scripts/test_lightpanda.py y diag_ws*.py).

Responsabilidades:
  - Establecer una sesion CDP asincronica con Lightpanda (WSL2 u OpenCloud).
  - Navegar a una URL y esperar a que la página renderice (incluido JS).
  - Extraer contenido limpio y estructurado (HTML y Markdown) listo para ser
    procesado por IA, mediante LP.dump.
  - Reintentos con backoff exponencial ante fallos de red o servidor inactivo.

Este modulo es agnostico a la interfaz: solo expone logica de navegacion que el
Motor Core (FastAPI) y cualquier otro consumidor pueden reutilizar.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx
import websockets
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import settings
from core.exceptions import (
    LightpandaConnectionError,
    LightpandaExtractionError,
    LightpandaNavigationError,
)

logger = logging.getLogger(__name__)

# Excepciones que deben disparar un reintento automático.
_RETRYABLE_EXCEPTIONS = (
    LightpandaConnectionError,
    LightpandaNavigationError,
    LightpandaExtractionError,
    ConnectionError,
    OSError,
    TimeoutError,
)


@dataclass
class ExtractionResult:
    """Resultado de la extracción de una página web."""

    url: str
    title: str
    html: str
    text: str  # versión en Markdown (limpia y óptima para IA)
    status_code: int = 200


# --------------------------------------------------------------------------- #
# Cliente de sesión CDP sobre WebSocket
# --------------------------------------------------------------------------- #
class CDPSession:
    """
    Sesión CDP sobre WebSocket con correlación de respuestas por ID.

    Lightpanda envía eventos asíncronos (p. ej. Target.targetCreated) al
    conectar y durante la navegación. La cola de mensajes permite vincular cada
    respuesta con su petición mediante el `id` sin perder eventos intermedios.
    """

    def __init__(self, ws_url: str, timeout: float = 30.0) -> None:
        self.ws_url = ws_url
        self.timeout = timeout
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._queue: "asyncio.Queue[str]" = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None

    async def __aenter__(self) -> "CDPSession":
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def open(self) -> None:
        """Abre la conexión WebSocket y lanza el lector de mensajes."""
        self._ws = await websockets.connect(self.ws_url, open_timeout=self.timeout)
        self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        """Cierra la sesión y cancela el lector de mensajes."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._ws is not None:
            await self._ws.close()

    async def _read_loop(self) -> None:
        """Lee mensajes del WebSocket continuamente y los pone en la cola."""
        assert self._ws is not None
        try:
            async for message in self._ws:
                await self._queue.put(message)
        except websockets.ConnectionClosed:
            pass  # Conexión cerrada normalmente
        except Exception as exc:  # noqa: BLE001
            logger.debug("Bucle de lector CDP terminado: %s", exc)

    async def send_and_wait(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Envía un comando CDP y espera la respuesta con el mismo id.

        Los eventos intermedios (sin id coincidente) se descartan silenciosamente.
        Lanza LightpandaConnectionError si el servidor devuelve un error o si se
        agota el tiempo de espera.
        """
        if self._ws is None:
            raise LightpandaConnectionError("WebSocket no está abierto")

        call_id = str(uuid.uuid4())
        message = {"id": call_id, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(message))

        deadline = asyncio.get_running_loop().time() + (timeout or self.timeout)
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise LightpandaConnectionError(
                    f"Tiempo de espera agotado para el comando CDP: {method}"
                )
            try:
                raw = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                raise LightpandaConnectionError(
                    f"Tiempo de espera agotado para el comando CDP: {method}"
                )

            data = json.loads(raw)
            if data.get("id") == call_id:
                if "error" in data:
                    raise LightpandaConnectionError(
                        f"Error CDP en {method}: {data['error']}"
                    )
                return data.get("result", {}) or {}
            # Evento no relacionado: lo ignoramos y seguimos esperando la respuesta.


# --------------------------------------------------------------------------- #
# Navegador de alto nivel sobre Lightpanda
# --------------------------------------------------------------------------- #
def _decode_content(content: Any) -> str:
    """
    Decodifica el contenido devuelto por LP.dump.

    Lightpanda devuelve el contenido codificado en base64. Si no es base64
    válido, se devuelve la cadena tal cual.
    """
    if content is None:
        return ""
    if not isinstance(content, str):
        content = str(content)
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except Exception:
        return content


_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _extract_title(html: str) -> str:
    """Extrae el título de una página a partir de su HTML."""
    match = _TITLE_RE.search(html or "")
    if match:
        return match.group(1).strip()
    return ""


class LightpandaBrowser:
    """Navegador de alto nivel sobre Lightpanda vía CDP (protocolo nativo)."""

    def __init__(self, lightpanda_url: Optional[str] = None) -> None:
        self.lightpanda_url = (lightpanda_url or settings.LIGHTPANDA_URL).rstrip("/")
        self._session: Optional[CDPSession] = None

    async def start(self) -> None:
        """Conecta con Lightpanda, obtiene el endpoint WebSocket de CDP y hace handshake."""
        await self._connect()

    async def stop(self) -> None:
        """Cierra la sesión CDP si está abierta."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "LightpandaBrowser":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def _fetch_ws_url(self) -> str:
        """Consulta /json/version de Lightpanda para obtener la URL de depuración WebSocket."""
        version_url = f"{self.lightpanda_url}/json/version"
        async with httpx.AsyncClient(timeout=settings.CDP_CONNECT_TIMEOUT) as client:
            try:
                resp = await client.get(version_url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise LightpandaConnectionError(
                    f"No se pudo contactar con Lightpanda en {version_url}: {exc}"
                ) from exc
        data = resp.json()
        ws_url = data.get("webSocketDebuggerUrl")
        if not ws_url:
            raise LightpandaConnectionError(
                f"Lightpanda no devolvió webSocketDebuggerUrl: {data}"
            )
        logger.debug("WebSocket CDP obtenido: %s", ws_url)
        return ws_url

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_BACKOFF, min=1, max=30),
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    )
    async def _connect(self) -> None:
        ws_url = await self._fetch_ws_url()
        session = CDPSession(ws_url, timeout=settings.NAVIGATION_TIMEOUT)
        await session.open()
        # Handshake ligero contra Lightpanda
        await session.send_and_wait("LP.version", {}, timeout=settings.CDP_CONNECT_TIMEOUT)
        self._session = session
        logger.info("Sesión CDP establecida con Lightpanda (%s)", self.lightpanda_url)

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_BACKOFF, min=1, max=30),
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
    )
    async def navigate_and_extract(self, url: str) -> ExtractionResult:
        """
        Navega a la URL y extrae título, HTML limpio y Markdown de la página.

        Flujo Lightpanda:
          1. Target.createBrowserContext
          2. Target.createTarget (con la URL)
          3. Espera de renderizado (NAVIGATION_WAIT)
          4. Target.attachToTarget (obtiene sessionId)
          5. LP.dump (formato html y markdown)
        """
        if self._session is None:
            await self._connect()
        assert self._session is not None
        session = self._session

        # 1. Crear contexto de navegador
        try:
            ctx = await session.send_and_wait("Target.createBrowserContext", {})
        except Exception as exc:
            raise LightpandaNavigationError(
                f"Error creando BrowserContext para {url}: {exc}"
            ) from exc
        browser_context_id = ctx.get("browserContextId")
        if not browser_context_id:
            raise LightpandaNavigationError(
                f"Lightpanda no devolvió browserContextId para {url}: {ctx}"
            )

        # 2. Crear target (carga la URL)
        try:
            target = await session.send_and_wait(
                "Target.createTarget",
                {"url": url, "browserContextId": browser_context_id},
                timeout=settings.NAVIGATION_TIMEOUT,
            )
        except Exception as exc:
            raise LightpandaNavigationError(
                f"Error creando Target para {url}: {exc}"
            ) from exc
        target_id = target.get("targetId")
        if not target_id:
            raise LightpandaNavigationError(
                f"Lightpanda no devolvió targetId para {url}: {target}"
            )

        # 3. Esperar a que la página renderice (JS incluido)
        await asyncio.sleep(settings.NAVIGATION_WAIT)

        # 4. Adjuntar sesión al target
        try:
            attach = await session.send_and_wait(
                "Target.attachToTarget", {"targetId": target_id}
            )
        except Exception as exc:
            raise LightpandaNavigationError(
                f"Error adjuntando sesión al target {target_id}: {exc}"
            ) from exc
        session_id = attach.get("sessionId")

        # 5. Extraer contenido limpio con LP.dump (HTML y Markdown)
        html_content = ""
        text_content = ""
        try:
            dump_html = await session.send_and_wait(
                "LP.dump",
                {"format": "html", "strip": ["js", "css", "ui", "invisible"]},
            )
            html_content = _decode_content(dump_html.get("content"))
        except Exception as exc:
            raise LightpandaExtractionError(
                f"Error extrayendo HTML de {url}: {exc}"
            ) from exc

        try:
            dump_md = await session.send_and_wait(
                "LP.dump",
                {
                    "format": "markdown",
                    "strip": ["js", "css", "ui", "invisible", "clutter"],
                },
            )
            text_content = _decode_content(dump_md.get("content"))
        except Exception as exc:
            raise LightpandaExtractionError(
                f"Error extrayendo Markdown de {url}: {exc}"
            ) from exc

        # Limpieza opcional del target para no acumular objetivos en Lightpanda
        if target_id:
            try:
                await session.send_and_wait("Target.closeTarget", {"targetId": target_id})
            except Exception:  # noqa: BLE001
                logger.debug("No se pudo cerrar el target %s (no crítico)", target_id)

        title = _extract_title(html_content)

        return ExtractionResult(
            url=url,
            title=title,
            html=html_content,
            text=text_content,
            status_code=200,
        )
