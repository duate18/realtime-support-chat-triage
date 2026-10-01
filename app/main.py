from collections import defaultdict
from functools import lru_cache

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from app.classifier import load_model
from app.triage import load_faq, triage

app = FastAPI(title="Live Support Demo")

ROLES = {"customer", "agent"}


class RoomManager:
    """Tiene traccia di chi è collegato a ogni ticket (una "stanza" per ticket) e con quale ruolo."""

    def __init__(self) -> None:
        self.rooms: dict[str, list[tuple[str, WebSocket]]] = defaultdict(list)

    async def connect(self, ticket_id: str, role: str, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms[ticket_id].append((role, ws))

    def disconnect(self, ticket_id: str, ws: WebSocket) -> None:
        remaining = [(r, c) for r, c in self.rooms[ticket_id] if c is not ws]
        if remaining:
            self.rooms[ticket_id] = remaining
        else:
            del self.rooms[ticket_id]

    async def broadcast(self, ticket_id: str, message: dict, only_role: str | None = None) -> None:
        """Invia il messaggio a tutti nella stanza, oppure solo a chi ha il ruolo indicato."""
        for role, connection in list(self.rooms.get(ticket_id, [])):
            if only_role is None or role == only_role:
                await connection.send_json(message)


manager = RoomManager()


@lru_cache
def get_triage_tools():
    """Carica modello e help center una sola volta, alla prima richiesta."""
    return load_model(), load_faq()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws/{ticket_id}")
async def chat(ws: WebSocket, ticket_id: str, role: str = "customer") -> None:
    if role not in ROLES:
        await ws.close(code=1008)  # 1008 = violazione di policy
        return
    await manager.connect(ticket_id, role, ws)
    try:
        while True:
            text = await ws.receive_text()
            await manager.broadcast(ticket_id, {"type": "message", "from": role, "text": text})
            if role == "customer":
                model, faq = get_triage_tools()
                # L'analisi usa la CPU: la eseguiamo in un thread per non bloccare la chat degli altri.
                result = await run_in_threadpool(triage, model, faq, text)
                # Il suggerimento lo vede solo l'operatore, mai il cliente.
                await manager.broadcast(ticket_id, {"type": "suggestion", **result}, only_role="agent")
    except WebSocketDisconnect:
        manager.disconnect(ticket_id, ws)
