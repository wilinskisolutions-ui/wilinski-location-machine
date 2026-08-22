"""Preference curves: turn an indicator value into a desirability in [0, 1].

The distinction implemented here is the one most easily got wrong, and it fails silently
when it is (`docs/methodology.md` section 3):

- **Monotone curves act on the national PERCENTILE.** "Cheaper is better" is a statement
  about rank.
- **Non-monotone curves act on the RAW value.** "A town between 25,000 and 250,000 people"
  is a statement about people, in people. Run through a percentile it becomes nonsense —
  under `higher_better` a four-million-person county outranks the ideal town, and the
  output still looks like a perfectly reasonable ranking.

Missing input yields `None`, never 0. A place with no data is not a place that scored badly
(Principle 6).
"""

from __future__ import annotations

import math

MONOTONE = {"higher_better", "lower_better"}
RAW_VALUED = {"ideal_band", "ideal_point"}
ALL_CURVES = MONOTONE | RAW_VALUED


class CurveError(ValueError):
    """An unusable curve definition."""


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def higher_better(percentile: float) -> float:
    return _clamp01(percentile)


def lower_better(percentile: float) -> float:
    return _clamp01(1.0 - percentile)


def ideal_band(
    value: float,
    *,
    lo: float,
    hi: float,
    shoulder: float,
    shoulder_lo: float | None = None,
    shoulder_hi: float | None = None,
) -> float:
    """Full desirability inside [lo, hi], decaying linearly to 0 over the shoulder.

    The two sides can decay at different rates. This matters more than it looks: with one
    symmetric shoulder, a band of 25,000-250,000 people gives a 500-person village 0.51,
    because 24,500 is "close" in linear units. It is not close in any sense the household
    means. Set `shoulder_lo` smaller than `shoulder_hi` for quantities like population where
    the scale is effectively logarithmic.
    """
    if lo >= hi:
        raise CurveError(f"ideal_band needs lo < hi, got lo={lo} hi={hi}")
    below = shoulder_lo if shoulder_lo is not None else shoulder
    above = shoulder_hi if shoulder_hi is not None else shoulder
    if below <= 0 or above <= 0:
        raise CurveError(f"ideal_band shoulders must be positive, got lo={below} hi={above}")
    if lo <= value <= hi:
        return 1.0
    if value < lo:
        return _clamp01(1.0 - (lo - value) / below)
    return _clamp01(1.0 - (value - hi) / above)


def ideal_point(value: float, *, target: float, tol: float) -> float:
    """Gaussian falloff around `target`; `tol` is the distance at which it drops to ~0.37."""
    if tol <= 0:
        raise CurveError(f"ideal_point tol must be positive, got {tol}")
    return _clamp01(math.exp(-(((value - target) / tol) ** 2)))


def desirability(
    *,
    curve: str,
    value: float | None,
    percentile: float | None,
    params: dict | None = None,
) -> float | None:
    """Apply `curve`, choosing raw value or percentile as the curve requires."""
    params = params or {}

    if curve not in ALL_CURVES:
        raise CurveError(f"unknown curve '{curve}'; expected one of {sorted(ALL_CURVES)}")

    if curve in MONOTONE:
        if percentile is None:
            return None
        return higher_better(percentile) if curve == "higher_better" else lower_better(percentile)

    # Raw-valued curves need the value itself, in its own unit.
    if value is None:
        return None
    if curve == "ideal_band":
        return ideal_band(
            value,
            lo=params["lo"],
            hi=params["hi"],
            shoulder=params["shoulder"],
            shoulder_lo=params.get("shoulder_lo"),
            shoulder_hi=params.get("shoulder_hi"),
        )
    return ideal_point(value, target=params["target"], tol=params["tol"])
