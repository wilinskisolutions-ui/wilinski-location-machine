"""USDA ERS Natural Amenities Scale ingest.

A small county table combining climate, topography and water area into one index. The 1999
vintage is old and deliberately used anyway: it measures terrain and water, which do not
move. It is the floor case for the ingest contract — one file, one indicator.
"""

from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "usda_amenities"

FIPS_COLUMNS = ("FIPS", "FIPS CODE", "FIPSCODE", "GEOID", "STCOFIPS")
SCALE_COLUMNS = ("NATURAL AMENITIES SCALE", "SCALE", "AMENITY_SCALE", "NAT_AMEN_SCALE")


def _read(path: Path) -> list[dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8-sig")
    return [
        {(k or "").strip().upper(): (v or "").strip() for k, v in rec.items()}
        for rec in csv.DictReader(text.splitlines())
    ]


def ingest(path: Path, *, vintage: str = "1999") -> pl.DataFrame:
    records: list[dict] = []

    for row in _read(path):
        raw_fips = next((row[c] for c in FIPS_COLUMNS if row.get(c)), None)
        scale = next((row[c] for c in SCALE_COLUMNS if row.get(c) is not None), None)
        if not raw_fips:
            continue
        geoid = norm_fips(raw_fips, 5)
        if not is_in_scope(geoid):
            continue
        records.append(
            {
                "geo_level": "county",
                "geo_id": geoid,
                "indicator_id": "env_natural_amenities",
                "value": scale if scale not in (None, "") else None,
            }
        )

    return emit(records, source_file=Path(path).name, vintage=vintage)
