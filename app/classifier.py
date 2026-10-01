from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

MODEL_PATH = Path("models/classifier.joblib")


def build_pipeline() -> Pipeline:
    """TF-IDF su sequenze di caratteri + regressione logistica.

    Le sequenze di 2-5 caratteri reggono bene refusi e due lingue insieme,
    senza bisogno di rilevare la lingua del messaggio.
    """
    return Pipeline([
        ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
        ("clf", LogisticRegression(max_iter=1000)),
    ])


def load_model(path: Path = MODEL_PATH) -> Pipeline:
    if not path.exists():
        raise FileNotFoundError(f"Modello non trovato in {path}. Esegui prima: python -m scripts.train")
    return joblib.load(path)


def predict(model: Pipeline, text: str) -> dict:
    """Restituisce la categoria più probabile e quanto il modello è sicuro (0-1)."""
    probabilities = model.predict_proba([text])[0]
    best = probabilities.argmax()
    return {"category": str(model.classes_[best]), "confidence": round(float(probabilities[best]), 3)}
