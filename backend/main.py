"""
NetWhisper - Backend & Live Telemetry Server
Role: Keerthana (Backend / Integration / Dashboard)

FastAPI application providing REST endpoints and WebSocket stream for the
NetWhisper acoustic communication monitoring dashboard.
"""

import asyncio
import json
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models import SystemStatus, TransmissionRequest
from .engine_adapter import engine_adapter

app = FastAPI(
    title="NetWhisper Telemetry API",
    description="Real-time monitoring dashboard backend for acoustic data communication",
    version="1.0.0"
)

# Enable CORS for local Vite / frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ActiveWebSocketsManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead)


ws_manager = ActiveWebSocketsManager()


# Register engine adapter listener to broadcast directly over WebSockets
def on_adapter_event(event_dict: dict):
    if ws_manager.active_connections:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(ws_manager.broadcast(event_dict))
        except RuntimeError:
            pass

engine_adapter.add_telemetry_listener(on_adapter_event)


@app.get("/api/status", response_model=SystemStatus)
async def get_system_status():
    """Retrieve current communication status, metrics, and recent packets."""
    return engine_adapter.get_status()


@app.post("/api/transmit")
async def transmit_message(req: TransmissionRequest):
    """
    Transmit a text message.
    Delegates to acoustic engine if connected, or runs synthetic loopback if in TEST_MODE.
    """
    result = await engine_adapter.transmit_message(req.message, req.simulate_noise)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Transmission failed"))
    return result


class ModeRequest(BaseModel):
    test_mode: bool


@app.post("/api/mode")
async def set_mode(req: ModeRequest):
    """Toggle between Awaiting Engine (Idle) and Test Loopback Mode."""
    engine_adapter.set_test_mode(req.test_mode)
    status = engine_adapter.get_status()
    await ws_manager.broadcast({
        "type": "STATUS_UPDATE",
        "status": status.model_dump()
    })
    return {"success": True, "active_mode": status.active_mode_label, "state": status.state.value}


@app.post("/api/reset")
async def reset_metrics():
    """Reset counters, recent packets, and metrics."""
    engine_adapter.reset_stats()
    status = engine_adapter.get_status()
    await ws_manager.broadcast({
        "type": "METRICS_RESET",
        "status": status.model_dump()
    })
    return {"success": True, "message": "Metrics reset successfully"}


@app.get("/api/integration-info")
async def get_integration_info():
    """
    Returns integration contract specs for Marnia's engine.
    """
    return {
        "project": "NetWhisper — Reliable Data Communication over an Acoustic Channel",
        "teammate_engine_role": "Marnia (FSK, Packet Framing, Audio I/O, CRC)",
        "dashboard_backend_role": "Keerthana (FastAPI, WebSockets, Dashboard, Integration)",
        "engine_registered": engine_adapter.acoustic_engine is not None,
        "contract": {
            "hook_function": "engine_adapter.register_acoustic_engine(engine_instance)",
            "expected_engine_interface": [
                "engine.transmit(text: str) -> dict",
                "engine.receive_callback = callback_func",
                "engine.audio_stream_callback = callback_func (optional for live spectrogram/waveform)"
            ],
            "data_rules": [
                "Real acoustic status only shown when engine is registered.",
                "Synthetic loopback strictly marked as 'TEST_LOOPBACK (Synthetic - Not Acoustic)'."
            ]
        }
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time status, live waveform streaming, and packet events.
    """
    await ws_manager.connect(websocket)
    # Send initial snapshot upon connection
    initial_status = engine_adapter.get_status()
    await websocket.send_text(json.dumps({
        "type": "INITIAL_STATE",
        "status": initial_status.model_dump(),
        "waveform": engine_adapter.current_signal_samples
    }))

    try:
        while True:
            # Handle incoming client commands over WS if any
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                if cmd.get("action") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif cmd.get("action") == "get_status":
                    status = engine_adapter.get_status()
                    await websocket.send_text(json.dumps({
                        "type": "STATUS_UPDATE",
                        "status": status.model_dump(),
                        "waveform": engine_adapter.current_signal_samples
                    }))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# Mount built frontend dist if available (for single-command running)
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.exists(frontend_dist) and os.path.exists(os.path.join(frontend_dist, "index.html")):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api") or full_path.startswith("ws"):
            raise HTTPException(status_code=404, detail="Not Found")
        target = os.path.join(frontend_dist, full_path)
        if full_path and os.path.exists(target) and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

