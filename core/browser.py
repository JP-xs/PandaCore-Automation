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
    conectar y durante la navegación. Cada respuesta se vincula a su petición
    mediante el `id`; los eventos intermedios (sin id coincidente) se ignoran.
    """

    def __init__(self, ws_url: str, timeout: float = 30.0) -> None:
        self.ws_url = ws_url
        self.timeout = timeout
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._next_id = 0

    async def __aenter__(self) -> "CDPSession":
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def open(self) -> None:
        """Abre la conexión WebSocket."""
        self._ws = await websockets.connect(self.ws_url, open_timeout=self.timeout)

    async def close(self) -> None:
        """Cierra la sesión WebSocket."""
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    def _next_message_id(self) -> int:
        """Devuelve el siguiente id numérico (Lightpanda requiere ids numéricos)."""
        self._next_id += 1
        return self._next_id

    async def send_and_wait(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Envía un comando CDP y espera la respuesta con el mismo id.

        Lee directamente del WebSocket. Los eventos asíncronos intermedios
        (sin id coincidente) se ignoran y se sigue esperando hasta encontrar
        la respuesta de esta petición o agotarse el tiempo de espera.
        Lanza LightpandaConnectionError si el servidor devuelve un error o si
        se agota el tiempo de espera.
        """
        if self._ws is None:
            raise LightpandaConnectionError("WebSocket no está abierto")

        call_id = self._next_message_id()
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
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
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
            # Evento no relacionado (p. ej. Target.targetCreated): lo ignoramos
            # y seguimos esperando la respuesta de esta petición.


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

    async def _connect(self) -> None:
        """
        Conecta con Lightpanda con reintentos manuales (backoff exponencial).

        Usamos reintentos manuales en lugar del decorador @retry de tenacity
        porque este último interfería con la sesión WebSocket abierta (cerraba
        el canal tras el primer comando).
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                ws_url = await self._fetch_ws_url()
                session = CDPSession(ws_url, timeout=settings.NAVIGATION_TIMEOUT)
                await session.open()
                # Handshake ligero contra Lightpanda
                await session.send_and_wait("LP.version", {}, timeout=settings.CDP_CONNECT_TIMEOUT)
                self._session = session
                logger.info("Sesión CDP establecida con Lightpanda (%s)", self.lightpanda_url)
                return
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt < settings.MAX_RETRIES:
                    wait = settings.RETRY_BACKOFF * attempt
                    logger.warning(
                        "Intento %d/%d falló al conectar con Lightpanda: %s. "
                        "Reintentando en %.1fs...",
                        attempt, settings.MAX_RETRIES, exc, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "No se pudo conectar con Lightpanda tras %d intentos: %s",
                        settings.MAX_RETRIES, exc,
                    )
        assert last_exc is not None
        raise last_exc

    async def navigate_and_extract(self, url: str) -> ExtractionResult:
        """
        Navega a la URL y extrae título, HTML limpio y Markdown de la página.

        Flujo Lightpanda:
          1. Target.createBrowserContext
          2. Target.createTarget (con la URL)
          3. Espera de renderizado (NAVIGATION_WAIT)
          4. Target.attachToTarget (obtiene sessionId)
          5. LP.dump (formato html y markdown)

        Los reintentos son manuales (backoff exponencial) para no interferir
        con la sesión WebSocket abierta.
        """
        last_exc: Optional[Exception] = None
        previous_target_id: Optional[str] = None
        for attempt in range(1, settings.MAX_RETRIES + 1):
            try:
                if self._session is None:
                    await self._connect()
                assert self._session is not None
                session = self._session

                # Evitar TargetAlreadyLoaded: cerrar el target del intento previo
                if previous_target_id:
                    try:
                        await session.send_and_wait(
                            "Target.closeTarget", {"targetId": previous_target_id}
                        )
                    except Exception:  # noqa: BLE001
                        logger.debug(
                            "No se pudo cerrar el target previo %s", previous_target_id
                        )
                    previous_target_id = None

                # 1. Crear contexto de navegador (Lightpanda solo permite uno a la vez;
                # si ya hay uno abierto de una sesión previa, se usa el contexto por defecto).
                browser_context_id: Optional[str] = None
                try:
                    ctx = await session.send_and_wait("Target.createBrowserContext", {})
                    browser_context_id = ctx.get("browserContextId")
                    if browser_context_id:
                        logger.debug("BrowserContext creado: %s", browser_context_id)
                except LightpandaConnectionError as exc:
                    msg = str(exc)
                    if "more than one browser context" in msg:
                        logger.warning(
                            "Lightpanda ya tiene un BrowserContext abierto; se usará el contexto por defecto"
                        )
                        browser_context_id = None
                    else:
                        raise LightpandaNavigationError(
                            f"Error creando BrowserContext para {url}: {exc}"
                        ) from exc

                # 2. Crear target (carga la URL)
                create_target_params: Dict[str, Any] = {"url": url}
                if browser_context_id:
                    create_target_params["browserContextId"] = browser_context_id
                try:
                    target = await session.send_and_wait(
                        "Target.createTarget",
                        create_target_params,
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
                previous_target_id = target_id

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
                if not session_id:
                    raise LightpandaNavigationError(
                        f"Lightpanda no devolvió sessionId para el target {target_id}"
                    )

                # 5. Extraer contenido limpio con LP.dump (HTML y Markdown).
                # Lightpanda requiere sessionId y no acepta el parámetro 'strip'
                # (devuelve UnexpectedToken si se envía).
                html_content = ""
                text_content = ""
                try:
                    dump_html = await session.send_and_wait(
                        "LP.dump",
                        {"format": "html", "sessionId": session_id},
                        timeout=settings.NAVIGATION_TIMEOUT,
                    )
                    html_content = _decode_content(dump_html.get("content", ""))
                except Exception as exc:
                    raise LightpandaExtractionError(
                        f"Error extrayendo HTML de {url}: {exc}"
                    ) from exc

                try:
                    dump_md = await session.send_and_wait(
                        "LP.dump",
                        {"format": "markdown", "sessionId": session_id},
                        timeout=settings.NAVIGATION_TIMEOUT,
                    )
                    text_content = _decode_content(dump_md.get("content", ""))
                except Exception as exc:
                    raise LightpandaExtractionError(
                        f"Error extrayendo Markdown de {url}: {exc}"
                    ) from exc

                # Limpieza del target y del browser context entre peticiones.
                if target_id:
                    try:
                        await session.send_and_wait(
                            "Target.closeTarget", {"targetId": target_id}
                        )
                    except Exception:  # noqa: BLE001
                        logger.debug("No se pudo cerrar el target %s (no crítico)", target_id)
                        previous_target_id = target_id  # intentar cerrar en el siguiente intento
                if browser_context_id:
                    try:
                        await session.send_and_wait(
                            "Target.disposeBrowserContext",
                            {"browserContextId": browser_context_id},
                        )
                    except Exception:  # noqa: BLE001
                        logger.debug(
                            "No se pudo disposeBrowserContext %s (no crítico)",
                            browser_context_id,
                        )

                title = _extract_title(html_content)

                return ExtractionResult(
                    url=url,
                    title=title,
                    html=html_content,
                    text=text_content,
                    status_code=200,
                )
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt < settings.MAX_RETRIES:
                    wait = settings.RETRY_BACKOFF * attempt
                    logger.warning(
                        "Intento %d/%d falló al extraer %s: %s. "
                        "Reintentando en %.1fs...",
                        attempt, settings.MAX_RETRIES, url, exc, wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "No se pudo extraer %s tras %d intentos: %s",
                        url, settings.MAX_RETRIES, exc,
                    )
        assert last_exc is not None
        raise last_exc
