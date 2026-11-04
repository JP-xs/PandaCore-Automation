import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://127.0.0.1:9222/") as ws:
        print("Conectado al WebSocket")
        
        # Tarea para leer mensajes entrantes continuamente
        async def reader():
            try:
                async for msg in ws:
                    print("RECV:", msg[:300])
            except Exception as e:
                print("Reader cerrado:", type(e).__name__, str(e)[:200])
        
        reader_task = asyncio.create_task(reader())
        
        await asyncio.sleep(0.5)
        
        # 1. LP.version
        msg = {"id": 1, "method": "LP.version", "params": {}}
        await ws.send(json.dumps(msg))
        print("ENVIADO: LP.version")
        await asyncio.sleep(1.0)
        
        # 2. Target.createBrowserContext
        msg = {"id": 2, "method": "Target.createBrowserContext", "params": {}}
        await ws.send(json.dumps(msg))
        print("ENVIADO: Target.createBrowserContext")
        await asyncio.sleep(1.0)
        
        # 3. Target.createTarget
        msg = {"id": 3, "method": "Target.createTarget", "params": {"url": "https://example.com"}}
        await ws.send(json.dumps(msg))
        print("ENVIADO: Target.createTarget")
        await asyncio.sleep(3.0)
        
        # 4. Intentar LP.dump
        msg = {"id": 4, "method": "LP.dump", "params": {"format": "markdown", "strip": ["js", "css"]}}
        await ws.send(json.dumps(msg))
        print("ENVIADO: LP.dump")
        await asyncio.sleep(2.0)
        
        reader_task.cancel()

asyncio.run(test())
