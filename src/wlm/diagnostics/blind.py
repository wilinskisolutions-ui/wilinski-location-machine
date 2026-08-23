"""Countermeasure #5: strip the names off the shortlist.

Emil and Winsor have already heard of Raleigh. They have opinions about Florida. Those
opinions arrived through the same channels this project exists to route around, so a
shortlist read with the names attached is partly a test of what they already believe.

So the shortlist is also exported without them: population, climate, costs, the indicator
values — and no name, no state, no GEOID. They rank the profiles cold, and only then are the
names revealed. A profile they love that turns out to be somewhere they had written off is
the single most useful thing this whole exercise can produce.

The export is checked rather than trusted. One leaked name defeats the exercise entirely,
and it is easy to leak one by accident — a county name inside a source filename, a state
code in a formatted string — so `find_leaks` re-reads the finished export and looks for
every name and code in the universe.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
import yaml

from wlm.paths import CONFIG, OUTPUT, PROCESSED, UNIVERSE
from wlm.units import fmt

# The export is built from an allowlist rather than by removing identifying columns: a
# profile carries only what `PROFILE_INDICATORS` names, so a new column added to the
# universe cannot leak by default. `find_leaks` then checks the result anyway.
#
# Indicators worth showing a human deciding blind. Anything whose value effectively names
# the place — a state-level tax rate, a single-metro airport count — stays out.
PROFILE_INDICATORS = (
    "climate_temp_winter_mean", "climate_temp_summer_mean",
    "climate_annual_precip", "climate_annual_snowfall",
    "cost_home_value_median", "cost_rent_median_zori",
    "form_population_density", "form_mean_commute",
    "amen_food_drink_per10k", "amen_arts_rec_per10k",
    "health_life_expectancy", "safety_traffic_fatality_rate",
    "env_pm25_annual", "hazard_fatality_risk_per100k",
    "econ_unemployment_rate",
)


@dataclass
class BlindExport:
    profiles: list[dict] = field(default_factory=list)
    key: dict[str, str] = field(default_factory=dict)
    leaks: list[str] = field(default_factory=list)


def _registry() -> dict[str, dict]:
    return {
        i["id"]: i
        for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]
    }


def strip(
    shortlist: list[str],
    *,
    features: pl.DataFrame,
    universe: pl.DataFrame,
    registry: dict[str, dict] | None = None,
) -> BlindExport:
    """Turn a shortlist of geo_ids into anonymous profiles plus a sealed key."""
    registry = registry or _registry()
    export = BlindExport()

    wanted = [i for i in PROFILE_INDICATORS if i in registry]
    rows = features.filter(
        pl.col("geo_id").is_in(shortlist) & pl.col("indicator_id").is_in(wanted)
    )
    populations = dict(universe.select(["geo_id", "population"]).iter_rows())
    names = {
        r["geo_id"]: f"{r['name']}, {r['state_usps']}"
        for r in universe.select(["geo_id", "name", "state_usps"]).iter_rows(named=True)
    }

    for position, geo_id in enumerate(shortlist, start=1):
        label = f"Place {chr(64 + position)}" if position <= 26 else f"Place {position}"
        values = {
            r["indicator_id"]: r["value"]
            for r in rows.filter(pl.col("geo_id") == geo_id).iter_rows(named=True)
        }
        export.profiles.append(
            {
                "label": label,
                "population": populations.get(geo_id),
                # Missing stays missing here too: an absent indicator is shown as absent
                # rather than filled in, or the blind reader is judging a different place.
                # Formatted through wlm.units, because a rate shown as "0.0" is not a
                # profile anyone can rank.
                "values": {
                    registry[i].get("label", i): fmt(values.get(i), registry[i].get("unit"))
                    for i in wanted
                },
            }
        )
        export.key[label] = names.get(geo_id, geo_id)

    export.leaks = find_leaks(export.profiles, universe)
    return export


def _text_and_numbers(node, strings: list[str], numbers: set[float]) -> None:
    """Split the export into the words in it and the numbers in it.

    Searching the raw JSON conflated the two: "05025" matched inside a population of
    105,025 and reported Cleveland County, Arkansas as a leak from a shortlist that never
    contained it. A number cannot leak a name — only a string can — while a GEOID stored
    as a number is a genuine leak, so the two are checked differently.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            strings.append(str(key))
            _text_and_numbers(value, strings, numbers)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _text_and_numbers(item, strings, numbers)
    elif isinstance(node, str):
        strings.append(node)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        numbers.add(float(node))


def find_leaks(profiles: list[dict], universe: pl.DataFrame) -> list[str]:
    """Look for anything in the export that would give a place away.

    Checked against the whole universe rather than only the shortlist, because a leak is
    just as damaging when it names a neighbouring county.
    """
    strings: list[str] = []
    numbers: set[float] = set()
    _text_and_numbers(profiles, strings, numbers)
    text = " ".join(strings)
    leaks = []

    # Place and county names. Short ones ("Lee", "Polk") appear inside ordinary words, so
    # match on word boundaries and skip anything too short to be conclusive.
    for name in universe["name"].unique():
        stem = re.sub(r"\s+(County|Parish|Borough|city|town|CDP|Census Area)$", "", name)
        if len(stem) < 5:
            continue
        if re.search(rf"\b{re.escape(stem)}\b", text):
            leaks.append(f"place name '{stem}'")

    # State codes as standalone tokens, and GEOIDs anywhere at all.
    for code in universe["state_usps"].unique():
        if code and re.search(rf"\b{re.escape(code)}\b", text):
            leaks.append(f"state code '{code}'")
    # A GEOID leaks either as its own string token or as a bare number.
    tokens = set(re.findall(r"\b\d{5,10}\b", text))
    for geo_id in universe["geo_id"]:
        if geo_id in tokens or float(geo_id) in numbers:
            leaks.append(f"GEOID '{geo_id}'")
            break  # one is enough to fail the export

    return sorted(set(leaks))


def render(export: BlindExport) -> str:
    lines = [
        "# Blind shortlist",
        "",
        "Rank these before looking at the key. The names are withheld on purpose: a",
        "shortlist read with them attached is partly a test of what you already believe",
        "about the places, which is the bias this whole project routes around.",
        "",
        "Write your order down first. Then open `blind-key.json`.",
        "",
    ]
    if export.leaks:
        lines += [
            "> **This export leaked and must not be used.** " + "; ".join(export.leaks),
            "",
        ]

    for profile in export.profiles:
        lines += [f"## {profile['label']}", ""]
        population = profile["population"]
        lines.append(f"- Population: {population:,}" if population else "- Population: unknown")
        for label, shown in profile["values"].items():
            lines.append(
                f"- {label}: not measured here" if shown == "—" else f"- {label}: {shown}"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def build(shortlist: list[str] | None = None, *, write: bool = True) -> str:
    from wlm.paths import FEATURES

    universe = pl.read_parquet(UNIVERSE)
    features = pl.read_parquet(FEATURES)

    if shortlist is None:
        candidates = sorted(PROCESSED.glob("scores-county-*.parquet"))
        if not candidates:
            return "# Blind shortlist\n\nNo scores found; run `make score` first.\n"
        shortlist = list(pl.read_parquet(candidates[0]).head(12)["geo_id"])

    export = strip(shortlist, features=features, universe=universe)
    text = render(export)
    if write:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "blind.md").write_text(text)
        # The key is written separately so reading the shortlist does not reveal it.
        (OUTPUT / "blind-key.json").write_text(json.dumps(export.key, indent=2))
    return text


if __name__ == "__main__":
    print(build())
