"""The household's current home, as the reference every candidate is measured against.

They live in **Harrisburg, Pennsylvania** and have decided they are leaving, so Harrisburg
is scored but excluded from the candidate set (`CONTEXT.md`, 2026-08-22). It stays in the
universe for two reasons: a domestic move is only decidable as "better or worse than what
we have", and a model that ranks their current home absurdly is telling us the weights are
wrong before it tells us anything about anywhere else.
"""

from __future__ import annotations

import polars as pl

BASELINE_PLACE = "4232800"   # Harrisburg city, PA
BASELINE_COUNTY = "42043"    # Dauphin County, PA
BASELINE_LABEL = "Harrisburg, PA"

# Scored, reported, but never offered as a destination.
EXCLUDE_FROM_CANDIDATES = True


def mark(universe: pl.DataFrame) -> pl.DataFrame:
    """Add `is_baseline` and `is_candidate` columns."""
    is_baseline = pl.col("geo_id").is_in([BASELINE_PLACE, BASELINE_COUNTY])
    return universe.with_columns(
        is_baseline.alias("is_baseline"),
        (~is_baseline if EXCLUDE_FROM_CANDIDATES else pl.lit(True)).alias("is_candidate"),
    )


def compare(features: pl.DataFrame) -> pl.DataFrame:
    """Add `baseline_value` and `vs_baseline` to every feature row.

    `vs_baseline` is the percentile gap against the household's current home at the same
    geography level: positive means this place ranks higher nationally than Harrisburg on
    that indicator. It is deliberately signed and in percentile terms so improvements are
    directly comparable across indicators measured in different units.
    """
    baseline = (
        features.filter(pl.col("geo_id").is_in([BASELINE_PLACE, BASELINE_COUNTY]))
        .select(["geo_level", "indicator_id", "value", "percentile"])
        .rename({"value": "baseline_value", "percentile": "baseline_percentile"})
        .unique(subset=["geo_level", "indicator_id"])
    )
    return features.join(baseline, on=["geo_level", "indicator_id"], how="left").with_columns(
        (pl.col("percentile") - pl.col("baseline_percentile")).alias("vs_baseline")
    )
