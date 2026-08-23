"""Calibration: does the elicited model reproduce judgements the household already holds?

The step these projects skip, and the reason they fail. A ranking nobody has validated is
just a confident-looking list.

**This diagnoses. It must never auto-tune.** Fitting the weights to these ratings would be
circular — the ratings and the weights come from the same two people — and it would destroy
the forced trade-offs that make the weights informative. A poor correlation is a finding to
investigate, not an error term to minimise.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import yaml

from wlm.features.curves import desirability
from wlm.paths import CONFIG, OUTPUT, PROCESSED, ROOT

PROFILES = ROOT / "profiles"


def spearman(a: list[float], b: list[float]) -> float | None:
    """Rank correlation, computed without scipy."""
    n = len(a)
    if n < 3:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = shared
            i = j + 1
        return out

    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return (num / den) if den else None


def score_places(geo_ids: list[str], weights: dict[str, float]) -> dict[str, float]:
    """Crude weighted-percentile score, sufficient for a correlation check.

    Deliberately simpler than the Phase 4 engine: this asks whether the *weights* point the
    right way, not whether the full aggregation is right.
    """
    registry = {i["id"]: i for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]}
    f = pl.read_parquet(PROCESSED / "features.parquet").filter(
        pl.col("geo_id").is_in(geo_ids) & pl.col("value").is_not_null()
    )
    out: dict[str, float] = {}
    for geo_id, group in f.group_by("geo_id"):
        total = weighted = 0.0
        for row in group.iter_rows(named=True):
            entry = registry.get(row["indicator_id"])
            if entry is None:
                continue
            w = weights.get(entry["domain"], 0.0)
            if w <= 0:
                continue
            # Use the real preference curve. Treating every percentile as monotone scored
            # ideal_band indicators wrongly in the one check meant to validate everything —
            # a town of exactly the right size looked mediocre because it sat mid-distribution.
            d = desirability(
                curve=entry["curve"],
                value=row["value"],
                percentile=row["percentile"],
                params=entry.get("curve_params"),
            )
            if d is None:
                continue
            weighted += w * d
            total += w
        if total:
            out[geo_id[0] if isinstance(geo_id, tuple) else geo_id] = weighted / total
    return out


def build(person: str, *, write: bool = True) -> str:
    profile_path = PROFILES / f"{person}.yaml"
    if not profile_path.exists():
        return f"No profile for {person} — run `make questionnaire PERSON={person}` first."

    profile = yaml.safe_load(profile_path.read_text())
    ratings = (profile.get("notes") or {}).get("calibration") or {}
    if not isinstance(ratings, dict) or len(ratings) < 3:
        return (f"{person} rated fewer than 3 places; calibration needs more to say anything. "
                "Rate places you genuinely know.")

    weights = profile.get("domain_weights") or {}
    scores = score_places(list(ratings), weights)
    paired = [(g, float(r), scores[g]) for g, r in ratings.items() if g in scores]
    if len(paired) < 3:
        return f"{person}: too few rated places had data to score."

    universe = pl.read_parquet(PROCESSED / "universe.parquet")
    names = dict(zip(universe["geo_id"], universe["name"] + ", " + universe["state_usps"]))

    rho = spearman([p[1] for p in paired], [p[2] for p in paired])
    # Rank both, so a "miss" means the model ranked it very differently, not just scaled it.
    by_rating = {g: i for i, (g, _, _) in enumerate(sorted(paired, key=lambda p: -p[1]))}
    by_score = {g: i for i, (g, _, _) in enumerate(sorted(paired, key=lambda p: -p[2]))}
    misses = sorted(paired, key=lambda p: -abs(by_rating[p[0]] - by_score[p[0]]))

    lines = [
        f"# Calibration — {person}",
        "",
        f"**{len(paired)} places rated.** Rank correlation between {person}'s ratings and the "
        f"elicited weights: **{rho:+.2f}**" if rho is not None else "Correlation unavailable.",
        "",
    ]
    if rho is None:
        # Say which of the two reasons it is. "Not enough data" reads as a coverage gap
        # when the real problem is usually that every place got the same score, and the two
        # call for completely different responses.
        spread = len({r for _, r, _ in paired})
        verdict = (
            f"Every one of the {len(paired)} rated places got the same score, so there is no "
            "ordering to compare against. Rate them relative to each other — the point is "
            "which you would rather live in, not whether each is good."
            if spread <= 1 else
            f"Only {len(paired)} places had both a rating and enough data to score. "
            "Rate more of the list, including places you would not move to."
        )
    elif rho >= 0.6:
        verdict = ("The weights reproduce judgements already held. That is the green light for "
                   "trusting a ranking built on them.")
    elif rho >= 0.3:
        verdict = ("Partial agreement. Worth reading the misses below before trusting a full "
                   "ranking — something is being weighted differently than it is felt.")
    else:
        verdict = ("**The weights do not reproduce judgements already held.** Do not trust a "
                   "ranking built on them yet. Either the questionnaire measured the wrong "
                   "thing, or the ratings encode something not in the data at all — which is "
                   "itself worth knowing.")
    lines += [verdict, ""]

    # The disagreement table only means anything once the ratings carry an order. Printing
    # it under "correlation unavailable" presented rank noise as a finding, complete with a
    # paragraph explaining how to interpret it.
    if rho is not None:
        lines += ["## Largest disagreements", "",
                  "| Place | Rated | Model rank | Rating rank |", "|---|---|---|---|"]
        for geo_id, rating, _score in misses[:5]:
            lines.append(
                f"| {names.get(geo_id, geo_id)} | {rating:.0f}/10 | "
                f"{by_score[geo_id] + 1} | {by_rating[geo_id] + 1} |"
            )
        lines += ["", "A place rated far above where the model puts it usually means something "
                  "matters that the indicators do not capture. That gap is the finding.", ""]

    text = "\n".join(lines)
    if write:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / f"calibration_{person}.md").write_text(text)
    return text


if __name__ == "__main__":
    import sys

    from wlm.questionnaire.session import REAL_PEOPLE

    for who in (sys.argv[1:] or list(REAL_PEOPLE)):
        print(build(who))
        print()
