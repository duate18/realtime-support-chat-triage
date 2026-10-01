import pytest

from app.classifier import load_model
from app.triage import detect_language, load_faq, triage


@pytest.fixture(scope="module")
def model():
    return load_model()


@pytest.fixture(scope="module")
def faq():
    return load_faq()


def test_clear_message_gets_a_suggestion_in_its_language(model, faq):
    result = triage(model, faq, "Parcel still not here, tracking says nothing since last week")
    assert result["category"] == "shipping"
    assert result["language"] == "en"
    assert result["needs_human"] is False
    assert result["suggestion"] == faq["shipping"]["en"]


def test_uncertain_message_goes_to_a_person(model, faq):
    result = triage(model, faq, "I can't sign in anymore, the app keeps logging me out")
    assert result["needs_human"] is True
    assert result["suggestion"] is None


def test_urgent_words_raise_the_priority(model, faq):
    normal = triage(model, faq, "Voglio un rimborso per l'ordine #12345.")
    urgent = triage(model, faq, "Mi hanno addebitato due volte l'ordine #12345, chiedo il rimborso.")
    assert normal["priority"] == "medium"
    assert urgent["priority"] == "high"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Il mio pacco non è arrivato", "it"),
        ("My parcel has not arrived", "en"),
    ],
)
def test_language_detection(text, expected):
    assert detect_language(text) == expected
