"""WebSocket /events/{job_id} — push pipeline events to the extension popup."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/events/{job_id}")
async def events(ws: WebSocket, job_id: str):
    await ws.accept()
    bus = ws.app.state.bus
    q = await bus.subscribe(job_id)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=60)
                await ws.send_json(msg)
                if msg.get("type") in ("done", "failed"):
                    return
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        return
    finally:
        await bus.unsubscribe(job_id, q)
