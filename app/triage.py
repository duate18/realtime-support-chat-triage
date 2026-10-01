"""Logica di smistamento: categoria, priorità e risposta suggerita per un messaggio."""
import json
import re
from pathlib import Path

from app.classifier import predict

FAQ_PATH = Path("data/faq.json")

# Sotto questa sicurezza il sistema non suggerisce nulla e lascia decidere a una persona.
# Valore scelto guardando le frasi scritte a mano: a 0,35 il modello risponde da solo a circa
# 3 messaggi su 4 e quasi sempre giusto (campione piccolo: 30 messaggi). Da rivalutare con dati veri.
CONFIDENCE_THRESHOLD = 0.35

# Regole di priorità volutamente semplici e leggibili (illustrative, non prese da dati reali).
BASE_PRIORITY = {"payment": 2, "refund": 2, "account": 2, "shipping": 1, "not_as_described": 1}
URGENT_WORDS = ("due volte", "twice", "bloccato", "blocked", "truffa", "scam", "frode", "fraud")

# Parole molto comuni per riconoscere la lingua. Parole ambigue (i, a, in) sono escluse di proposito.
ITALIAN_WORDS = {"il", "la", "le", "lo", "un", "una", "non", "mi", "che", "di", "per", "con",
                 "ho", "sono", "è", "del", "dei", "ma", "come", "dove", "mio", "mia"}
ENGLISH_WORDS = {"the", "my", "is", "to", "and", "not", "for", "have", "it", "you", "of",
                 "was", "with", "but", "how", "where", "still", "me"}


def load_faq(path: Path = FAQ_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def detect_language(text: str) -> str:
    """Restituisce 'it' o 'en' contando parole comuni. Semplice: sui messaggi molto corti può sbagliare."""
    words = re.findall(r"[\w']+", text.lower())
    italian = sum(word in ITALIAN_WORDS for word in words)
    english = sum(word in ENGLISH_WORDS for word in words)
    return "en" if english > italian else "it"


def priority_label(score: int) -> str:
    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    return "low"


def triage(model, faq: dict, text: str) -> dict:
    """Analizza un messaggio e dice cosa fare: categoria, priorità, risposta suggerita (se il modello è sicuro)."""
    prediction = predict(model, text)
    category, confidence = prediction["category"], prediction["confidence"]
    needs_human = confidence < CONFIDENCE_THRESHOLD
    language = detect_language(text)
    urgent = any(word in text.lower() for word in URGENT_WORDS)

    base = 2 if needs_human else BASE_PRIORITY[category]  # categoria incerta: priorità media
    score = base + (2 if urgent else 0)

    return {
        "category": category,
        "confidence": confidence,
        "language": language,
        "priority": priority_label(score),
        "needs_human": needs_human,
        "suggestion": None if needs_human else faq[category][language],
    }
