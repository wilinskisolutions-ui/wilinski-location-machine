"""Turn questionnaire answers into weights.

The trade-off block is the load-bearing part. Rather than asking how much someone values
clean air — which nobody can answer — it shows pairs of real places and records which they
pick. Fitting a utility over those choices recovers the weights from behaviour instead of
from self-report, which is why it works on universally-directional indicators where asking
the question directly would be absurd.

Everything here is numpy and the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class ChoiceFit:
    weights: dict[str, float]           # indicator -> importance, non-negative, sums to 1
    coefficients: dict[str, float]      # signed, before taking magnitude
    accuracy: float                     # IN-SAMPLE reproduction — a fit quality diagnostic,
                                         # never the informativeness gate. See is_informative.
    n_choices: int
    contradictions: list[str] = field(default_factory=list)
    cv_accuracy: float | None = None    # leave-one-out; the actual informativeness signal

    @property
    def is_informative(self) -> bool:
        """Whether the answers actually carry signal.

        Gated on leave-one-out cross-validated accuracy, never on `accuracy` (in-sample).
        The trade-off block has ~15 attributes over ~24-25 real choices — enough dimensions
        relative to data that an unregularized *or* lightly regularized fit can reproduce
        its own training labels almost regardless of whether the choices were coherent.
        Measured directly: pure random answers on the real bank design produced in-sample
        accuracy averaging 0.83-0.95 across trials, comfortably clearing the old 0.65
        threshold every time. A threshold on the wrong metric is not a safety check.

        Leave-one-out accuracy — refit with one choice held out, predict it, repeat — is
        the standard remedy and cheap at this sample size. It cannot be inflated by the
        model's own capacity the way in-sample accuracy can, because each held-out choice
        was never used to fit the model being tested against it.

        **The threshold is calibrated against the real design's null distribution, not
        guessed.** At ~24-28 choices, LOO accuracy is itself a noisy estimator — 60 trials
        of pure random answers on the actual bank produced a mean of 0.50 but a standard
        deviation of 0.12, with the 95th percentile reaching 0.68. A first attempt at 0.6
        let three of six random trials through as "informative" in testing. 0.68 keeps the
        false-positive rate against pure noise near 5%.

        That threshold rejects roughly half of genuinely consistent respondents too — 60
        trials of a synthetic respondent with a few dominant, realistically-noisy
        preferences had a median LOO accuracy of 0.68, right at the cutoff. That asymmetry
        is deliberate rather than a compromise to fix later: the two failure modes are not
        equally costly. A false negative falls back to the household's own directly stated
        allocation, which is a fully legitimate, already-supported way to get weights. A
        false positive corrupts the ranking with revealed weights that only look like
        findings. Erring toward the safe side costs a warning; erring the other way cost
        the first real household an amenity indicator with the wrong sign at second-highest
        weight, presented as their answer.
        """
        if self.cv_accuracy is None:
            return self.n_choices >= 8 and self.accuracy >= 0.65
        return self.n_choices >= 8 and self.cv_accuracy >= 0.68


def _standardize(matrix: np.ndarray) -> np.ndarray:
    spread = matrix.std(axis=0)
    spread[spread == 0] = 1.0
    return (matrix - matrix.mean(axis=0)) / spread


def _gradient_ascent(
    x: np.ndarray, y: np.ndarray, *, iterations: int, learning_rate: float, l2: float
) -> np.ndarray:
    beta = np.zeros(x.shape[1])
    for _ in range(iterations):
        p = 1.0 / (1.0 + np.exp(-np.clip(x @ beta, -30, 30)))
        beta += learning_rate * ((x.T @ (y - p)) / len(y) - l2 * beta)
    return beta


def _leave_one_out_accuracy(
    x_raw: np.ndarray, y: np.ndarray, *, iterations: int, learning_rate: float, l2: float
) -> float | None:
    """Refit with each choice held out in turn and predict it. The only honest way to ask
    "did these answers carry signal" when attributes and choices are close in number,
    because in-sample accuracy can be high by construction regardless of the answer."""
    n = len(y)
    if n < 8:
        return None
    correct = 0
    for holdout in range(n):
        keep = np.arange(n) != holdout
        x_train = _standardize(x_raw[keep])
        beta = _gradient_ascent(
            x_train, y[keep], iterations=iterations, learning_rate=learning_rate, l2=l2
        )
        # The held-out row standardized against the training fold's own mean/spread — using
        # the full-sample statistics would leak the held-out point into its own prediction.
        spread = x_raw[keep].std(axis=0)
        spread[spread == 0] = 1.0
        x_test = (x_raw[holdout] - x_raw[keep].mean(axis=0)) / spread
        predicted = float(x_test @ beta > 0)
        correct += int(predicted == y[holdout])
    return correct / n


def fit_choices(
    tasks: list[dict],
    answers: dict[str, object],
    *,
    directions: dict[str, str],
    iterations: int = 4000,
    learning_rate: float = 0.12,
    l2: float = 0.3,
) -> ChoiceFit:
    """Fit a linear utility over attribute differences by logistic regression.

    `directions` maps indicator -> curve, so a lower_better attribute is sign-flipped and
    every coefficient ends up oriented "more of this is better".

    **Regularized, and not optionally.** The trade-off block has ~15 design attributes and
    produces ~24-25 real choices — p/n near 0.6, well inside the regime where an
    unregularized fit can perfectly separate the training labels by construction rather than
    by finding a genuine preference. It did, on the first real household to answer: accuracy
    came out at exactly 1.00, and the second-highest weight belonged to an indicator whose
    fitted coefficient had the *wrong sign* — the choices looked like a preference against
    more arts and recreation venues, which almost certainly reflects that attribute's
    correlation with cost in the specific pairs shown rather than a real aversion to culture.
    A perfect-looking fit is the symptom, not the reassurance.

    Adding an L2 penalty and testing it against that respondent's real answers: accuracy
    fell to a believable 0.88 (21 of 24), the wrong-signed indicator's weight collapsed from
    second place to a minor factor, and stated climate preferences — reported directly by
    the household before any of this was built — surfaced into the top weights for the
    first time instead of being buried under the collinear artifact. `l2=0.3` was the
    smallest penalty that reached that plateau without flattening every coefficient toward
    uniform importance (tested from 0.05 to 3.0). `TestEqualPreferences` uses 300 synthetic
    choices, p/n far below the danger zone, so this barely perturbs a fit that already has
    enough data to be trusted.
    """
    rows, labels, attributes = [], [], sorted(
        {a["indicator"] for t in tasks for a in t.get("attributes", [])}
    )
    index = {name: i for i, name in enumerate(attributes)}
    seen: dict[str, str] = {}
    contradictions: list[str] = []

    for task in tasks:
        answer = answers.get(task["id"])
        if answer not in ("A", "B"):
            continue

        # A repeated task that flips is a contradiction, not data to average away.
        origin = task.get("repeat_of")
        if origin and origin in seen and seen[origin] != answer:
            contradictions.append(origin)
        seen[task["id"]] = answer
        if origin:
            continue  # the repeat exists to check consistency, not to double-count

        row = np.zeros(len(attributes))
        for attr in task["attributes"]:
            a, b = attr.get("a_raw"), attr.get("b_raw")
            if a is None or b is None:
                continue
            diff = a - b
            if directions.get(attr["indicator"]) == "lower_better":
                diff = -diff  # orient every coefficient as "more is better"
            row[index[attr["indicator"]]] = diff
        rows.append(row)
        labels.append(1.0 if answer == "A" else 0.0)

    if len(rows) < 4:
        return ChoiceFit({}, {}, 0.0, len(rows), contradictions)

    x_raw = np.array(rows)
    y = np.array(labels)
    x = _standardize(x_raw)
    beta = _gradient_ascent(x, y, iterations=iterations, learning_rate=learning_rate, l2=l2)

    predicted = (x @ beta > 0).astype(float)
    accuracy = float((predicted == y).mean())
    cv_accuracy = _leave_one_out_accuracy(
        x_raw, y, iterations=iterations, learning_rate=learning_rate, l2=l2
    )

    magnitude = np.abs(beta)
    total = magnitude.sum()
    weights = (
        {name: float(magnitude[i] / total) for name, i in index.items()} if total > 0 else {}
    )
    return ChoiceFit(
        weights=weights,
        coefficients={name: float(beta[i]) for name, i in index.items()},
        accuracy=accuracy,
        n_choices=len(rows),
        contradictions=contradictions,
        cv_accuracy=cv_accuracy,
    )


def domain_weights_from_choices(fit: ChoiceFit, domain_of: dict[str, str]) -> dict[str, float]:
    """Roll indicator importances up to domains, normalised to 100.

    Uses the **mean** of a domain's indicator weights, not the sum.

    Summing made domain weight depend on how many attributes that domain happened to
    contribute to the choice set. A synthetic respondent who valued every attribute exactly
    equally came out with climate at 30.8 and healthcare at 7.8 — a 4x spread produced
    entirely by climate having four attributes and healthcare one. That measured the design
    of the questionnaire rather than anyone's preferences.

    `tests/test_end_to_end.py::TestEqualPreferences` is the regression guard.
    """
    grouped: dict[str, list[float]] = {}
    for indicator, weight in fit.weights.items():
        domain = domain_of.get(indicator)
        if domain:
            grouped.setdefault(domain, []).append(weight)

    means = {d: sum(ws) / len(ws) for d, ws in grouped.items()}
    grand = sum(means.values())
    return {d: round(v / grand * 100, 2) for d, v in means.items()} if grand else {}


def blend(
    stated: dict[str, float],
    revealed: dict[str, float],
    *,
    revealed_share: float = 0.65,
    data_less: set[str] | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Combine stated and revealed weights without silently shrinking either.

    The naive blend punished any domain absent from the trade-off block: its revealed weight
    was 0, so blending cut it to 35% of what the household actually asked for. Five of
    eleven domains were in that position, which meant the instrument structurally could not
    hear them on schools, jobs or community.

    Domains present in both are blended. Domains the trade-offs never covered keep their
    stated weight, and everything is renormalised together afterwards.
    """
    covered = set(revealed)
    combined: dict[str, float] = {}
    for domain in set(stated) | covered:
        if domain in covered:
            combined[domain] = (
                revealed_share * revealed.get(domain, 0.0)
                + (1 - revealed_share) * stated.get(domain, 0.0)
            )
        else:
            combined[domain] = stated.get(domain, 0.0)

    notes = []
    uncovered = sorted(set(stated) - covered - (data_less or set()))
    if uncovered:
        notes.append(
            "weighted from the stated allocation alone (no trade-off attributes): "
            + ", ".join(uncovered)
        )
    if data_less:
        notes.append(
            "weighted but CANNOT AFFECT THE RANKING — no data for: "
            + ", ".join(sorted(data_less))
        )
    return normalize_budget(combined), notes


def normalize_budget(allocation: dict[str, float], total: float = 100.0) -> dict[str, float]:
    grand = sum(allocation.values())
    if grand <= 0:
        return {}
    return {k: round(v / grand * total, 2) for k, v in allocation.items()}


def compare(
    budget: dict[str, float], revealed: dict[str, float], *, threshold: float = 10.0
) -> list[str]:
    """Where stated priorities and revealed choices disagree.

    Both measure the same thing by different routes. A large gap usually means the household
    *says* one thing matters and *chooses* as though another does — which is exactly the
    kind of thing worth knowing before buying a house, so it is reported rather than
    quietly averaged.
    """
    notes = []
    for domain in sorted(set(budget) | set(revealed)):
        stated, chosen = budget.get(domain, 0.0), revealed.get(domain, 0.0)
        if abs(stated - chosen) >= threshold:
            direction = "more" if chosen > stated else "less"
            notes.append(
                f"{domain}: allocated {stated:.0f} points but chose as if it mattered "
                f"{direction} ({chosen:.0f})"
            )
    return notes
