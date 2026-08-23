"""Join ingested indicators to the universe, transform, and rank nationally.

Output: `data/processed/features.parquet` (long form plus percentile) and
`coverage.parquet` (how much data each place actually has).

Coverage is not bookkeeping — it is countermeasure #4 from `docs/anti-bias.md`. Large,
well-instrumented places report more data. If a gap were treated as zero or as average,
place size would silently become a scoring dimension. So gaps stay null, and every place
carries the share of applicable indicators it genuinely has.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from wlm.ingest.base import registry
from wlm.paths import PROCESSED

TRANSFORMS = {"none", "log", "sqrt", "per_capita"}

FEATURE_COLUMNS = [
    "geo_level", "geo_id", "indicator_id",
    "value", "value_transformed", "percentile",
    "vintage", "source_file",
]


@dataclass
class FeatureReport:
    rows_in: int = 0
    rows_joined: int = 0
    rows_dropped_no_geo: int = 0
    indicators_seen: int = 0
    null_values: int = 0
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"long rows in            {self.rows_in:>8,}",
            f"  joined to universe    {self.rows_joined:>8,}",
            f"  dropped (unknown geo) {self.rows_dropped_no_geo:>8,}",
            f"indicators present      {self.indicators_seen:>8,}",
            f"null values preserved   {self.null_values:>8,}  (never imputed to zero)",
        ]
        return "\n".join(lines + [f"  warning: {w}" for w in self.warnings])


def _apply_transform(df: pl.DataFrame, reg: dict[str, dict]) -> pl.DataFrame:
    """Add `value_transformed` per the registry's transform for each indicator."""
    kind = pl.col("indicator_id").replace_strict(
        {i: (e.get("transform") or "none") for i, e in reg.items()},
        default="none",
        return_dtype=pl.Utf8,
    )
    v = pl.col("value")
    return df.with_columns(kind.alias("_transform")).with_columns(
        pl.when(pl.col("_transform") == "log")
        # log1p keeps zero finite; negatives are not log-able and stay null rather than
        # silently becoming a number.
        .then(pl.when(v >= 0).then((v + 1).log()).otherwise(None))
        .when(pl.col("_transform") == "sqrt")
        .then(pl.when(v >= 0).then(v.sqrt()).otherwise(None))
        .when(pl.col("_transform") == "per_capita")
        .then(pl.when(pl.col("population") > 0).then(v / pl.col("population")).otherwise(None))
        .otherwise(v)
        .alias("value_transformed")
    ).drop("_transform")


def _add_percentiles(df: pl.DataFrame) -> pl.DataFrame:
    """National percentile within each (indicator, geo_level).

    Percentile rather than z-score because US place data is full of extreme outliers — one
    county's land area or income would otherwise dominate the scale
    (`docs/methodology.md` section 3).
    """
    grp = ["indicator_id", "geo_level"]
    ranked = df.with_columns(
        pl.col("value_transformed").rank(method="average").over(grp).alias("_rank"),
        pl.col("value_transformed").count().over(grp).alias("_n"),
    )
    return ranked.with_columns(
        pl.when(pl.col("value_transformed").is_null())
        .then(None)  # missing has no rank; it must not become 0.0
        .when(pl.col("_n") <= 1)
        .then(pl.lit(0.5))  # a lone observation is neither best nor worst
        .otherwise((pl.col("_rank") - 1) / (pl.col("_n") - 1))
        .alias("percentile")
    ).drop("_rank", "_n")


def compute_coverage(features: pl.DataFrame, universe: pl.DataFrame, reg: dict[str, dict]) -> pl.DataFrame:
    """Share of applicable indicators each geography actually has."""
    applicable = {}
    for entry in reg.values():
        applicable[entry["geo_level"]] = applicable.get(entry["geo_level"], 0) + 1

    present = (
        features.filter(pl.col("value").is_not_null())
        .group_by(["geo_level", "geo_id"])
        .agg(pl.col("indicator_id").n_unique().alias("indicators_present"))
    )

    return (
        universe.select(["geo_level", "geo_id", "name"])
        .join(present, on=["geo_level", "geo_id"], how="left")
        .with_columns(
            pl.col("indicators_present").fill_null(0),
            pl.col("geo_level")
            .replace_strict(applicable, default=0, return_dtype=pl.Int64)
            .alias("indicators_applicable"),
        )
        .with_columns(
            pl.when(pl.col("indicators_applicable") > 0)
            .then(pl.col("indicators_present") / pl.col("indicators_applicable"))
            .otherwise(None)
            .alias("coverage")
        )
    )


def build(
    *,
    universe: pl.DataFrame,
    long_frames: list[pl.DataFrame],
    reg: dict[str, dict] | None = None,
    out_dir: Path = PROCESSED,
    write: bool = True,
) -> tuple[pl.DataFrame, pl.DataFrame, FeatureReport]:
    reg = reg if reg is not None else registry()
    report = FeatureReport()

    long = pl.concat(long_frames, how="vertical") if long_frames else pl.DataFrame()
    report.rows_in = long.height
    if long.is_empty():
        return long, pl.DataFrame(), report

    joined = long.join(
        universe.select(["geo_level", "geo_id", "population"]),
        on=["geo_level", "geo_id"],
        how="inner",
    )
    report.rows_joined = joined.height
    report.rows_dropped_no_geo = long.height - joined.height
    if report.rows_dropped_no_geo:
        # Break the drop down by indicator so a genuine join bug is distinguishable from a
        # source that simply covers geographies below the population floor. A generic total
        # hides the difference, and the two need opposite responses.
        dropped = long.join(
            universe.select(["geo_level", "geo_id"]), on=["geo_level", "geo_id"], how="anti"
        )
        worst = (
            dropped.group_by("indicator_id").len().sort("len", descending=True).head(3)
        )
        report.warnings.append(
            "dropped rows by indicator: "
            + ", ".join(f"{r['indicator_id']} {r['len']:,}" for r in worst.iter_rows(named=True))
        )
        report.warnings.append(
            f"{report.rows_dropped_no_geo} row(s) referenced a geography outside the universe. "
            "Usually benign — a source covers places below the population floor. Worth "
            "checking when the count is large, since a GEOID width or vintage mismatch looks "
            "identical here and would present as missing data downstream."
        )

    features = _add_percentiles(_apply_transform(joined, reg)).select(FEATURE_COLUMNS)
    report.indicators_seen = features["indicator_id"].n_unique()
    report.null_values = int(features["value"].null_count())

    coverage = compute_coverage(features, universe, reg)

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        features.write_parquet(out_dir / "features.parquet")
        coverage.write_parquet(out_dir / "coverage.parquet")

    return features, coverage, report
