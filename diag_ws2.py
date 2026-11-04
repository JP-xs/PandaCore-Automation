import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://127.0.0.1:9222/") as ws:
        print("Conectado al WebSocket")
        
        # 1. LP.version
        msg = {"id": 1, "method": "LP.version", "params": {}}
        await ws.send(json.dumps(msg))
        resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
        print("LP.version:", resp[:200])
        
        # 2. Probar Page.navigate
        msg = {"id": 2, "method": "Page.navigate", "params": {"url": "https://example.com", "waitUntil": "networkidle2"}}
        await ws.send(json.dumps(msg))
        print("Enviado Page.navigate")
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=10.0)
            print("Page.navigate respuesta:", resp[:300])
        except Exception as e:
            print("Page.navigate ERROR:", type(e).__name__, str(e)[:200])
        
        # 3. Probar LP.dump inmediatamente
        msg = {"id": 3, "method": "LP.dump", "params": {"format": "markdown", "strip": ["js", "css"]}}
        await ws.send(json.dumps(msg))
        print("Enviado LP.dump")
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=10.0)
            print("LP.dump respuesta:", resp[:300])
        except Exception as e:
            print("LP.dump ERROR:", type(e).__name__, str(e)[:200])

asyncio.run(test())
