"""FEMA National Risk Index ingest.

One wide county CSV carrying 18 hazards as expected-annual-loss scores. This is the source
that turns "is Florida risky?" from a vibe into a number, and it is the cleanest of the
county files — one row per county, a ready-made 5-digit STCOFIPS.
"""

from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "fema_nri"

# NRI column -> registered indicator id. `*_RISKS` columns are composite risk scores.
HAZARD_MAP: dict[str, str] = {
    "RISK_SCORE": "hazard_nri_composite",
    "HRCN_RISKS": "hazard_nri_hurricane",
    "WFIR_RISKS": "hazard_nri_wildfire",
}

FIPS_COLUMNS = ("STCOFIPS", "STCOFIPS5", "GEOID")


def _read(path: Path) -> list[dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8-sig")
    return [
        {(k or "").strip().upper(): (v or "").strip() for k, v in rec.items()}
        for rec in csv.DictReader(text.splitlines())
    ]


def ingest(path: Path, *, vintage: str = "2023", hazard_map: dict[str, str] | None = None) -> pl.DataFrame:
    hazard_map = hazard_map or HAZARD_MAP
    records: list[dict] = []

    for row in _read(path):
        raw_fips = next((row[c] for c in FIPS_COLUMNS if row.get(c)), None)
        if not raw_fips:
            continue
        geoid = norm_fips(raw_fips, 5)
        if not is_in_scope(geoid):
            continue
        for column, indicator_id in hazard_map.items():
            if column not in row:
                continue
            raw = row[column]
            # NRI leaves cells blank where a hazard does not apply to a county. Blank is
            # missing, not zero — a county with no wildfire exposure and a county FEMA did
            # not assess are different things (Principle 6).
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": geoid,
                    "indicator_id": indicator_id,
                    "value": raw if raw != "" else None,
                }
            )

    return emit(records, source_file=Path(path).name, vintage=vintage)
