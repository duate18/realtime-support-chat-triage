from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.classifier import load_model
from app.tickets import TicketStore
from app.triage import load_faq, triage

app = FastAPI(title="Live Support Demo")

PAGES = Path(__file__).parent / "pages"
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
store = TicketStore()
lobby: list[WebSocket] = []  # console degli operatori collegate (ricevono la coda dei ticket)


@lru_cache
def get_triage_tools():
    """Carica modello e help center una sola volta, alla prima richiesta."""
    return load_model(), load_faq()


async def notify_agents() -> None:
    """Manda la coda aggiornata a tutte le console degli operatori collegate."""
    message = {"type": "queue", "tickets": store.queue()}
    for ws in list(lobby):
        try:
            await ws.send_json(message)
        except Exception:  # console chiusa nel frattempo: la togliamo dalla lista
            if ws in lobby:
                lobby.remove(ws)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def customer_page() -> FileResponse:
    return FileResponse(PAGES / "customer.html")


@app.get("/agent")
def agent_page() -> FileResponse:
    return FileResponse(PAGES / "agent.html")


@app.get("/api/tickets/{ticket_id}")
def ticket_history(ticket_id: str) -> dict:
    ticket = store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket non trovato")
    return {"id": ticket.id, "messages": ticket.messages}


@app.websocket("/ws-agents")
async def agents_lobby(ws: WebSocket) -> None:
    await ws.accept()
    lobby.append(ws)
    await ws.send_json({"type": "queue", "tickets": store.queue()})
    try:
        while True:
            await ws.receive_text()  # le console non mandano nulla: serve solo ad accorgersi della chiusura
    except WebSocketDisconnect:
        if ws in lobby:
            lobby.remove(ws)


@app.websocket("/ws/{ticket_id}")
async def chat(ws: WebSocket, ticket_id: str, role: str = "customer") -> None:
    if role not in ROLES:
        await ws.close(code=1008)  # 1008 = violazione di policy
        return
    await manager.connect(ticket_id, role, ws)
    try:
        while True:
            text = await ws.receive_text()
            store.add_message(ticket_id, role, text)  # prima salviamo, così lo storico è già aggiornato
            await manager.broadcast(ticket_id, {"type": "message", "from": role, "text": text})
            if role == "customer":
                model, faq = get_triage_tools()
                # L'analisi usa la CPU: la eseguiamo in un thread per non bloccare la chat degli altri.
                result = await run_in_threadpool(triage, model, faq, text)
                store.set_triage(ticket_id, result)
                # Il suggerimento lo vede solo l'operatore, mai il cliente.
                await manager.broadcast(ticket_id, {"type": "suggestion", **result}, only_role="agent")
            await notify_agents()
    except WebSocketDisconnect:
        manager.disconnect(ticket_id, ws)
