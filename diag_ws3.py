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
        
        # 2. Probar Target.createBrowserContext (CDP estandar)
        msg = {"id": 2, "method": "Target.createBrowserContext", "params": {}}
        await ws.send(json.dumps(msg))
        print("Enviado Target.createBrowserContext")
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print("Respuesta:", resp[:300])
        except Exception as e:
            print("ERROR:", type(e).__name__, str(e)[:200])
        
        # 3. Probar Target.createTarget
        msg = {"id": 3, "method": "Target.createTarget", "params": {"url": "https://example.com"}}
        await ws.send(json.dumps(msg))
        print("Enviado Target.createTarget")
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print("Respuesta:", resp[:300])
        except Exception as e:
            print("ERROR:", type(e).__name__, str(e)[:200])
        
        # 4. Probar LP.configureLoading
        msg = {"id": 4, "method": "LP.configureLoading", "params": {}}
        await ws.send(json.dumps(msg))
        print("Enviado LP.configureLoading")
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print("Respuesta:", resp[:300])
        except Exception as e:
            print("ERROR:", type(e).__name__, str(e)[:200])

asyncio.run(test())
