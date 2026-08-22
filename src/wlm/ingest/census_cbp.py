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
        # No population means no per-capita rate. Missing, not zero (Principle 6).
        value = (establishments / pop * 10_000) if pop else None

        records.append(
            {"geo_level": "county", "geo_id": geoid, "indicator_id": indicator, "value": value}
        )

    return emit(records, source_file=Path(path).name, vintage=vintage)
