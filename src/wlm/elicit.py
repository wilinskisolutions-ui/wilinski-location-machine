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
    accuracy: float                     # share of choices the fitted model reproduces
    n_choices: int
    contradictions: list[str] = field(default_factory=list)

    @property
    def is_informative(self) -> bool:
        """Whether the answers actually carry signal.

        Near-chance accuracy means the choices were effectively random — fatigue, or pairs
        that felt equally good. The weights must then be reported as noise rather than
        presented as findings.
        """
        return self.n_choices >= 8 and self.accuracy >= 0.65


def _standardize(matrix: np.ndarray) -> np.ndarray:
    spread = matrix.std(axis=0)
    spread[spread == 0] = 1.0
    return (matrix - matrix.mean(axis=0)) / spread


def fit_choices(
    tasks: list[dict],
    answers: dict[str, object],
    *,
    directions: dict[str, str],
    iterations: int = 4000,
    learning_rate: float = 0.12,
) -> ChoiceFit:
    """Fit a linear utility over attribute differences by logistic regression.

    `directions` maps indicator -> curve, so a lower_better attribute is sign-flipped and
    every coefficient ends up oriented "more of this is better".
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

    x = _standardize(np.array(rows))
    y = np.array(labels)
    beta = np.zeros(x.shape[1])

    for _ in range(iterations):
        p = 1.0 / (1.0 + np.exp(-np.clip(x @ beta, -30, 30)))
        beta += learning_rate * (x.T @ (y - p)) / len(y)

    predicted = (x @ beta > 0).astype(float)
    accuracy = float((predicted == y).mean())

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
    )


def domain_weights_from_choices(fit: ChoiceFit, domain_of: dict[str, str]) -> dict[str, float]:
    """Roll indicator importances up to domains, normalised to 100."""
    totals: dict[str, float] = {}
    for indicator, weight in fit.weights.items():
        domain = domain_of.get(indicator)
        if domain:
            totals[domain] = totals.get(domain, 0.0) + weight
    grand = sum(totals.values())
    return {d: round(v / grand * 100, 2) for d, v in totals.items()} if grand else {}


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
