import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


@pytest.fixture
def client():
    # "with" fa girare tutte le connessioni nello stesso ciclo di eventi, come in un server vero.
    with TestClient(app) as test_client:
        yield test_client


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
        customer.send_text("Parcel still not here, tracking says nothing since last week")

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
