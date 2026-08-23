"""EPA Air Quality System — annual PM2.5 by county.

Readings are per monitor, so counties with several monitors get several rows. Those are
averaged; a county with no monitor is left missing rather than borrowing a neighbour's air,
which would understate exactly the rural counties least likely to be measured.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path

import polars as pl

from wlm.geo import county_geoid, is_in_scope
from wlm.ingest.base import emit

SOURCE_ID = "epa_aqs"
VINTAGE = "2024"

PM25_PARAMETER = "PM2.5 - Local Conditions"
PREFERRED_METRIC = "Daily Mean"


def _rows(path: Path):
    path = Path(path)
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            with z.open(name) as fh:
                yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))
    else:
        yield from csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())


def ingest(path: Path, *, vintage: str = VINTAGE) -> tuple[pl.DataFrame, dict]:
    totals: dict[str, list[float]] = defaultdict(list)

    for row in _rows(path):
        if (row.get("Parameter Name") or "").strip() != PM25_PARAMETER:
            continue
        if PREFERRED_METRIC not in (row.get("Metric Used") or ""):
            continue
        try:
            geoid = county_geoid(row["State Code"], row["County Code"])
            value = float(row["Arithmetic Mean"])
        except (KeyError, ValueError):
            continue
        if is_in_scope(geoid):
            totals[geoid].append(value)

    records = [
        {
            "geo_level": "county",
            "geo_id": geoid,
            "indicator_id": "env_pm25_annual",
            "value": sum(vals) / len(vals),
        }
        for geoid, vals in totals.items()
    ]
    return emit(records, source_file=Path(path).name, vintage=vintage), {
        "counties_with_monitors": len(totals)
    }
