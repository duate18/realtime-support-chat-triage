import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import MAX_MESSAGE_LENGTH, RATE_LIMIT_MESSAGES, app

LOW_PRIORITY_TEXT = "Parcel still not here, tracking says nothing since last week"  # spedizione, nessuna urgenza
URGENT_TEXT = "Mi hanno addebitato due volte l'ordine #12345, chiedo il rimborso."  # pagamento doppio


@pytest.fixture
def client():
    # "with" è fondamentale: tiene un solo event loop per tutta la durata del test,
    # altrimenti ogni websocket ne avrebbe uno suo e non potrebbero parlarsi.
    with TestClient(app) as test_client:
        yield test_client


def find(tickets, ticket_id):
    return next(t for t in tickets if t["id"] == ticket_id)


# Ogni test usa ticket con id propri: l'archivio è condiviso e non lo svuotiamo tra un test e l'altro.


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_message_reaches_customer_and_agent(client):
    expected = {"type": "message", "from": "customer", "text": "Il mio pacco non è arrivato"}
    with client.websocket_connect("/ws/t1?role=customer") as customer, \
            client.websocket_connect("/ws/t1?role=agent") as agent:
        customer.send_text(expected["text"])
        assert customer.receive_json() == expected
        assert agent.receive_json() == expected


def test_agent_gets_a_suggestion_but_customer_does_not(client):
    with client.websocket_connect("/ws/t2?role=customer") as customer, \
            client.websocket_connect("/ws/t2?role=agent") as agent:
        customer.send_text(LOW_PRIORITY_TEXT)

        assert agent.receive_json()["type"] == "message"  # prima il messaggio del cliente
        suggestion = agent.receive_json()  # poi il suggerimento, solo per l'operatore
        assert suggestion["type"] == "suggestion"
        assert suggestion["category"] == "shipping"
        assert suggestion["suggestion"] is not None

        assert customer.receive_json()["type"] == "message"  # il cliente vede solo il proprio messaggio
        agent.send_text("Controllo subito")
        # Se il cliente avesse ricevuto il suggerimento, arriverebbe prima di questo messaggio.
        assert customer.receive_json() == {"type": "message", "from": "agent", "text": "Controllo subito"}


def test_invalid_role_is_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/t1?role=hacker"):
            pass


def test_pages_are_served(client):
    customer_page = client.get("/")
    assert customer_page.status_code == 200
    assert "text/html" in customer_page.headers["content-type"]
    assert "Support chat" in customer_page.text

    agent_page = client.get("/agent")
    assert agent_page.status_code == 200
    assert "Agent console" in agent_page.text


def test_unknown_ticket_history_is_404(client):
    assert client.get("/api/tickets/does-not-exist").status_code == 404


def test_history_keeps_both_sides_of_the_conversation(client):
    with client.websocket_connect("/ws/h1?role=customer") as customer, \
            client.websocket_connect("/ws/h1?role=agent") as agent:
        customer.send_text(LOW_PRIORITY_TEXT)
        agent.receive_json()  # messaggio del cliente
        agent.receive_json()  # suggerimento (dopo questo il ticket è già smistato)
        agent.send_text("Controllo subito")
        customer.receive_json()  # eco del proprio messaggio
        customer.receive_json()  # risposta dell'operatore

    history = client.get("/api/tickets/h1").json()
    assert history["id"] == "h1"
    assert [(m["from"], m["text"]) for m in history["messages"]] == [
        ("customer", LOW_PRIORITY_TEXT),
        ("agent", "Controllo subito"),
    ]


def test_console_gets_a_snapshot_when_it_connects(client):
    with client.websocket_connect("/ws-agents") as console:
        snapshot = console.receive_json()
    assert snapshot["type"] == "queue"
    assert isinstance(snapshot["tickets"], list)


def test_console_sees_the_urgent_ticket_before_the_calm_one(client):
    with client.websocket_connect("/ws-agents") as console:
        console.receive_json()  # istantanea iniziale

        with client.websocket_connect("/ws/q-low?role=customer") as calm, \
                client.websocket_connect("/ws/q-high?role=customer") as urgent:
            calm.send_text(LOW_PRIORITY_TEXT)
            console.receive_json()  # coda aggiornata dopo il primo messaggio
            urgent.send_text(URGENT_TEXT)
            queue = console.receive_json()

    assert queue["type"] == "queue"
    ours = [t for t in queue["tickets"] if t["id"] in {"q-low", "q-high"}]
    assert [t["id"] for t in ours] == ["q-high", "q-low"]  # arrivato dopo, ma più urgente
    assert find(queue["tickets"], "q-high")["triage"]["priority"] == "high"
    assert find(queue["tickets"], "q-low")["triage"]["priority"] == "low"


def test_agent_reply_marks_the_ticket_as_answered(client):
    with client.websocket_connect("/ws-agents") as console:
        console.receive_json()  # istantanea iniziale

        with client.websocket_connect("/ws/q-reply?role=customer") as customer, \
                client.websocket_connect("/ws/q-reply?role=agent") as agent:
            customer.send_text(LOW_PRIORITY_TEXT)
            waiting = console.receive_json()
            assert find(waiting["tickets"], "q-reply")["status"] == "waiting"

            agent.send_text("Controllo subito")
            answered = console.receive_json()

    assert find(answered["tickets"], "q-reply")["status"] == "answered"


def test_follow_up_does_not_lower_the_priority_of_an_urgent_ticket(client):
    with client.websocket_connect("/ws-agents") as console:
        console.receive_json()  # istantanea iniziale

        with client.websocket_connect("/ws/q-followup?role=customer") as customer:
            customer.send_text(URGENT_TEXT)
            console.receive_json()
            customer.send_text("Ciao, c'è qualcuno?")
            queue = console.receive_json()

    ticket = find(queue["tickets"], "q-followup")
    assert ticket["triage"]["priority"] != "high"  # il seguito, da solo, non è urgente...
    assert ticket["priority"] == "high"  # ...ma il ticket resta urgente


def test_priority_starts_over_after_the_agent_replies(client):
    with client.websocket_connect("/ws-agents") as console:
        console.receive_json()  # istantanea iniziale

        with client.websocket_connect("/ws/q-reset?role=customer") as customer, \
                client.websocket_connect("/ws/q-reset?role=agent") as agent:
            customer.send_text(URGENT_TEXT)
            assert find(console.receive_json()["tickets"], "q-reset")["priority"] == "high"

            agent.send_text("Ci penso io")
            console.receive_json()

            customer.send_text(LOW_PRIORITY_TEXT)
            queue = console.receive_json()

    assert find(queue["tickets"], "q-reset")["priority"] == "low"


def test_message_that_is_too_long_is_rejected_and_not_saved(client):
    with client.websocket_connect("/ws/long1?role=customer") as customer:
        customer.send_text("a" * (MAX_MESSAGE_LENGTH + 1))
        assert customer.receive_json() == {
            "type": "error",
            "detail": f"Message too long (max {MAX_MESSAGE_LENGTH} characters).",
        }

    assert client.get("/api/tickets/long1").status_code == 404  # nessun ticket creato


def test_message_at_the_limit_is_accepted(client):
    text = "a" * MAX_MESSAGE_LENGTH
    with client.websocket_connect("/ws/long2?role=agent") as agent:
        agent.send_text(text)
        assert agent.receive_json() == {"type": "message", "from": "agent", "text": text}


def test_empty_messages_are_ignored(client):
    with client.websocket_connect("/ws/empty1?role=agent") as agent:
        agent.send_text("   ")
        agent.send_text("ok")
        assert agent.receive_json() == {"type": "message", "from": "agent", "text": "ok"}  # il vuoto non è arrivato


def test_too_many_messages_are_rejected(client):
    # Usiamo il ruolo "agent": non fa partire lo smistamento, quindi il test è veloce.
    with client.websocket_connect("/ws/rate1?role=agent") as agent:
        for i in range(RATE_LIMIT_MESSAGES):
            agent.send_text(f"messaggio {i}")
            assert agent.receive_json()["type"] == "message"

        agent.send_text("uno di troppo")
        assert agent.receive_json() == {"type": "error", "detail": "Too many messages, please slow down."}

    history = client.get("/api/tickets/rate1").json()
    assert len(history["messages"]) == RATE_LIMIT_MESSAGES  # quello rifiutato non è stato salvato
