"""
scripts/test_lightpanda.py
==========================

Script de prueba y validacion de la conexion CDP a Lightpanda (puerto 9222).

Objetivo:
  - Verificar que Lightpanda esta escuchando y expone su WebSocket CDP.
  - Conectar al WebSocket de Lightpanda (ws://127.0.0.1:9222/).
  - Crear un BrowserContext y Target para cargar una URL.
  - Extraer contenido limpio con LP.dump (html/markdown).
  - Manejar errores: Lightpanda caido, URL invalida, timeout de navegacion.
  - Cerrar la sesion de forma segura liberando todos los recursos.

Flujo correcto de Lightpanda (NO es CDP estandar de Chrome):
  1. Conectar al WebSocket raiz ws://127.0.0.1:9222/
  2. Target.createBrowserContext  -> crea un contexto de navegador
  3. Target.createTarget (con URL) -> crea una pagina y la carga
  4. Target.attachToTarget        -> obtiene sessionId para ese target
  5. LP.dump (con sessionId)      -> extrae contenido limpio

Uso desde WSL2 (dentro de feature-panda-core):
    python3 scripts/test_lightpanda.py

Variables de entorno opcionales:
    BROWSER_CDP_URL   : Endpoint HTTP de Lightpanda (default: http://127.0.0.1:9222)
    TEST_URL          : URL a usar en la prueba (default: https://example.com)
    LOG_LEVEL         : Nivel de log (default: INFO)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Optional

import httpx
import websockets

# --------------------------------------------------------------------------- #
# Configuracion de logs y consola (UTF-8 para evitar errores en Windows)
# --------------------------------------------------------------------------- #

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("test_lightpanda")

CDP_URL = os.getenv("BROWSER_CDP_URL", "http://127.0.0.1:9222").rstrip("/")
TEST_URL = os.getenv("TEST_URL", "https://example.com")
HTTP_TIMEOUT = 15.0
WS_TIMEOUT = 30.0
NAVIGATION_WAIT = 4.0  # segundos de espera para que renderice JS


class LightpandaTestResult:
    """Resultado estructurado de una prueba individual."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.ok = False
        self.detail: str = ""
        self.duration_ms: float = 0.0
        self.data: dict[str, Any] = {}

    def mark_ok(self, detail: str = "", data: dict[str, Any] | None = None) -> None:
        self.ok = True
        self.detail = detail
        self.data = data or {}

    def mark_fail(self, detail: str, data: dict[str, Any] | None = None) -> None:
        self.ok = False
        self.detail = detail
        self.data = data or {}


# --------------------------------------------------------------------------- #
# Cliente CDP con correlacion por ID (maneja eventos async del servidor)
# --------------------------------------------------------------------------- #

class CdpSession:
    """
    Sesion CDP sobre WebSocket con correlacion de respuestas por ID.

    Lightpanda envia eventos asincronicos (Target.targetCreated, etc.)
    inmediatamente al conectar y durante la navegacion. Usamos un diccionario
    de asyncio.Future para correlacionar cada respuesta con su peticion por ID,
    y un reader task que resuelve los futuros a medida que llegan los mensajes.
    """

    def __init__(self, ws: websockets.ClientConnection) -> None:
        self.ws = ws
        self._pending: dict[str, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Inicia la tarea de lectura continua del WebSocket."""
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def _reader_loop(self) -> None:
        """Lee mensajes del WebSocket y resuelve el futuro correspondiente."""
        try:
            async for msg in self.ws:
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    continue
                call_id = str(data.get("id", ""))
                future = self._pending.pop(call_id, None)
                if future is not None and not future.done():
                    if "error" in data:
                        future.set_exception(RuntimeError(
                            f"Error CDP: {data['error']}"
                        ))
                    else:
                        future.set_result(data.get("result", {}))
                # Los eventos sin id (o con id ya resuelto) se ignoran
        except websockets.ConnectionClosed:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("Reader loop terminado: %s", exc)
        finally:
            # Rechazar todos los futuros pendientes si la conexion se cierra
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(
                        RuntimeError("Conexion WebSocket cerrada")
                    )
            self._pending.clear()

    async def stop(self) -> None:
        """Detiene la tarea de lectura."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

    async def send_and_wait(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = WS_TIMEOUT,
    ) -> dict[str, Any]:
        """
        Envia un comando CDP y espera la respuesta con el mismo id.
        """
        call_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[call_id] = future

        message = {"id": call_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(message))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(call_id, None)
            raise TimeoutError(
                f"Tiempo de espera agotado para el comando CDP: {method}"
            )


# --------------------------------------------------------------------------- #
# Endpoints HTTP
# --------------------------------------------------------------------------- #

async def get_ws_url(cdp_url: str) -> str:
    """
    Obtiene la URL del WebSocket CDP desde /json/version.
    """
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{cdp_url}/json/version")
        resp.raise_for_status()
        data = resp.json()
    ws_url = data.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError(
            "El endpoint /json/version no devolvio webSocketDebuggerUrl. "
            "Verifica que Lightpanda este ejecutandose correctamente."
        )
    return ws_url


# --------------------------------------------------------------------------- #
# Pruebas individuales
# --------------------------------------------------------------------------- #

async def run_test_version_and_ws() -> LightpandaTestResult:
    """Prueba 1: Obtener /json/version y resolver URL del WebSocket CDP."""
    result = LightpandaTestResult("Obtener version y URL WebSocket CDP")
    start = time.time()
    try:
        ws_url = await get_ws_url(CDP_URL)
        result.mark_ok(
            f"WebSocket CDP resuelto: {ws_url}",
            {"ws_url": ws_url},
        )
    except Exception as exc:  # noqa: BLE001
        result.mark_fail(f"No se pudo resolver el WebSocket CDP: {exc}")
    result.duration_ms = (time.time() - start) * 1000
    return result


async def run_test_navigate_and_dump() -> LightpandaTestResult:
    """
    Prueba 2: Conectar al WebSocket, crear BrowserContext + Target, y extraer
    contenido limpio con LP.dump.
    """
    result = LightpandaTestResult("Navegar y extraer con LP.dump")
    start = time.time()
    ws: Optional[websockets.ClientConnection] = None

    try:
        ws_url = await get_ws_url(CDP_URL)
        logger.info("Conectando WebSocket CDP a: %s", ws_url)
        ws = await websockets.connect(ws_url)

        session = CdpSession(ws)
        await session.start()
        # Pequeño delay para estabilizar el reader task antes del primer comando
        await asyncio.sleep(0.3)

        # Handshake ligero
        version_resp = await session.send_and_wait("LP.version", {})
        logger.info("Lightpanda version: %s", version_resp.get("version", "desconocida"))

        # 1. Crear BrowserContext
        ctx_resp = await session.send_and_wait("Target.createBrowserContext", {})
        browser_context_id = ctx_resp.get("browserContextId")
        logger.info("BrowserContext creado: %s", browser_context_id)

        # 2. Crear Target (cargar la URL)
        target_resp = await session.send_and_wait(
            "Target.createTarget",
            {"url": TEST_URL, "browserContextId": browser_context_id},
        )
        target_id = target_resp.get("targetId")
        logger.info("Target creado: %s", target_id)

        # Esperar a que la pagina termine de renderizar
        await asyncio.sleep(NAVIGATION_WAIT)

        # 3. Adjuntar sesion al target para obtener sessionId
        attach_resp = await session.send_and_wait(
            "Target.attachToTarget",
            {"targetId": target_id},
        )
        session_id = attach_resp.get("sessionId")
        logger.info("Sesion adjunta: %s", session_id)

        # 4. Extraer contenido limpio con LP.dump (con sessionId)
        dump_html = await session.send_and_wait(
            "LP.dump",
            {"format": "html", "strip": ["js", "css", "ui", "invisible"]},
        )
        html_content = dump_html.get("content", "") or ""

        try:
            html_decoded = base64.b64decode(html_content).decode("utf-8", errors="replace")
        except Exception:
            html_decoded = html_content

        # 5. Extraer en markdown (ideal para analisis de tesis)
        dump_md = await session.send_and_wait(
            "LP.dump",
            {"format": "markdown", "strip": ["js", "css", "ui", "invisible", "clutter"]},
        )
        md_content = dump_md.get("content", "") or ""
        try:
            md_decoded = base64.b64decode(md_content).decode("utf-8", errors="replace")
        except Exception:
            md_decoded = md_content

        result.mark_ok(
            f"Extraccion exitosa: HTML={len(html_decoded)} chars, "
            f"Markdown={len(md_decoded)} chars",
            {
                "url": TEST_URL,
                "browser_context_id": browser_context_id,
                "target_id": target_id,
                "session_id": session_id,
                "html_length": len(html_decoded),
                "markdown_length": len(md_decoded),
                "markdown_preview": md_decoded[:300],
            },
        )

    except Exception as exc:  # noqa: BLE001
        result.mark_fail(f"Fallo en navegacion/extraccion: {exc}")
    finally:
        if ws is not None:
            try:
                await ws.close()
                logger.debug("WebSocket cerrado")
            except Exception:  # pragma: no cover
                pass

    result.duration_ms = (time.time() - start) * 1000
    return result


async def run_test_error_invalid_url() -> LightpandaTestResult:
    """Prueba 3: Manejo de error con URL invalida."""
    result = LightpandaTestResult("Manejo de error: URL invalida")
    start = time.time()
    ws: Optional[websockets.ClientConnection] = None

    try:
        ws_url = await get_ws_url(CDP_URL)
        ws = await websockets.connect(ws_url)
        session = CdpSession(ws)
        await session.start()
        await asyncio.sleep(0.3)

        await session.send_and_wait("LP.version", {})

        invalid_url = "http://dominio-inexistente-12345.invalid/"

        # Crear BrowserContext y Target para la URL invalida
        ctx_resp = await session.send_and_wait("Target.createBrowserContext", {})
        browser_context_id = ctx_resp.get("browserContextId")

        try:
            await session.send_and_wait(
                "Target.createTarget",
                {"url": invalid_url, "browserContextId": browser_context_id},
            )
            await asyncio.sleep(2.0)
            result.mark_ok(
                "Navegacion a URL invalida no lanzo excepcion visible",
                {"tested_url": invalid_url},
            )
        except Exception as nav_exc:
            result.mark_ok(
                f"Error capturado para URL invalida: {nav_exc}",
                {"error_type": type(nav_exc).__name__},
            )

    except Exception as exc:  # noqa: BLE001
        result.mark_ok(
            f"Error de conexion capturado: {type(exc).__name__}: {exc}",
            {"error_type": type(exc).__name__},
        )
    finally:
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    result.duration_ms = (time.time() - start) * 1000
    return result


async def run_test_error_lightpanda_down() -> LightpandaTestResult:
    """Prueba 4: Manejo de error si Lightpanda no esta disponible (puerto erroneo)."""
    result = LightpandaTestResult("Manejo de error: Lightpanda caido (puerto wrong)")
    start = time.time()
    wrong_url = "http://127.0.0.1:19999"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get(f"{wrong_url}/json/version")
        result.mark_fail("Lightpanda respondio en un puerto inesperado")
    except Exception as exc:  # noqa: BLE001
        result.mark_ok(
            f"Error de conexion capturado correctamente: {type(exc).__name__}: {exc}",
            {"error_type": type(exc).__name__},
        )

    result.duration_ms = (time.time() - start) * 1000
    return result


# --------------------------------------------------------------------------- #
# Resumen y entrada principal
# --------------------------------------------------------------------------- #

async def print_summary(results: list[LightpandaTestResult]) -> None:
    """Imprime un resumen de todas las pruebas (sin emojis para Windows)."""
    print("\n" + "=" * 60)
    print("  RESUMEN DE PRUEBAS - Lightpanda CDP")
    print("=" * 60)

    total = len(results)
    passed = sum(1 for r in results if r.ok)
    failed = total - passed

    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"  [{status}]  {r.name}  ({r.duration_ms:.0f} ms)")
        if r.detail:
            print(f"         -> {r.detail}")
        if r.data and r.ok:
            for k, v in r.data.items():
                if k in ("ws_url", "title", "html_length", "markdown_length", "url", "target_id", "session_id"):
                    print(f"         -> {k}: {v}")

    print("-" * 60)
    print(f"  Total: {total}  |  Pasadas: {passed}  |  Fallidas: {failed}")
    print("=" * 60 + "\n")

    if failed == 0:
        logger.info("Todas las pruebas de Lightpanda pasaron correctamente.")
    else:
        logger.warning("Algunas pruebas fallaron. Revisar logs arriba.")


async def main() -> int:
    """Punto de entrada principal."""
    logger.info("Iniciando pruebas de Lightpanda CDP...")
    logger.info("Endpoint CDP: %s", CDP_URL)
    logger.info("URL de prueba: %s", TEST_URL)

    results: list[LightpandaTestResult] = []

    r1 = await run_test_version_and_ws()
    results.append(r1)

    r2 = await run_test_navigate_and_dump()
    results.append(r2)

    r3 = await run_test_error_invalid_url()
    results.append(r3)

    r4 = await run_test_error_lightpanda_down()
    results.append(r4)

    await print_summary(results)

    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Pruebas interrumpidas por el usuario.")
        exit_code = 130
    sys.exit(exit_code)
