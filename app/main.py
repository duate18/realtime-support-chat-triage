from collections import defaultdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Live Support Demo")

ROLES = {"customer", "agent"}


class RoomManager:
    """Tiene traccia di chi è collegato a ogni ticket (una "stanza" per ticket)."""

    def __init__(self) -> None:
        self.rooms: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, ticket_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms[ticket_id].append(ws)

    def disconnect(self, ticket_id: str, ws: WebSocket) -> None:
        self.rooms[ticket_id].remove(ws)
        if not self.rooms[ticket_id]:
            del self.rooms[ticket_id]

    async def broadcast(self, ticket_id: str, message: dict) -> None:
        for connection in list(self.rooms.get(ticket_id, [])):
            await connection.send_json(message)


manager = RoomManager()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws/{ticket_id}")
async def chat(ws: WebSocket, ticket_id: str, role: str = "customer") -> None:
    if role not in ROLES:
        await ws.close(code=1008)  # 1008 = violazione di policy
        return
    await manager.connect(ticket_id, ws)
    try:
        while True:
            text = await ws.receive_text()
            await manager.broadcast(ticket_id, {"from": role, "text": text})
    except WebSocketDisconnect:
        manager.disconnect(ticket_id, ws)
