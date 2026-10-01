"""Addestra il classificatore dei ticket e ne misura la qualità.

Uso (dalla cartella del progetto):  python -m scripts.train
"""
import csv
import json

import joblib
from sklearn.dummy import DummyClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split

from app.classifier import MODEL_PATH, build_pipeline


def read_csv(path: str) -> tuple[list[str], list[str]]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r["text"] for r in rows], [r["category"] for r in rows]


def report(name: str, model, texts: list[str], labels: list[str]) -> float:
    predicted = model.predict(texts)
    accuracy = accuracy_score(labels, predicted)
    print(f"\n=== {name} ({len(texts)} messaggi) ===")
    print(f"Accuracy: {accuracy:.3f}")
    print(classification_report(labels, predicted, digits=3, zero_division=0))
    classes = sorted(set(labels))
    print("Matrice di confusione (righe = vero, colonne = previsto):")
    print("classi:", classes)
    print(confusion_matrix(labels, predicted, labels=classes))
    return accuracy


def main() -> None:
    texts, labels = read_csv("data/tickets.csv")
    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, stratify=labels, random_state=42
    )

    baseline = DummyClassifier(strategy="most_frequent").fit(x_train, y_train)
    baseline_accuracy = accuracy_score(y_test, baseline.predict(x_test))
    print(f"Baseline (risponde sempre la categoria più frequente): accuracy {baseline_accuracy:.3f}")

    model = build_pipeline().fit(x_train, y_train)
    synthetic_accuracy = report("Test sintetico (stessi modelli di frase dell'addestramento)", model, x_test, y_test)

    hand_texts, hand_labels = read_csv("data/handwritten_test.csv")
    hand_accuracy = report("Test scritto a mano (frasi nuove)", model, hand_texts, hand_labels)

    print("\nMessaggi scritti a mano sbagliati dal modello:")
    for text, expected in zip(hand_texts, hand_labels):
        guess = model.predict([text])[0]
        if guess != expected:
            confidence = model.predict_proba([text])[0].max()
            print(f"- {text!r}\n    vero: {expected} | previsto: {guess} (sicurezza {confidence:.2f})")

    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    metrics = {
        "baseline_accuracy": round(baseline_accuracy, 3),
        "synthetic_test_accuracy": round(synthetic_accuracy, 3),
        "handwritten_test_accuracy": round(hand_accuracy, 3),
    }
    with open(MODEL_PATH.parent / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nModello salvato in {MODEL_PATH}. Metriche: {metrics}")


if __name__ == "__main__":
    main()
