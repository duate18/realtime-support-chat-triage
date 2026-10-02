from app.tickets import TicketStore


class FakeClock:
    """Orologio finto: nei test decidiamo noi quanto tempo passa."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_store():
    clock = FakeClock()
    return TicketStore(clock=clock), clock


def test_unknown_ticket_is_none():
    store, _ = make_store()
    assert store.get("nope") is None


def test_messages_are_saved_in_order():
    store, clock = make_store()
    store.add_message("a", "customer", "Ciao")
    clock.advance(5)
    store.add_message("a", "agent", "Buongiorno")

    messages = store.get("a").messages
    assert [(m["from"], m["text"]) for m in messages] == [("customer", "Ciao"), ("agent", "Buongiorno")]
    assert messages[1]["at"] == 1005.0


def test_waiting_starts_with_the_first_unanswered_message_and_does_not_reset():
    store, clock = make_store()
    store.add_message("a", "customer", "Primo")
    clock.advance(30)
    store.add_message("a", "customer", "Secondo")  # il cliente scrive ancora: aspetta dal primo messaggio

    assert store.get("a").waiting_since == 1000.0


def test_agent_reply_ends_the_wait_and_a_new_message_restarts_it():
    store, clock = make_store()
    store.add_message("a", "customer", "Primo")
    clock.advance(10)
    store.add_message("a", "agent", "Risposta")
    assert store.get("a").waiting_since is None

    clock.advance(10)
    store.add_message("a", "customer", "Un'altra domanda")
    assert store.get("a").waiting_since == 1020.0


def test_queue_puts_high_priority_first_then_the_longest_wait():
    store, clock = make_store()
    for ticket_id, priority in [("low", "low"), ("high", "high"), ("medium-old", "medium"), ("medium-new", "medium")]:
        store.add_message(ticket_id, "customer", "...")
        store.set_triage(ticket_id, {"priority": priority})
        clock.advance(10)

    assert [t["id"] for t in store.queue()] == ["high", "medium-old", "medium-new", "low"]


def test_answered_tickets_go_last_most_recent_first():
    store, clock = make_store()
    store.add_message("old", "customer", "...")
    store.set_triage("old", {"priority": "high"})
    store.add_message("old", "agent", "fatto")
    clock.advance(10)
    store.add_message("recent", "customer", "...")
    store.set_triage("recent", {"priority": "low"})
    store.add_message("recent", "agent", "fatto")
    clock.advance(10)
    store.add_message("waiting", "customer", "...")
    store.set_triage("waiting", {"priority": "low"})

    queue = store.queue()
    assert [t["id"] for t in queue] == ["waiting", "recent", "old"]
    assert [t["status"] for t in queue] == ["waiting", "answered", "answered"]


def test_ticket_without_triage_counts_as_medium():
    store, clock = make_store()
    store.add_message("untriaged", "customer", "...")
    clock.advance(1)
    store.add_message("low", "customer", "...")
    store.set_triage("low", {"priority": "low"})
    store.add_message("high", "customer", "...")
    store.set_triage("high", {"priority": "high"})

    assert [t["id"] for t in store.queue()] == ["high", "untriaged", "low"]


def test_summary_has_what_the_console_needs():
    store, _ = make_store()
    store.add_message("a", "customer", "Il mio pacco non è arrivato")
    store.set_triage("a", {"priority": "low", "category": "shipping"})

    assert store.queue() == [{
        "id": "a",
        "status": "waiting",
        "waiting_since": 1000.0,
        "priority": "low",
        "last_message": "Il mio pacco non è arrivato",
        "triage": {"priority": "low", "category": "shipping"},
    }]


def test_priority_keeps_the_highest_while_the_customer_waits():
    store, clock = make_store()
    store.add_message("a", "customer", "Mi hanno addebitato due volte!")
    store.set_triage("a", {"priority": "high"})
    clock.advance(5)
    store.add_message("a", "customer", "Ci siete?")
    store.set_triage("a", {"priority": "medium"})  # il seguito è più calmo, ma il ticket resta urgente

    ticket = store.get("a")
    assert ticket.priority == "high"
    assert ticket.triage == {"priority": "medium"}  # il suggerimento riguarda l'ultimo messaggio


def test_priority_can_rise_with_a_later_message():
    store, _ = make_store()
    store.add_message("a", "customer", "Il mio pacco non è arrivato")
    store.set_triage("a", {"priority": "low"})
    store.add_message("a", "customer", "Mi hanno truffato")
    store.set_triage("a", {"priority": "high"})

    assert store.get("a").priority == "high"


def test_agent_reply_resets_the_priority():
    store, clock = make_store()
    store.add_message("a", "customer", "Urgente!")
    store.set_triage("a", {"priority": "high"})
    store.add_message("a", "agent", "Ci penso io")
    assert store.get("a").priority is None

    clock.advance(10)
    store.add_message("a", "customer", "Un'altra domanda, nessuna fretta")
    store.set_triage("a", {"priority": "low"})
    assert store.get("a").priority == "low"  # non si porta dietro l'urgenza del giro precedente


def test_a_late_triage_does_not_change_the_priority_of_an_answered_ticket():
    store, _ = make_store()
    store.add_message("a", "customer", "Urgente!")
    store.add_message("a", "agent", "Risposto prima che lo smistamento finisse")
    store.set_triage("a", {"priority": "high"})  # arriva in ritardo

    assert store.get("a").priority is None
    assert store.queue()[0]["status"] == "answered"


def test_queue_orders_by_the_highest_priority_not_the_latest():
    store, clock = make_store()
    store.add_message("urgent-then-calm", "customer", "Urgente!")
    store.set_triage("urgent-then-calm", {"priority": "high"})
    clock.advance(10)
    store.add_message("urgent-then-calm", "customer", "Ci siete?")
    store.set_triage("urgent-then-calm", {"priority": "low"})
    store.add_message("medium", "customer", "Una domanda")
    store.set_triage("medium", {"priority": "medium"})

    assert [t["id"] for t in store.queue()] == ["urgent-then-calm", "medium"]
