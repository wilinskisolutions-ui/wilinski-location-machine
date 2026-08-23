"""Turn the bank into a concrete list of questions, using real data.

Generated blocks draw from `features.parquet`, so:

- **Trade-off pairs are real places.** No impossible combination is ever shown — a place
  with San Francisco prices and Wyoming density does not exist and must not be offered.
- **Places stay unnamed**, which makes the trade-off block double as the blind evaluation
  from `docs/anti-bias.md`: choices are made on attributes, not on reputation.
- **Band questions are anchored to Harrisburg**, whose real values are filled in here.
  "Warmer than here?" is answerable; "what January mean do you want?" is not.
"""

from __future__ import annotations

import random
from pathlib import Path

import polars as pl
import yaml

from wlm.baseline import BASELINE_COUNTY, BASELINE_LABEL, BASELINE_PLACE
from wlm.paths import CONFIG, PROCESSED, ROOT

BANK = ROOT / "questionnaire" / "bank.yaml"

# How many attributes to show per trade-off. More than about six and the comparison stops
# being a judgement and starts being a spreadsheet.
ATTRIBUTES_PER_TASK = 5


def _fmt(value: float | None, unit: str | None) -> str:
    if value is None:
        return "—"
    u = (unit or "").lower()
    if u == "usd":
        return f"${value/1000:,.0f}k" if value >= 10_000 else f"${value:,.0f}"
    if u == "usd/month":
        return f"${value:,.0f}/mo"
    if u == "degf":
        return f"{value:.0f}°F"
    if u == "inches":
        return f'{value:.0f}"'
    if u == "miles":
        return f"{value:.0f} mi"
    if u == "minutes":
        return f"{value:.0f} min"
    if u == "people":
        return f"{value:,.0f}"
    if u == "per10k":
        return f"{value:.1f} per 10k"
    if u == "per100k":
        return f"{value:.1f} per 100k"
    if u == "years":
        return f"{value:.1f} yrs"
    if u == "share":
        return f"{value*100:.0f}%"
    if u == "count":
        return f"{value:.0f}"
    if u == "ug/m3":
        return f"{value:.1f} µg/m³"
    return f"{value:,.1f}"


def load_bank(path: Path = BANK) -> dict:
    return yaml.safe_load(Path(path).read_text())


def load_registry() -> dict[str, dict]:
    data = yaml.safe_load((CONFIG / "indicators.yaml").read_text())
    return {i["id"]: i for i in data["indicators"]}


def wide_counties(features: Path = PROCESSED / "features.parquet") -> pl.DataFrame:
    """One row per county, one column per indicator, joined to names."""
    f = pl.read_parquet(features).filter(pl.col("geo_level") == "county")
    wide = f.pivot(values="value", index="geo_id", on="indicator_id")
    universe = pl.read_parquet(PROCESSED / "universe.parquet").filter(
        pl.col("geo_level") == "county"
    )
    return wide.join(
        universe.select(["geo_id", "name", "state_usps", "population"]), on="geo_id", how="inner"
    )


# ------------------------------------------------------------------- generated blocks


def baseline_values(features: Path = PROCESSED / "features.parquet") -> dict[str, float]:
    """Harrisburg's value for every indicator, across BOTH geography levels.

    Population, density, median age and residential stability are place-level; climate and
    hazard are county-level. Looking in only one place silently dropped four band questions
    the first time, which would have left those bands on my provisional guesses.
    """
    f = pl.read_parquet(features).filter(
        pl.col("geo_id").is_in([BASELINE_COUNTY, BASELINE_PLACE]) & pl.col("value").is_not_null()
    )
    return dict(zip(f["indicator_id"], f["value"]))


def anchored_band_questions(spec: dict, wide: pl.DataFrame, registry: dict) -> list[dict]:
    base = baseline_values()
    missing = [i for i in spec["indicators"] if i not in base]
    if missing:
        # Loud rather than silent: a dropped band question means that indicator keeps a
        # placeholder curve nobody chose.
        print(f"  warning: no baseline value for {', '.join(missing)} — band question skipped")
    out = []
    for indicator in spec["indicators"]:
        entry = registry.get(indicator)
        value = base.get(indicator)
        if entry is None or value is None:
            continue
        out.append(
            {
                "id": f"band_{indicator}",
                "type": "scale",
                "text": f"{entry['label']}",
                "anchor": f"{BASELINE_LABEL}: {_fmt(value, entry.get('unit'))}",
                "help": "Compared with what you have now.",
                "options": [s["label"] for s in spec["scale"]],
                "offsets": [s["offset"] for s in spec["scale"]],
                "maps_to": {"kind": "indicator", "target": indicator, "sets": "curve_params"},
            }
        )
    return out


def _dominates(a: dict, b: dict, attrs: list[str], registry: dict) -> bool:
    """True if a is at least as good as b on every attribute — such a pair teaches nothing."""
    better_or_equal = True
    for attr in attrs:
        lower_is_better = registry[attr]["curve"] == "lower_better"
        av, bv = a[attr], b[attr]
        if av is None or bv is None:
            return True  # incomparable; reject the pair
        if lower_is_better:
            better_or_equal &= av <= bv
        else:
            better_or_equal &= av >= bv
    return better_or_equal


def choice_tasks(spec: dict, wide: pl.DataFrame, registry: dict, *, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    attrs = [a for a in spec["attributes"] if a in wide.columns]
    # Only offer places big enough that both are plausible destinations.
    pool = wide.filter(pl.col("population") > 40_000).drop_nulls(subset=attrs).to_dicts()
    tasks: list[dict] = []
    attempts = 0

    while len(tasks) < spec["tasks"] and attempts < spec["tasks"] * 200:
        attempts += 1
        shown = rng.sample(attrs, min(ATTRIBUTES_PER_TASK, len(attrs)))
        a, b = rng.sample(pool, 2)
        if _dominates(a, b, shown, registry) or _dominates(b, a, shown, registry):
            continue
        tasks.append(
            {
                "id": f"choice_{len(tasks) + 1}",
                "type": "choice_pair",
                "text": "Which would you rather live in?",
                "attributes": [
                    {
                        "indicator": attr,
                        "label": registry[attr]["label"],
                        "a": _fmt(a[attr], registry[attr].get("unit")),
                        "b": _fmt(b[attr], registry[attr].get("unit")),
                        "a_raw": a[attr],
                        "b_raw": b[attr],
                    }
                    for attr in shown
                ],
                "options": ["A", "B", "Genuinely can't choose"],
                "maps_to": {"kind": "weight_domain", "target": "all", "sets": "weights"},
            }
        )

    # Repeat a few tasks verbatim later on, to detect contradictions.
    for i, source in enumerate(rng.sample(tasks, min(spec.get("repeat_for_consistency", 0), len(tasks)))):
        echo = dict(source)
        echo["id"] = f"{source['id']}_repeat"
        echo["repeat_of"] = source["id"]
        tasks.append(echo)
    return tasks


def budget_question(spec: dict) -> list[dict]:
    domains = yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
    scoring = [d for d in domains if d.get("scoring")]
    return [
        {
            "id": "budget_allocation",
            "type": "budget",
            "text": f"Spread {spec['total']} points across these.",
            "help": "Everything you give one, you take from another. The total must come to "
                    f"{spec['total']}.",
            "total": spec["total"],
            "items": [{"id": d["id"], "label": d["label"], "description": d.get("description", "")}
                      for d in scoring],
            "maps_to": {"kind": "weight_domain", "target": "all", "sets": "budget"},
        }
    ]


def place_rating_question(spec: dict, wide: pl.DataFrame, *, seed: int = 11) -> list[dict]:
    """Candidate places the household plausibly knows: big metros plus Harrisburg's neighbours."""
    rng = random.Random(seed)
    biggest = wide.sort("population", descending=True).head(18).to_dicts()
    nearby = (
        wide.filter((pl.col("state_usps").is_in(["PA", "MD", "NJ", "NY", "DE", "VA"]))
                    & (pl.col("population") > 150_000))
        .sort("population", descending=True)
        .head(12)
        .to_dicts()
    )
    seen, places = set(), []
    for row in biggest + nearby:
        if row["geo_id"] in seen:
            continue
        seen.add(row["geo_id"])
        places.append({"geo_id": row["geo_id"], "name": f"{row['name']}, {row['state_usps']}"})

    if spec.get("include_baseline"):
        base = wide.filter(pl.col("geo_id") == BASELINE_COUNTY).to_dicts()
        if base and BASELINE_COUNTY not in seen:
            places.insert(0, {"geo_id": BASELINE_COUNTY,
                              "name": f"{base[0]['name']}, {base[0]['state_usps']}"})

    rng.shuffle(places)
    return [
        {
            "id": "calibration_ratings",
            "type": "rating_grid",
            "text": "Rate the ones you actually know, 1-10.",
            "help": "Skip anything you only know by reputation — a rating from what you've "
                    "read imports exactly the bias we're trying to remove.",
            "scale": spec["scale"],
            "allow_skip": spec.get("allow_skip", True),
            "places": places[: spec["count"]],
            "maps_to": {"kind": "qualitative_note", "target": "calibration"},
        }
    ]


# ------------------------------------------------------------------------- assembly

GENERATORS = {
    "anchored_band": lambda s, w, r: anchored_band_questions(s, w, r),
    "discrete_choice": lambda s, w, r: choice_tasks(s, w, r),
    "budget_allocation": lambda s, w, r: budget_question(s),
    "place_rating": lambda s, w, r: place_rating_question(s, w),
}


def build(bank: dict | None = None, wide: pl.DataFrame | None = None) -> list[dict]:
    """Flatten the bank into an ordered question list, expanding generated blocks."""
    bank = bank or load_bank()
    registry = load_registry()
    wide = wide if wide is not None else wide_counties()

    questions: list[dict] = []
    for section in bank["sections"]:
        header = {"id": section["id"], "title": section["title"],
                  "intro": section.get("intro", ""), "optional": section.get("optional", False)}
        for q in section.get("questions", []):
            questions.append({**q, "section": header})
        if "generated" in section:
            spec = section["generated"]
            for q in GENERATORS[spec["kind"]](spec, wide, registry):
                questions.append({**q, "section": header})
    return questions
