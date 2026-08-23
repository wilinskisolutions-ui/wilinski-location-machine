"""Turn weights into a ranking.

Implements `docs/methodology.md` sections 3-8. The choices that matter:

- **Geometric mean, not arithmetic.** A weighted average is fully compensatory: a place
  that is excellent on nine domains and catastrophic on healthcare averages its way to the
  top. Real relocation decisions are not like that — one intolerable dimension disqualifies
  a place. The geometric mean punishes low values disproportionately, and an epsilon floor
  keeps that severe but finite.
- **Missing renormalises, never zeroes.** Weights are redistributed across the indicators a
  place actually has, so a data gap is not scored as a failing grade (Principle 6).
- **Knockouts are a mask applied after scoring**, so the eliminated set stays inspectable
  and every filter can report what it cost.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from wlm.features.curves import desirability

EPSILON = 0.01  # floor for the geometric mean: severe but finite

# Minimum share of the household's weight a candidate must actually have data for.
# Renormalising over present indicators is right (Principle 6), but past a point it
# stops being a fair comparison: King County, Texas (population 215) ranked 7th while
# scored on 48% of the weight. Below this floor a place is excluded and counted, not
# quietly ranked against places measured twice as thoroughly.
MIN_WEIGHT_COVERED = 0.80


@dataclass
class ScoreReport:
    places_scored: int = 0
    domains_used: int = 0
    knockouts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"scored {self.places_scored:,} candidates across {self.domains_used} domains"]
        for k in self.knockouts:
            lines.append(
                f"  knockout {k['indicator']} {k['op']} {k['value']}: removed {k['removed']:,}"
                + (f" (best removed: {k['best_removed']})" if k.get("best_removed") else "")
            )
        lines += [f"  warning: {w}" for w in self.warnings]
        return "\n".join(lines)


def attach_desirability(
    features: pl.DataFrame, registry: dict[str, dict], overrides: dict[str, dict] | None = None
) -> pl.DataFrame:
    """Map every value through its preference curve, honouring elicited overrides."""
    overrides = overrides or {}
    out = []
    for row in features.iter_rows(named=True):
        entry = registry.get(row["indicator_id"])
        if entry is None:
            continue
        override = overrides.get(row["indicator_id"]) or {}
        if override.get("indifferent"):
            continue  # household said they don't care; excluding beats guessing
        curve = override.get("curve", entry["curve"])
        params = override.get("curve_params", entry.get("curve_params"))
        d = desirability(
            curve=curve, value=row["value"], percentile=row["percentile"], params=params
        )
        if d is None:
            continue
        out.append({**row, "desirability": d, "domain": entry["domain"]})
    return pl.DataFrame(out) if out else pl.DataFrame()


def _geometric(values: list[float], weights: list[float]) -> float | None:
    total = sum(weights)
    if total <= 0 or not values:
        return None
    acc = sum(w * math.log(max(v, EPSILON)) for v, w in zip(values, weights))
    return math.exp(acc / total)


def score(
    features: pl.DataFrame,
    registry: dict[str, dict],
    profile: dict,
    *,
    indicator_weights: dict[str, float] | None = None,
) -> tuple[pl.DataFrame, ScoreReport]:
    """Score every geography in `features` against one profile."""
    report = ScoreReport()
    weights = {k: v for k, v in (profile.get("domain_weights") or {}).items() if v > 0}
    if not weights:
        report.warnings.append("profile has no positive domain weights; nothing to score")
        return pl.DataFrame(), report

    # Prefer the profile's own within-domain weights; fall back to equal.
    if indicator_weights is None:
        indicator_weights = profile.get("indicator_weights") or {}

    desir = attach_desirability(features, registry, profile.get("curve_overrides"))
    if desir.is_empty():
        report.warnings.append("no indicator produced a desirability value")
        return pl.DataFrame(), report

    # Principle 10, enforced at the one place every ranking passes through. A sensitive
    # indicator is dropped outright unless the profile opted into it by name: the
    # within-domain weight floor on line ~126 means a zero weight would still leave it
    # counting at 0.05, so silence has to mean absence rather than a small number.
    opted_in = set(profile.get("sensitive_indicators") or [])
    excluded = sorted(
        i for i, e in registry.items() if e.get("sensitive") and i not in opted_in
    )
    if excluded:
        desir = desir.filter(~pl.col("indicator_id").is_in(excluded))
        report.warnings.append(
            f"{len(excluded)} sensitive indicator(s) not opted into and excluded: "
            + ", ".join(excluded)
        )
        if desir.is_empty():
            report.warnings.append("nothing left to score once sensitive data was excluded")
            return pl.DataFrame(), report

    # Domains carrying weight but no data cannot influence anything. Say so.
    present_domains = set(desir["domain"].unique())
    for domain, w in weights.items():
        if domain not in present_domains:
            report.warnings.append(
                f"'{domain}' carries {w:.0f} points of weight but has no data — "
                "it cannot affect this ranking"
            )

    rows: list[dict] = []
    for (geo_id,), group in desir.group_by(["geo_id"]):
        per_domain: dict[str, float] = {}
        for (domain,), sub in group.group_by(["domain"]):
            if domain not in weights:
                continue
            # An indicator the trade-offs never touched still counts, at a small weight:
            # dropping it would silently narrow the domain to whatever was asked about.
            ws = [max(indicator_weights.get(i, 0.0), 0.05) for i in sub["indicator_id"]]
            value = _geometric(list(sub["desirability"]), ws)
            if value is not None:
                per_domain[domain] = value

        if not per_domain:
            continue
        # Renormalise across the domains this place actually has (Principle 6).
        dw = [weights[d] for d in per_domain]
        total = _geometric(list(per_domain.values()), dw)
        worst = min(per_domain, key=per_domain.get)
        covered = sum(dw) / sum(weights.values())
        rows.append(
            {
                "geo_id": geo_id,
                "score": total,
                "worst_domain": worst,
                "worst_domain_score": per_domain[worst],
                "weight_covered": covered,
                **{f"d_{d}": v for d, v in per_domain.items()},
            }
        )

    if not rows:
        # Polars raises ColumnNotFoundError on an empty frame, which tells nobody anything.
        # Reaching here means every candidate lost every weighted domain — usually because
        # the weight sits on domains with no data.
        report.warnings.append(
            "no candidate could be scored: none has data in any weighted domain "
            f"({', '.join(sorted(weights))})"
        )
        return pl.DataFrame(), report

    result = pl.DataFrame(rows).sort("score", descending=True)

    thin = result.filter(pl.col("weight_covered") < MIN_WEIGHT_COVERED)
    if thin.height:
        report.warnings.append(
            f"{thin.height:,} candidate(s) excluded: data covers under "
            f"{MIN_WEIGHT_COVERED:.0%} of the weighted domains"
        )
        result = result.filter(pl.col("weight_covered") >= MIN_WEIGHT_COVERED)

    report.places_scored = result.height
    report.domains_used = len(present_domains & set(weights))
    return result, report


def apply_knockouts(
    scores: pl.DataFrame,
    features: pl.DataFrame,
    knockouts: list[dict],
    report: ScoreReport,
    names: dict[str, str] | None = None,
) -> pl.DataFrame:
    """Mask out places failing a deal-breaker, reporting what each filter cost."""
    surviving = scores
    for rule in knockouts or []:
        indicator, op = rule.get("indicator"), rule.get("op", "max")
        try:
            threshold = float(rule.get("value"))
        except (TypeError, ValueError):
            # A deal-breaker that cannot be read must not disappear quietly: the household
            # would believe a filter was applied that never ran.
            report.warnings.append(
                f"knockout on '{indicator}' skipped — value {rule.get('value')!r} "
                f"(from {rule.get('from', 'unknown question')}) is not a number"
            )
            continue

        relevant = features.filter(
            (pl.col("indicator_id") == indicator) & pl.col("value").is_not_null()
        )
        if relevant.is_empty():
            report.warnings.append(f"knockout on '{indicator}' skipped — no data")
            continue

        failing = relevant.filter(
            pl.col("value") > threshold if op == "max" else pl.col("value") < threshold
        )
        failing_ids = set(failing["geo_id"])
        removed = surviving.filter(pl.col("geo_id").is_in(failing_ids))
        best = removed.head(1)
        report.knockouts.append(
            {
                "indicator": indicator,
                "op": op,
                "value": threshold,
                "removed": removed.height,
                "best_removed": (names or {}).get(best["geo_id"][0]) if best.height else None,
            }
        )
        surviving = surviving.filter(~pl.col("geo_id").is_in(failing_ids))
    return surviving


def joint(a: pl.DataFrame, b: pl.DataFrame) -> pl.DataFrame:
    """Combine two people. Geometric mean, plus an explicit disagreement column.

    Averaging two people into one preference vector destroys exactly the information a
    couple needs (Principle 8). A place ranked 4th with both agreeing is a different
    proposition from one ranked 4th because one of them loves it.
    """
    merged = a.select(["geo_id", "score"]).rename({"score": "score_a"}).join(
        b.select(["geo_id", "score"]).rename({"score": "score_b"}), on="geo_id", how="inner"
    )
    return merged.with_columns(
        ((pl.col("score_a") * pl.col("score_b")).sqrt()).alias("score_joint"),
        (pl.col("score_a") - pl.col("score_b")).abs().alias("disagreement"),
    ).sort("score_joint", descending=True)


def places_with_county_context(
    features: pl.DataFrame, place_rows: pl.DataFrame, winners: set[str]
) -> pl.DataFrame:
    """Every place in the winning counties, carrying its county's numbers as well as its own.

    A place inherits its county's context and adds its own local detail
    (docs/methodology.md section 1). Scored on place-level indicators alone it would be
    judged on about seven things, none of them climate, hazard, jobs or health — which is
    where nearly all the weight sits, and the stage returned nothing at all.

    Separated out because the sensitivity run has to jitter exactly the frame the ranking
    came from. Banding places on their seven local indicators while ranking them on forty
    would produce an honest-looking band for a different question.
    """
    own = features.filter(
        (pl.col("geo_level") == "place") & pl.col("geo_id").is_in(set(place_rows["geo_id"]))
    )
    county_context = (
        features.filter((pl.col("geo_level") == "county") & pl.col("geo_id").is_in(winners))
        .rename({"geo_id": "county_geoid"})
        .join(place_rows, on="county_geoid", how="inner")
        .drop("county_geoid")
        .with_columns(pl.lit("place").alias("geo_level"))
    )
    return pl.concat(
        [own.select(sorted(own.columns)), county_context.select(sorted(own.columns))],
        how="vertical",
    )


def two_stage(
    features: pl.DataFrame,
    universe: pl.DataFrame,
    registry: dict[str, dict],
    profile: dict,
    *,
    top_counties: int = 25,
) -> tuple[pl.DataFrame, pl.DataFrame, ScoreReport]:
    """Rank counties, then rank places inside the winners.

    Counties carry roughly 35 indicators and places roughly 8 — climate, hazard, jobs and
    health are all county-level. Ranking them in one list would compare things measured to
    very different depths, and let a shallow place win on near-complete coverage of very
    little.

    So the deep data does the hard cut (which region), and the local data does the fine cut
    (which town within it), which is also how people actually decide.
    """
    counties = features.filter(pl.col("geo_level") == "county")
    county_scores, report = score(counties, registry, profile)
    if county_scores.is_empty():
        return county_scores, pl.DataFrame(), report

    # Only counties that actually contain a town you could move to. 43% of US counties have
    # no place above the 5,000 floor, and several were topping the ranking — a county you
    # cannot move to a town in is not a candidate for this decision.
    with_places = universe.filter(pl.col("geo_level") == "place").group_by("county_geoid").len()
    livable = set(with_places["county_geoid"])
    eligible = county_scores.filter(pl.col("geo_id").is_in(livable))
    skipped = county_scores.head(top_counties).filter(~pl.col("geo_id").is_in(livable)).height
    if skipped:
        report.warnings.append(
            f"{skipped} of the top {top_counties} counties contain no town above the "
            "population floor; stage 2 skipped past them"
        )

    winners = set(eligible.head(top_counties)["geo_id"])
    place_rows = universe.filter(
        (pl.col("geo_level") == "place") & pl.col("county_geoid").is_in(winners)
    ).select(["geo_id", "county_geoid"])
    if place_rows.is_empty():
        report.warnings.append("no places inside the winning counties")
        return county_scores, pl.DataFrame(), report

    combined = places_with_county_context(features, place_rows, winners)
    place_scores, place_report = score(combined, registry, profile)
    report.warnings.extend(place_report.warnings)
    return county_scores, place_scores, report


def sensitivity(
    features: pl.DataFrame,
    registry: dict[str, dict],
    profile: dict,
    *,
    draws: int = 200,
    concentration: float = 60.0,
    seed: int = 17,
    top_n: int = 300,
) -> pl.DataFrame:
    """Rank stability under jittered weights.

    Weights are elicited estimates, so ranks are estimates. A rank reported without its band
    is false precision (Principle 9) — with thousands of candidates many adjacent ranks are
    indistinguishable.
    """
    rng = np.random.default_rng(seed)
    base = {k: v for k, v in (profile.get("domain_weights") or {}).items() if v > 0}
    if not base:
        return pl.DataFrame()

    # Only jitter the contenders. Re-scoring all 3,144 counties took about 5 seconds a draw,
    # so the default of 200 would have run for 17 minutes — and nobody needs to know whether
    # rank 2,000 is stable. Narrowing to the top few hundred keeps the answer identical
    # where it matters and makes it usable.
    if top_n:
        baseline, _ = score(features, registry, profile)
        if not baseline.is_empty():
            contenders = set(baseline.head(top_n)["geo_id"])
            features = features.filter(pl.col("geo_id").is_in(contenders))

    domains = list(base)
    alpha = np.array([base[d] for d in domains], dtype=float)
    alpha = alpha / alpha.sum() * concentration

    collected: dict[str, list[int]] = {}
    for _ in range(draws):
        jittered = rng.dirichlet(alpha) * 100
        trial = dict(profile)
        trial["domain_weights"] = dict(zip(domains, jittered))
        result, _ = score(features, registry, trial)
        if result.is_empty():
            continue
        for rank, geo_id in enumerate(result["geo_id"], start=1):
            collected.setdefault(geo_id, []).append(rank)

    rows = []
    for geo_id, ranks in collected.items():
        arr = np.array(ranks)
        rows.append(
            {
                "geo_id": geo_id,
                "rank_median": int(np.median(arr)),
                "rank_p05": int(np.percentile(arr, 5)),
                "rank_p95": int(np.percentile(arr, 95)),
                "rank_spread": int(np.percentile(arr, 95) - np.percentile(arr, 5)),
            }
        )
    if not rows:
        # Every draw scored nothing. Returning an empty frame with the right columns lets
        # the caller's band check say "no band" rather than polars saying "no column".
        return pl.DataFrame(
            schema={
                "geo_id": pl.Utf8, "rank_median": pl.Int64,
                "rank_p05": pl.Int64, "rank_p95": pl.Int64, "rank_spread": pl.Int64,
            }
        )
    return pl.DataFrame(rows).sort("rank_median")
