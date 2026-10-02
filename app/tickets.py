"""Archivio in memoria dei ticket: messaggi, ultimo smistamento e coda ordinata per l'operatore."""
import time
from dataclasses import dataclass, field

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Ticket:
    id: str
    created_at: float
    messages: list[dict] = field(default_factory=list)
    triage: dict | None = None  # smistamento dell'ultimo messaggio del cliente (serve per il suggerimento)
    priority: str | None = None  # la più alta tra i messaggi del cliente ancora senza risposta
    waiting_since: float | None = None  # da quando il cliente aspetta risposta (None = nessuna attesa)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "status": "waiting" if self.waiting_since is not None else "answered",
            "waiting_since": self.waiting_since,
            "priority": self.priority,
            "last_message": self.messages[-1]["text"] if self.messages else "",
            "triage": self.triage,
        }


class TicketStore:
    def __init__(self, clock=time.time) -> None:
        self.clock = clock  # iniettabile, così nei test controlliamo il tempo
        self.tickets: dict[str, Ticket] = {}

    def get(self, ticket_id: str) -> Ticket | None:
        return self.tickets.get(ticket_id)

    def add_message(self, ticket_id: str, sender: str, text: str) -> Ticket:
        now = self.clock()
        ticket = self.tickets.setdefault(ticket_id, Ticket(id=ticket_id, created_at=now))
        ticket.messages.append({"from": sender, "text": text, "at": now})
        if sender == "customer":
            if ticket.waiting_since is None:
                ticket.waiting_since = now  # l'attesa parte dal primo messaggio senza risposta
        else:
            ticket.waiting_since = None  # l'operatore ha risposto...
            ticket.priority = None  # ...quindi l'attesa finisce e la priorità riparte da zero
        return ticket

    def set_triage(self, ticket_id: str, triage: dict) -> None:
        ticket = self.tickets[ticket_id]
        ticket.triage = triage
        # Il cliente sta ancora aspettando: tengo la priorità più alta vista finora, così un messaggio
        # successivo e più calmo ("ci siete?") non fa scendere un ticket urgente. Se l'operatore ha già
        # risposto nel frattempo, questo smistamento è vecchio e non conta per la priorità.
        if ticket.waiting_since is not None:
            new = triage["priority"]
            if ticket.priority is None or PRIORITY_ORDER[new] < PRIORITY_ORDER[ticket.priority]:
                ticket.priority = new

    def queue(self) -> list[dict]:
        """Prima i ticket in attesa (priorità più alta, poi chi aspetta da più tempo), poi quelli già risposti."""

        def sort_key(ticket: Ticket) -> tuple:
            if ticket.waiting_since is None:
                return (1, 0, -ticket.messages[-1]["at"])  # già risposti: i più recenti per primi
            priority = PRIORITY_ORDER[ticket.priority or "medium"]  # senza smistamento: media
            return (0, priority, ticket.waiting_since)

        return [ticket.summary() for ticket in sorted(self.tickets.values(), key=sort_key)]
