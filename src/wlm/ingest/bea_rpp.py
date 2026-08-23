"""BEA Regional Price Parities — what a dollar actually buys.

The only cost indicator published at metro rather than county level, so it needs the CBSA
crosswalk. Counties outside any metro area have no RPP and are left missing rather than
assigned the national average, which would flatter rural places on the exact dimension
being measured.

RPP is the right cost measure to pair with income: nominal wages in an expensive metro and
a cheap one are not comparable, and this is the deflator that makes them so.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import polars as pl

from wlm.ingest.base import emit

SOURCE_ID = "bea_rpp"
VINTAGE = "2023"

MEMBER = "MARPP_MSA_2008_2024.csv"
LINE_ALL_ITEMS = "1"


def _rows(path: Path):
    with zipfile.ZipFile(Path(path)) as z:
        name = next(n for n in z.namelist() if n.endswith(MEMBER))
        with z.open(name) as fh:
            yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", errors="replace"))


def ingest(
    path: Path,
    cbsa_by_county: dict[str, tuple[str, str]],
    *,
    vintage: str = VINTAGE,
    year: str = "2023",
) -> tuple[pl.DataFrame, dict]:
    by_cbsa: dict[str, float] = {}

    for row in _rows(path):
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if norm.get("linecode") != LINE_ALL_ITEMS:
            continue
        geofips = norm.get("geofips", "").strip('"')
        value = norm.get(year)
        if not geofips or not value:
            continue
        try:
            by_cbsa[geofips] = float(value)
        except ValueError:
            continue

    records: list[dict] = []
    matched = 0
    for county, (cbsa, _title) in cbsa_by_county.items():
        value = by_cbsa.get(cbsa)
        matched += value is not None
        records.append(
            {
                "geo_level": "county",
                "geo_id": county,
                "indicator_id": "cost_price_parity",
                "value": value,
            }
        )

    return emit(records, source_file=Path(path).name, vintage=vintage), {
        "metros_in_file": len(by_cbsa),
        "counties_matched": matched,
        "counties_in_metros": len(cbsa_by_county),
    }
