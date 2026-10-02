"""Test delle funzioni di misura usate da scripts/evaluate_banking77.py (senza scaricare nulla)."""
import numpy as np

from app.triage import CONFIDENCE_THRESHOLD
from scripts.evaluate_banking77 import add_typos, calibration_table, selective_table, wilson_interval


def test_wilson_interval_for_half_of_a_hundred():
    low, high = wilson_interval(50, 100)
    assert abs(low - 0.4038) < 0.001
    assert abs(high - 0.5962) < 0.001


def test_wilson_interval_stays_between_zero_and_one_at_the_extremes():
    low, _ = wilson_interval(0, 10)
    _, high = wilson_interval(10, 10)
    assert low > -1e-9
    assert high < 1 + 1e-9


def test_typos_with_rate_zero_change_nothing_and_are_repeatable():
    texts = ["How do I locate my card?", "Order #4821 never arrived"]
    assert add_typos(texts, 0.0, seed=1) == texts
    assert add_typos(texts, 0.3, seed=7) == add_typos(texts, 0.3, seed=7)


def test_typos_change_letters_but_never_digits_or_symbols():
    noisy = add_typos(["order #4821 arrived late"], 1.0, seed=3)[0]
    assert noisy != "order #4821 arrived late"
    assert "#4821" in noisy


def test_selective_table_counts_answered_and_correct():
    confidence = np.array([0.9, 0.8, 0.4, 0.2])
    correct = np.array([True, True, False, False])
    rows = {row["threshold"]: row for row in selective_table(confidence, correct)}

    assert rows[0.0] == {"threshold": 0.0, "answered": 1.0, "accuracy_on_answered": 0.5}
    assert rows[CONFIDENCE_THRESHOLD]["answered"] == 0.75      # 0,9 / 0,8 / 0,4 superano la soglia
    assert rows[CONFIDENCE_THRESHOLD]["accuracy_on_answered"] == round(2 / 3, 4)
    assert rows[0.9] == {"threshold": 0.9, "answered": 0.25, "accuracy_on_answered": 1.0}


def test_calibration_is_zero_when_confidence_matches_accuracy():
    confidence = np.full(10, 0.9)
    correct = np.array([True] * 9 + [False])  # 9 giuste su 10, dichiarava 90%
    rows, ece = calibration_table(confidence, correct)

    assert ece < 1e-9
    assert [(row["range"], row["count"]) for row in rows] == [("0.9-1.0", 10)]


def test_calibration_error_is_large_for_an_overconfident_model():
    confidence = np.array([0.95, 0.95, 1.0])  # anche 1,0 finisce nell'ultima fascia
    correct = np.array([False, False, False])
    rows, ece = calibration_table(confidence, correct)

    assert len(rows) == 1 and rows[0]["count"] == 3
    assert abs(ece - np.mean(confidence)) < 1e-9
