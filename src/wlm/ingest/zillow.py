"""Zillow home values (ZHVI) and rents (ZORI).

Uses the **county** files rather than the metro ones: they join straight onto the universe
with no CBSA crosswalk, and county is the level most other indicators sit at.

The files are wide — one column per month back to 2000 — so the reader walks backwards from
the last column to the most recent non-null value per county. Zillow suppresses thin
markets, and a suppressed county must stay missing rather than inherit a stale 2019 price.
"""

from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from wlm.geo import county_geoid, is_in_scope
from wlm.ingest.base import emit

SOURCE_ID = "zillow_research"

STATE_COL, COUNTY_COL = "StateCodeFIPS", "MunicipalCodeFIPS"


def _latest(row: dict[str, str], date_columns: list[str]) -> float | None:
    for column in reversed(date_columns):
        raw = (row.get(column) or "").strip()
        if raw:
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def ingest(path: Path, indicator_id: str, *, vintage: str) -> pl.DataFrame:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(text.splitlines())
    fields = reader.fieldnames or []
    # Month columns look like 2024-06-30; everything else is metadata.
    date_columns = [f for f in fields if len(f) == 10 and f[4] == "-" and f[:4].isdigit()]

    records: list[dict] = []
    for row in reader:
        state, county = (row.get(STATE_COL) or "").strip(), (row.get(COUNTY_COL) or "").strip()
        if not state or not county:
            continue
        try:
            geoid = county_geoid(state, county)
        except ValueError:
            continue
        if not is_in_scope(geoid):
            continue
        records.append(
            {
                "geo_level": "county",
                "geo_id": geoid,
                "indicator_id": indicator_id,
                "value": _latest(row, date_columns),
            }
        )

    return emit(records, source_file=Path(path).name, vintage=vintage)
