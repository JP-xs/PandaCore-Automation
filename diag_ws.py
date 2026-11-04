import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://127.0.0.1:9222/") as ws:
        print("Conectado al WebSocket")
        msg = {"id": 1, "method": "LP.version", "params": {}}
        await ws.send(json.dumps(msg))
        print("Enviado LP.version")
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print("Respuesta:", resp[:500])
        except Exception as e:
            print("Error recibiendo:", type(e).__name__, str(e)[:200])

asyncio.run(test())
