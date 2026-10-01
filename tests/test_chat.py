import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_message_reaches_customer_and_agent():
    expected = {"from": "customer", "text": "Il mio pacco non è arrivato"}
    with client.websocket_connect("/ws/t1?role=customer") as customer, \
            client.websocket_connect("/ws/t1?role=agent") as agent:
        customer.send_text(expected["text"])
        assert customer.receive_json() == expected
        assert agent.receive_json() == expected


def test_invalid_role_is_rejected():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/t1?role=hacker"):
            pass
