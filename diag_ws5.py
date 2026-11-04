import asyncio
import websockets
import json

async def send_and_wait(ws, method, params, timeout=10.0, call_id=None):
    if call_id is None:
        call_id = time.time() if 'time' in dir() else 1
    import time as _t
    call_id = _t.time()
    msg = {"id": call_id, "method": method, "params": params or {}}
    await ws.send(json.dumps(msg))
    print(f"ENVIADO: {method} (id={call_id})")
    
    deadline = _t.time() + timeout
    while _t.time() < deadline:
        remaining = deadline - _t.time()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            print("  TIMEOUT esperando respuesta")
            return None
        
        data = json.loads(raw)
        if data.get("id") == call_id:
            print(f"  RESPUESTA: {json.dumps(data)[:300]}")
            return data
        else:
            print(f"  EVENTO ignorado: {data.get('method', '?')}")
    
    return None

async def test():
    import time
    async with websockets.connect("ws://127.0.0.1:9222/") as ws:
        print("Conectado al WebSocket\n")
        
        # 1. LP.version
        await send_and_wait(ws, "LP.version", {})
        await asyncio.sleep(0.5)
        
        # 2. Target.createBrowserContext
        ctx = await send_and_wait(ws, "Target.createBrowserContext", {})
        browser_context_id = ctx.get("result", {}).get("browserContextId")
        print(f"  -> browserContextId: {browser_context_id}\n")
        await asyncio.sleep(0.5)
        
        # 3. Target.createTarget con URL
        target = await send_and_wait(
            ws, "Target.createTarget",
            {"url": "https://example.com", "browserContextId": browser_context_id}
        )
        target_id = target.get("result", {}).get("targetId")
        print(f"  -> targetId: {target_id}\n")
        await asyncio.sleep(3.0)
        
        # 4. Target.attachToTarget
        session = await send_and_wait(
            ws, "Target.attachToTarget",
            {"targetId": target_id}
        )
        session_id = session.get("result", {}).get("sessionId")
        print(f"  -> sessionId: {session_id}\n")
        await asyncio.sleep(1.0)
        
        # 5. LP.dump con sessionId
        await send_and_wait(
            ws, "LP.dump",
            {"format": "markdown", "strip": ["js", "css"]},
            call_id=100
        )
        
        await asyncio.sleep(1.0)

asyncio.run(test())
