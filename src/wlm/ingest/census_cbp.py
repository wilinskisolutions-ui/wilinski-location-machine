"""County Business Patterns — amenity density.

Replaces OpenStreetMap/Overpass, which is egress-blocked. CBP is the stronger source
regardless: authoritative establishment counts from the business register, complete
national coverage, no rate limits, and identical treatment of a rural county and a metro
one — which matters, because uneven coverage is countermeasure #4 in `docs/anti-bias.md`.

NAICS in this file is padded to six characters with dashes and slashes marking the
aggregation level: `722///` is the 3-digit food-services group, `71----` the 2-digit
sector, `713940` a full 6-digit industry.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import polars as pl

from wlm.geo import county_geoid, is_in_scope
from wlm.ingest.base import emit

SOURCE_ID = "census_cbp"
VINTAGE = "2022"

# NAICS code as it appears in the file -> registered indicator id.
NAICS_MAP: dict[str, str] = {
    "722///": "amen_food_drink_per10k",
    "71----": "amen_arts_rec_per10k",
    "445///": "amen_grocery_per10k",
    "713940": "amen_fitness_per10k",
    "------": "amen_establishments_per10k",
}

# Absolute counts, alongside the per-capita rates.
#
# Per-capita alone measures amenities *per resident*, which spikes in tourist economies:
# San Juan County, Colorado (population 821, Silverton) shows 158 restaurants per 10,000
# against Manhattan's 57. That is not "more to do" — it is a ski town serving visitors.
# Variety and density are different questions and a couple asking "is there anything going
# on here" wants both, so both are measured. Log-transformed, since the difference between
# 20 and 200 venues matters far more than between 2,000 and 2,180.
NAICS_TOTALS: dict[str, str] = {
    "722///": "amen_food_drink_total",
    "71----": "amen_arts_rec_total",
}

# This comment said "so both are measured" as though registering the total settled it.
# It did not: the questionnaire's trade-off design only ever offered the per-10k attributes,
# so the totals could never earn a real weight and sat at the 0.05 floor while a per-10k
# indicator could reach 0.2+. A real household's answers reached this exact case — Emil's
# arts_rec_per10k weight came out at 0.22 against arts_rec_total's floor of 0.05 — and it put
# four-county Great Plains towns with a handful of venues ahead of Topeka, which has 55.
#
# The fix belongs here rather than in the elicitation design, because it should not depend
# on any one household happening to trade off on the total. A population floor on the rate's
# denominator is the same treatment MIN_POPULATION_FOR_RATE gives road-fatality rates in
# fars.py: below the floor, the rate stops climbing as population shrinks, so a county of a
# few hundred people cannot report a rate as if it served ten thousand. Established towns
# above the floor are untouched.
MIN_POPULATION_FOR_RATE = 10_000


def _rows(path: Path):
    path = Path(path)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith((".txt", ".csv")))
            with z.open(name) as fh:
                yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
    else:
        yield from csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())


def ingest(
    path: Path,
    population: dict[str, int],
    *,
    vintage: str = VINTAGE,
    naics_map: dict[str, str] | None = None,
) -> pl.DataFrame:
    """Establishments per 10,000 residents, by county.

    Per-capita rather than raw counts: otherwise this measures population, and every large
    county wins by construction.
    """
    naics_map = naics_map or NAICS_MAP
    records: list[dict] = []

    for row in _rows(path):
        naics = (row.get("naics") or "").strip()
        indicator = naics_map.get(naics)
        if indicator is None:
            continue
        try:
            geoid = county_geoid(row["fipstate"], row["fipscty"])
        except (KeyError, ValueError):
            continue
        if not is_in_scope(geoid):
            continue

        pop = population.get(geoid)
        try:
            establishments = float(row.get("est") or "")
        except ValueError:
            continue
        # No population means no per-capita rate. Missing, not zero (Principle 6). A
        # population below the floor still gets a rate, computed against the floor rather
        # than the true (tiny) count, so the number cannot claim an implausible density.
        value = (establishments / max(pop, MIN_POPULATION_FOR_RATE) * 10_000) if pop else None

        records.append(
            {"geo_level": "county", "geo_id": geoid, "indicator_id": indicator, "value": value}
        )
        if (total_indicator := NAICS_TOTALS.get(naics)) is not None:
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": geoid,
                    "indicator_id": total_indicator,
                    "value": establishments,
                }
            )

    return emit(records, source_file=Path(path).name, vintage=vintage)
