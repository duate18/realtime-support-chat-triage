"""Archivio in memoria dei ticket: messaggi, ultimo smistamento e coda ordinata per l'operatore."""
import time
from dataclasses import dataclass, field

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Ticket:
    id: str
    created_at: float
    messages: list[dict] = field(default_factory=list)
    triage: dict | None = None  # ultimo smistamento di un messaggio del cliente
    waiting_since: float | None = None  # da quando il cliente aspetta risposta (None = nessuna attesa)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "status": "waiting" if self.waiting_since is not None else "answered",
            "waiting_since": self.waiting_since,
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
            ticket.waiting_since = None  # l'operatore ha risposto
        return ticket

    def set_triage(self, ticket_id: str, triage: dict) -> None:
        self.tickets[ticket_id].triage = triage

    def queue(self) -> list[dict]:
        """Prima i ticket in attesa (priorità più alta, poi chi aspetta da più tempo), poi quelli già risposti."""

        def sort_key(ticket: Ticket) -> tuple:
            if ticket.waiting_since is None:
                return (1, 0, -ticket.messages[-1]["at"])  # già risposti: i più recenti per primi
            priority = PRIORITY_ORDER[ticket.triage["priority"]] if ticket.triage else PRIORITY_ORDER["medium"]
            return (0, priority, ticket.waiting_since)

        return [ticket.summary() for ticket in sorted(self.tickets.values(), key=sort_key)]
