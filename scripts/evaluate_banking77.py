"""Valuta il classificatore su dati veri e pubblici: Banking77 (PolyAI, licenza CC BY 4.0).

Perché esiste: i test del progetto (frasi sintetiche e 30 messaggi scritti a mano) sono troppo
pochi per dire quanto il modello vale davvero. Banking77 ha 13.083 messaggi reali di clienti di
una banca online, divisi in 77 categorie, con un test fisso da 3.080 messaggi che il modello
non vede mai in addestramento.

Cosa misura:
  1. accuratezza contro una baseline banale, con intervallo di confidenza;
  2. TF-IDF su caratteri (quello dell'app) contro TF-IDF su parole;
  3. robustezza ai refusi (si addestra su testo pulito, si testa su testo con errori);
  4. "risposta selettiva": se il sistema tace quando non è sicuro, quanto sale la precisione?
  5. calibrazione: quando dice "sono sicuro al 70%", ha ragione 7 volte su 10?

Uso (dalla cartella del progetto, con l'ambiente virtuale attivo):
    pip install -r requirements-eval.txt
    python -m scripts.evaluate_banking77

Il dataset viene scaricato in data/external/ (cartella ignorata da git, non si pubblica).
Il grafico finisce in docs/banking77_coverage_accuracy.png e i numeri in docs/banking77_report.json.

Dataset: Casanueva et al. (2020), "Efficient Intent Detection with Dual Sentence Encoders".
https://github.com/PolyAI-LDN/task-specific-datasets
"""
import csv
import json
import math
import random
import string
import sys
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

from app.classifier import build_pipeline
from app.triage import CONFIDENCE_THRESHOLD

BASE_URL = "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/"
DATA_DIR = Path("data/external/banking77")
CHART_PATH = Path("docs/banking77_coverage_accuracy.png")
REPORT_PATH = Path("docs/banking77_report.json")

EXPECTED = {"train.csv": 10003, "test.csv": 3080}  # righe attese: serve a accorgersi di file rovinati
TYPO_RATES = (0.02, 0.05)  # probabilità di errore per ogni lettera (circa 1 e 2 refusi per messaggio)
SEED = 42
THRESHOLDS = (0.0, 0.1, 0.2, 0.3, CONFIDENCE_THRESHOLD, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


# ---------- dati ----------

def download_dataset() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED:
        target = DATA_DIR / name
        if target.exists():
            continue
        url = BASE_URL + name
        print(f"Scarico {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                target.write_bytes(response.read())
        except OSError as error:
            sys.exit(
                f"\nDownload non riuscito ({error}).\n"
                f"Scarica i due file a mano e riprova:\n"
                f"  mkdir -p {DATA_DIR}\n"
                f"  curl -L -o {DATA_DIR}/train.csv {BASE_URL}train.csv\n"
                f"  curl -L -o {DATA_DIR}/test.csv {BASE_URL}test.csv"
            )


def read_split(name: str) -> tuple[list[str], list[str]]:
    with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != EXPECTED[name]:
        sys.exit(f"{name}: attese {EXPECTED[name]} righe, trovate {len(rows)}. "
                 f"Il file è rovinato: cancellalo da {DATA_DIR} e rilancia.")
    return [r["text"] for r in rows], [r["category"] for r in rows]


# ---------- strumenti di misura ----------

def wilson_interval(correct: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Intervallo di confidenza al 95% per una proporzione (metodo di Wilson)."""
    p = correct / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (centre - margin) / denominator, (centre + margin) / denominator


def add_typos(texts: list[str], rate: float, seed: int) -> list[str]:
    """Rovina i messaggi come farebbe una persona di fretta: lettera tolta, doppiata, scambiata o sbagliata."""
    rng = random.Random(seed)
    noisy = []
    for text in texts:
        chars, out, i = list(text), [], 0
        while i < len(chars):
            c = chars[i]
            if c.isalpha() and rng.random() < rate:
                kind = rng.choice(("delete", "double", "swap", "replace"))
                if kind == "delete":
                    pass
                elif kind == "double":
                    out += [c, c]
                elif kind == "swap" and i + 1 < len(chars) and chars[i + 1].isalpha():
                    out += [chars[i + 1], c]
                    i += 1
                else:
                    out.append(rng.choice(string.ascii_lowercase))
            else:
                out.append(c)
            i += 1
        noisy.append("".join(out))
    return noisy


def build_word_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("clf", LogisticRegression(max_iter=1000)),
    ])


def accuracy_with_interval(truth: np.ndarray, predicted: np.ndarray) -> dict:
    correct = int((truth == predicted).sum())
    low, high = wilson_interval(correct, len(truth))
    return {"accuracy": round(correct / len(truth), 4), "ci95": [round(low, 4), round(high, 4)]}


def selective_table(confidence: np.ndarray, correct: np.ndarray) -> list[dict]:
    """Per ogni soglia: quanti messaggi riceverebbero una risposta e quanti di questi sono giusti."""
    rows = []
    for threshold in THRESHOLDS:
        answered = confidence >= threshold
        rows.append({
            "threshold": threshold,
            "answered": round(float(answered.mean()), 4),
            "accuracy_on_answered": round(float(correct[answered].mean()), 4) if answered.any() else None,
        })
    return rows


def calibration_table(confidence: np.ndarray, correct: np.ndarray, bins: int = 10) -> tuple[list[dict], float]:
    """Divide i messaggi per sicurezza dichiarata e confronta con la precisione reale in ogni fascia."""
    index = np.minimum((confidence * bins).astype(int), bins - 1)
    rows, ece = [], 0.0
    for b in range(bins):
        in_bin = index == b
        if not in_bin.any():
            continue
        mean_conf = float(confidence[in_bin].mean())
        accuracy = float(correct[in_bin].mean())
        ece += in_bin.mean() * abs(accuracy - mean_conf)
        rows.append({"range": f"{b / bins:.1f}-{(b + 1) / bins:.1f}", "count": int(in_bin.sum()),
                     "mean_confidence": round(mean_conf, 4), "accuracy": round(accuracy, 4)})
    return rows, float(ece)


# ---------- grafico ----------

def draw_chart(confidence: np.ndarray, correct: np.ndarray, calibration: list[dict], ece: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    surface, ink, ink2, grid, blue = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1", "#2a78d6"
    plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "text.color": ink,
                         "axes.labelcolor": ink2, "xtick.color": ink2, "ytick.color": ink2})

    fig, (left, right) = plt.subplots(1, 2, figsize=(10.4, 4.4), dpi=200, facecolor=surface)
    for ax in (left, right):
        ax.set_facecolor(surface)
        ax.grid(True, color=grid, linewidth=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(grid)
        ax.tick_params(length=0)

    # Sinistra: ordino i messaggi dal più sicuro al meno sicuro e guardo la precisione cumulata.
    order = np.argsort(-confidence, kind="stable")
    cumulative = np.cumsum(correct[order]) / np.arange(1, len(order) + 1)
    coverage = np.arange(1, len(order) + 1) / len(order)
    keep = coverage >= 0.05  # sotto il 5% la curva dipende da pochissimi messaggi
    left.plot(coverage[keep] * 100, cumulative[keep] * 100, color=blue, linewidth=2)

    answered = confidence >= CONFIDENCE_THRESHOLD
    app_coverage = float(answered.mean() * 100)
    app_accuracy = float(correct[answered].mean() * 100)
    left.plot([app_coverage], [app_accuracy], marker="o", markersize=8, color=blue,
              markeredgecolor=surface, markeredgewidth=2, linestyle="none")
    left.annotate(f"app threshold {CONFIDENCE_THRESHOLD}:\nanswers {app_coverage:.0f}% of messages,\n"
                  f"{app_accuracy:.0f}% of those correct",
                  xy=(app_coverage, app_accuracy), xytext=(app_coverage - 6, app_accuracy - 6),
                  ha="right", va="top", fontsize=9, color=ink,
                  arrowprops={"arrowstyle": "-", "color": ink2, "linewidth": 0.8, "shrinkA": 2, "shrinkB": 6})
    left.set_xlim(0, 100)
    left.set_ylim(80, 100)
    left.set_yticks(range(80, 101, 5))
    left.set_xlabel("Messages answered by the assistant (%)")
    left.set_ylabel("Correct among answered (%)")
    left.set_title("Staying silent when unsure raises precision", loc="left", fontsize=11, color=ink)

    # Destra: diagramma di affidabilità. Sulla diagonale = "dice 70%, ha ragione il 70% delle volte".
    right.plot([0, 100], [0, 100], color=ink2, linewidth=1, linestyle=(0, (4, 3)))
    right.text(68, 56, "perfect calibration\n(dashed line)", ha="left", va="top", fontsize=9, color=ink2)
    reliable = [r for r in calibration if r["count"] >= 20]  # fasce con pochi messaggi sono rumore
    right.plot([r["mean_confidence"] * 100 for r in reliable], [r["accuracy"] * 100 for r in reliable],
               color=blue, linewidth=2, marker="o", markersize=6, markeredgecolor=surface, markeredgewidth=1.5)
    first = reliable[0]
    right.text(2.5, first["accuracy"] * 100 - 5,
               f"stated {first['mean_confidence']:.0%}:\nactually right {first['accuracy']:.0%}",
               ha="left", va="top", fontsize=9, color=ink)
    right.set_xlim(0, 100)
    right.set_ylim(0, 100)
    right.set_xlabel("Confidence stated by the model (%)")
    right.set_ylabel("Actual accuracy (%)")
    right.set_title(f"The model is underconfident (ECE {ece * 100:.0f} points)", loc="left", fontsize=11, color=ink)

    fig.text(0.01, 0.01, "Banking77 test set, 3,080 real messages, 77 categories. Model trained on 10,003 messages. "
             "Dataset: PolyAI, CC BY 4.0.", fontsize=8, color=ink2)
    fig.tight_layout(rect=(0, 0.04, 1, 1), w_pad=3)
    CHART_PATH.parent.mkdir(exist_ok=True)
    fig.savefig(CHART_PATH, facecolor=surface)
    plt.close(fig)


# ---------- programma principale ----------

def main() -> None:
    download_dataset()
    x_train, y_train = read_split("train.csv")
    x_test, y_test = read_split("test.csv")
    truth = np.array(y_test)
    print(f"Addestramento: {len(x_train)} messaggi. Test: {len(x_test)} messaggi. "
          f"Categorie: {len(set(y_train))}.")

    report: dict = {"dataset": "Banking77 (PolyAI, CC BY 4.0)", "train_size": len(x_train),
                    "test_size": len(x_test), "categories": len(set(y_train)),
                    "scikit_learn": sklearn.__version__, "seed": SEED}

    # 1. Baseline e modello dell'app
    baseline = DummyClassifier(strategy="most_frequent").fit(x_train, y_train)
    report["baseline"] = accuracy_with_interval(truth, baseline.predict(x_test))
    print(f"\nBaseline (risponde sempre la categoria più frequente): {report['baseline']['accuracy']:.1%}")

    print("Addestro il modello dell'app (TF-IDF su caratteri)... ", end="", flush=True)
    char_model = build_pipeline().fit(x_train, y_train)
    print("fatto")
    char_proba = char_model.predict_proba(x_test)
    char_pred = char_model.classes_[char_proba.argmax(axis=1)]
    report["char_tfidf"] = accuracy_with_interval(truth, char_pred)
    report["char_tfidf"]["macro_f1"] = round(float(f1_score(truth, char_pred, average="macro")), 4)
    low, high = report["char_tfidf"]["ci95"]
    print(f"Modello dell'app: accuratezza {report['char_tfidf']['accuracy']:.1%} "
          f"(intervallo al 95%: {low:.1%}-{high:.1%}), F1 macro {report['char_tfidf']['macro_f1']:.3f}")

    # 2. Caratteri contro parole, e 3. refusi
    print("Addestro la variante con TF-IDF su parole... ", end="", flush=True)
    word_model = build_word_pipeline().fit(x_train, y_train)
    print("fatto")
    noisy_sets = {rate: add_typos(x_test, rate, SEED) for rate in TYPO_RATES}
    report["typos"] = {"example_original": x_test[0], "example_noisy": noisy_sets[TYPO_RATES[-1]][0]}
    comparison = {}
    for name, model in (("char_tfidf", char_model), ("word_tfidf", word_model)):
        row = {"clean": float(accuracy_score(truth, model.predict(x_test)))}
        for rate in TYPO_RATES:
            row[f"typos_{rate:.0%}"] = float(accuracy_score(truth, model.predict(noisy_sets[rate])))
        comparison[name] = {key: round(value, 4) for key, value in row.items()}
    report["typos"]["accuracy"] = comparison
    print("\nRobustezza ai refusi (accuratezza sul test, addestrando sempre su testo pulito):")
    columns = list(comparison["char_tfidf"])
    print(f"  {'':24}" + "".join(f"{c:>12}" for c in columns))
    for name, row in comparison.items():
        label = "caratteri (app)" if name == "char_tfidf" else "parole"
        print(f"  {label:24}" + "".join(f"{row[c]:>12.1%}" for c in columns))
    print(f"  Esempio di messaggio con refusi: {report['typos']['example_noisy']!r}")

    # 4. Risposta selettiva
    confidence = char_proba.max(axis=1)
    correct = (char_pred == truth)
    table = selective_table(confidence, correct)
    report["selective_prediction"] = table
    print("\nRisposta selettiva (il sistema risponde solo se la sicurezza supera la soglia):")
    print(f"  {'soglia':>8}{'risponde a':>14}{'giuste tra le risposte':>26}")
    for row in table:
        mark = "   <- soglia dell'app" if row["threshold"] == CONFIDENCE_THRESHOLD else ""
        accuracy = f"{row['accuracy_on_answered']:.1%}" if row["accuracy_on_answered"] is not None else "-"
        print(f"  {row['threshold']:>8.2f}{row['answered']:>14.1%}{accuracy:>26}{mark}")

    wrong = ~correct
    silent_errors = int((wrong & (confidence < CONFIDENCE_THRESHOLD)).sum())
    report["errors_at_app_threshold"] = {"errors": int(wrong.sum()), "caught_by_silence": silent_errors,
                                         "answered_wrongly": int(wrong.sum()) - silent_errors}
    print(f"\nErrori totali: {int(wrong.sum())}. Alla soglia {CONFIDENCE_THRESHOLD} "
          f"{silent_errors} sarebbero stati evitati perché il sistema avrebbe taciuto; "
          f"{int(wrong.sum()) - silent_errors} sarebbero stati risposte sbagliate.")

    # 5. Calibrazione
    calibration, ece = calibration_table(confidence, correct)
    report["calibration"] = {"ece": round(ece, 4), "bins": calibration}
    print(f"\nCalibrazione (ECE = {ece:.3f}, più è vicino a 0 meglio è):")
    print(f"  {'sicurezza':>10}{'messaggi':>10}{'media dichiarata':>18}{'precisione reale':>18}")
    for row in calibration:
        print(f"  {row['range']:>10}{row['count']:>10}{row['mean_confidence']:>18.1%}{row['accuracy']:>18.1%}")

    # Errori più frequenti
    confusions = Counter((t, p) for t, p in zip(truth, char_pred) if t != p).most_common(5)
    report["top_confusions"] = [{"true": t, "predicted": p, "count": n} for (t, p), n in confusions]
    print("\nConfusioni più frequenti (vero -> previsto):")
    for (true_label, predicted_label), count in confusions:
        print(f"  {count:>3}  {true_label} -> {predicted_label}")

    draw_chart(confidence, correct, calibration, ece)
    REPORT_PATH.parent.mkdir(exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nGrafico salvato in {CHART_PATH}. Numeri salvati in {REPORT_PATH}.")


if __name__ == "__main__":
    main()
