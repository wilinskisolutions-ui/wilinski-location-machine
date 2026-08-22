"""Census Population Estimates Program.

Two files, two jobs:

- `co-est2024-alldata.csv` — county population, the most current official estimate.
- `sub-est2024.csv` — sub-county estimates. `SUMLEV 162` rows are place totals;
  **`SUMLEV 157` rows are place x county**, and that is what supplies real population
  weights for places straddling county lines.

PEP covers incorporated places and minor civil divisions only: of its 19,479 place rows,
19,465 are active incorporated. **Census designated places are absent entirely**, so CDP
population comes from the ACS bulk table instead (see `census_acs.population_from_bulk`).
"""

from __future__ import annotations

import csv
from pathlib import Path

from wlm.geo import county_geoid, is_in_scope, place_geoid

SOURCE_ID = "census_pep"

SUMLEV_COUNTY = "050"
SUMLEV_PLACE = "162"
SUMLEV_PLACE_COUNTY = "157"

POP_COLUMN = "POPESTIMATE2024"


def _rows(path: Path) -> list[dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    return [
        {(k or "").strip().upper(): (v or "").strip() for k, v in rec.items()}
        for rec in csv.DictReader(text.splitlines())
    ]


def _int(value: str | None) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def county_population(path: Path, column: str = POP_COLUMN) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in _rows(path):
        if row.get("SUMLEV") != SUMLEV_COUNTY:
            continue
        geoid = county_geoid(row["STATE"], row["COUNTY"])
        if not is_in_scope(geoid):
            continue
        if (pop := _int(row.get(column))) is not None:
            out[geoid] = pop
    return out


def place_population(path: Path, column: str = POP_COLUMN) -> dict[str, int]:
    """Incorporated-place population. CDPs are not present in this file."""
    out: dict[str, int] = {}
    for row in _rows(path):
        if row.get("SUMLEV") != SUMLEV_PLACE:
            continue
        geoid = place_geoid(row["STATE"], row["PLACE"])
        if not is_in_scope(geoid):
            continue
        if (pop := _int(row.get(column))) is not None:
            out[geoid] = pop
    return out


def place_county_weights(path: Path, column: str = POP_COLUMN) -> list[dict]:
    """Place x county population, for the crosswalk.

    Returns rows shaped for `PlaceCountyCrosswalk.from_rows`, using the population of the
    place's part in each county as the weight. Only incorporated places appear here.
    """
    rows: list[dict] = []
    for row in _rows(path):
        if row.get("SUMLEV") != SUMLEV_PLACE_COUNTY:
            continue
        place = place_geoid(row["STATE"], row["PLACE"])
        county = county_geoid(row["STATE"], row["COUNTY"])
        if not is_in_scope(place):
            continue
        pop = _int(row.get(column))
        if pop is None:
            continue
        rows.append({"place_geoid": place, "county_geoid": county, "weight": pop})
    return rows
