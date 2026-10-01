import pytest

from app.classifier import load_model, predict

CATEGORIES = {"shipping", "refund", "not_as_described", "account", "payment"}


@pytest.fixture(scope="module")
def model():
    return load_model()


def test_prediction_has_valid_shape(model):
    result = predict(model, "Il mio pacco non è arrivato")
    assert result["category"] in CATEGORIES
    assert 0 <= result["confidence"] <= 1


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Il mio pacco non è ancora arrivato", "shipping"),
        ("I want a refund for my order", "refund"),
        ("Non riesco ad accedere al mio account", "account"),
    ],
)
def test_obvious_messages(model, text, expected):
    assert predict(model, text)["category"] == expected
