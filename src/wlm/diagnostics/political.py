"""The stacking trap, measured: what does the sensitive layer actually cost?

From `docs/anti-bias.md` and the decision logged in `CONTEXT.md`. Emil described the
household as more conservative and asked not to rule anything out early. That preference,
combined with wanting somewhere warm and somewhere with cheap access to Europe, points at
the same Sunbelt metros the internet already over-promotes — the same shortlist arrived at
by a different route.

The mitigation is not to refuse the preference. It is to price it. Every ranking is produced
twice, with the sensitive layer on and off, and the difference is reported per place:
  * how far each place moved, and which way
  * what entered and left the top of the list
  * the best-scoring places on the *other* side of the axis, always shown

That last one is the point. A filter whose cost stays invisible is a filter nobody can
decide about. If turning the layer on drops a place they would otherwise have loved, they
should be looking at it and choosing, not never learning it existed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
import yaml

from wlm.paths import CONFIG, FEATURES, OUTPUT, UNIVERSE
from wlm.scoring.engine import score


@dataclass
class PoliticalReport:
    on: pl.DataFrame = field(default_factory=pl.DataFrame)
    off: pl.DataFrame = field(default_factory=pl.DataFrame)
    delta: pl.DataFrame = field(default_factory=pl.DataFrame)
    entered: list[str] = field(default_factory=list)
    left: list[str] = field(default_factory=list)
    counter_axis: pl.DataFrame = field(default_factory=pl.DataFrame)
    indicators: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _registry() -> dict[str, dict]:
    return {
        i["id"]: i
        for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]
    }


def _ranked(frame: pl.DataFrame, names: dict[str, str]) -> pl.DataFrame:
    return frame.with_row_index("rank", offset=1).with_columns(
        pl.col("geo_id").replace_strict(names, default=pl.col("geo_id")).alias("name")
    )


def compare(
    profile: dict,
    *,
    features: pl.DataFrame | None = None,
    universe: pl.DataFrame | None = None,
    registry: dict[str, dict] | None = None,
    top: int = 25,
) -> PoliticalReport:
    """Score with the sensitive layer on and off, and report the gap."""
    report = PoliticalReport()
    features = features if features is not None else pl.read_parquet(FEATURES)
    universe = universe if universe is not None else pl.read_parquet(UNIVERSE)
    registry = registry or _registry()

    opted_in = list(profile.get("sensitive_indicators") or [])
    report.indicators = opted_in
    if not opted_in:
        report.notes.append(
            "the sensitive layer is off: nothing was opted into, so there is no delta to "
            "report. This comparison becomes meaningful the moment it is switched on."
        )

    counties = features.filter(pl.col("geo_level") == "county")
    names = {
        r["geo_id"]: f"{r['name']}, {r['state_usps']}"
        for r in universe.select(["geo_id", "name", "state_usps"]).iter_rows(named=True)
    }

    with_layer, _ = score(counties, registry, profile)
    # Off means the domain carries no weight at all, not merely that the indicators are
    # dropped: removing them while leaving the weight would redistribute it and pretend the
    # comparison was about something else.
    without = dict(profile)
    without["domain_weights"] = {
        k: v for k, v in (profile.get("domain_weights") or {}).items() if k != "sensitive"
    }
    without["sensitive_indicators"] = []
    no_layer, _ = score(counties, registry, without)

    if with_layer.is_empty() or no_layer.is_empty():
        report.notes.append("one of the two runs scored nothing; no comparison possible")
        return report

    report.on = _ranked(with_layer, names)
    report.off = _ranked(no_layer, names)

    delta = (
        report.on.select(["geo_id", "name", "rank", "score"])
        .rename({"rank": "rank_on", "score": "score_on"})
        .join(
            report.off.select(["geo_id", "rank", "score"])
            .rename({"rank": "rank_off", "score": "score_off"}),
            on="geo_id",
            how="inner",
        )
        .with_columns(
            # Positive means the layer helped it: a smaller rank number is better.
            (pl.col("rank_off") - pl.col("rank_on")).alias("rank_change")
        )
    )
    report.delta = delta.sort("rank_change", descending=True)

    on_top = set(report.on.head(top)["geo_id"])
    off_top = set(report.off.head(top)["geo_id"])
    report.entered = [names.get(g, g) for g in on_top - off_top]
    report.left = [names.get(g, g) for g in off_top - on_top]

    # Always show the best places on the other side of the axis, whatever the axis is.
    report.counter_axis = _counter_axis(counties, registry, profile, names, opted_in)
    return report


def _counter_axis(
    counties: pl.DataFrame,
    registry: dict[str, dict],
    profile: dict,
    names: dict[str, str],
    opted_in: list[str],
    *,
    show: int = 12,
) -> pl.DataFrame:
    """Places that score well but sit opposite the household on the sensitive indicators.

    Built by scoring with the layer off and then keeping the high scorers whose sensitive
    values fall on the far side of the elicited ideal — so the list is "good places you are
    filtering out", which is the only version of it worth showing.
    """
    if not opted_in:
        return pl.DataFrame()

    without = dict(profile)
    without["domain_weights"] = {
        k: v for k, v in (profile.get("domain_weights") or {}).items() if k != "sensitive"
    }
    without["sensitive_indicators"] = []
    base, _ = score(counties, registry, without)
    if base.is_empty():
        return pl.DataFrame()

    overrides = profile.get("curve_overrides") or {}
    frames = []
    for indicator in opted_in:
        params = (overrides.get(indicator) or {}).get("curve_params") or registry[
            indicator
        ].get("curve_params") or {}
        ideal = params.get("point", params.get("lo"))
        values = counties.filter(
            (pl.col("indicator_id") == indicator) & pl.col("value").is_not_null()
        ).select(["geo_id", "value"])
        if values.is_empty() or ideal is None:
            continue
        median = values["value"].median()
        # "Other side" means the opposite side of the national median from the ideal.
        far = (
            values.filter(pl.col("value") > median)
            if ideal <= median
            else values.filter(pl.col("value") < median)
        )
        frames.append(
            far.join(base.select(["geo_id", "score"]), on="geo_id", how="inner")
            .with_columns(pl.lit(indicator).alias("indicator"))
            .sort("score", descending=True)
            .head(show)
        )

    if not frames:
        return pl.DataFrame()
    return pl.concat(frames).with_columns(
        pl.col("geo_id").replace_strict(names, default=pl.col("geo_id")).alias("name")
    )


def render(report: PoliticalReport) -> str:
    lines = [
        "# The sensitive layer, with and without",
        "",
        "Every ranking is produced twice so the cost of the filter stays visible.",
        "",
    ]
    if report.notes:
        lines += [f"> {n}" for n in report.notes] + [""]

    if report.delta.is_empty():
        lines += [
            "The two runs are identical, which is what an unweighted sensitive layer",
            "should produce. Nothing here is hidden; there is simply nothing to show yet.",
            "",
        ]
        return "\n".join(lines)

    lines += [
        f"Layer indicators: {', '.join(report.indicators) or 'none'}.",
        "",
        "## What the filter moves",
        "",
        f"Entered the top 25 when the layer was switched on: "
        f"{', '.join(sorted(report.entered)) or 'nothing'}.",
        "",
        f"Dropped out of the top 25: {', '.join(sorted(report.left)) or 'nothing'}.",
        "",
        "## Biggest movers",
        "",
        "| County | Rank with layer | Rank without | Change |",
        "|---|---|---|---|",
    ]
    movers = pl.concat([report.delta.head(8), report.delta.tail(8)]).unique(
        subset=["geo_id"], keep="first"
    ).sort("rank_change", descending=True)
    for row in movers.iter_rows(named=True):
        lines.append(
            f"| {row['name']} | {row['rank_on']:,} | {row['rank_off']:,} "
            f"| {row['rank_change']:+,} |"
        )

    lines += [
        "",
        "## Good places on the other side of the axis",
        "",
        "These score well on everything else and sit opposite you on the sensitive",
        "indicators. They are shown because a filter whose cost is invisible is a filter",
        "nobody can actually decide about.",
        "",
    ]
    if report.counter_axis.is_empty():
        lines.append("_None to show._")
    else:
        lines += ["| County | Score | Axis |", "|---|---|---|"]
        for row in report.counter_axis.sort("score", descending=True).head(12).iter_rows(
            named=True
        ):
            lines.append(f"| {row['name']} | {row['score']:.3f} | {row['indicator']} |")
    return "\n".join(lines) + "\n"


def build(profile: dict | Path | str | None = None, *, write: bool = True) -> str:
    if isinstance(profile, (str, Path)):
        from wlm.profile import load_profile

        profile = load_profile(Path(profile))
    if profile is None:
        return "# The sensitive layer\n\nNo profile supplied.\n"

    text = render(compare(profile))
    if write:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "political.md").write_text(text)
    return text


if __name__ == "__main__":
    print(build())
