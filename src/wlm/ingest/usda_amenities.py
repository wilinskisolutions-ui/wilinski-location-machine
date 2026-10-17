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


# The ERS workbook (`.xls`) carries ~100 rows of notes above a two-line header, so columns
# are taken by position — verified against the header row on 2026-10-15:
#   col 0 "FIPS Code", col 11 "topography code", col 12 "Percent Water area",
#   col 20 "Natural amenity Scale".
XLS_COLUMNS = {"FIPS": 0, "TOPOGRAPHY": 11, "WATER PERCENT": 12, "SCALE": 20}

# The header sat at row 104 when this was written, and the row number was hardcoded. It is
# now searched for instead: a hardcoded row breaks the moment ERS adds or removes a line of
# notes, and the whole point of the preamble is that it is prose someone edits.
FIPS_HEADER = "fips code"
HEADER_SEARCH_ROWS = 400


def _header_row(sheet) -> int:
    for row in range(min(sheet.nrows, HEADER_SEARCH_ROWS)):
        if str(sheet.cell_value(row, 0)).strip().lower() == FIPS_HEADER:
            return row
    raise ValueError(
        f"{SOURCE_ID}: no '{FIPS_HEADER}' header in the first {HEADER_SEARCH_ROWS} rows"
    )


def _read_xls(path: Path) -> list[dict[str, str]]:
    import xlrd

    sheet = xlrd.open_workbook(str(path)).sheet_by_index(0)
    start = _header_row(sheet)
    header = [str(c.value).strip().upper() for c in sheet.row(start)]
    expected = {11: "TOPOGRAPHY CODE", 12: "WATER AREA", 20: "SCALE"}
    moved = {i: header[i] for i, want in expected.items() if header[i] != want}
    if moved:
        raise ValueError(f"{path.name}: header moved, got {moved}")
    rows = []
    for r in range(start + 1, sheet.nrows):
        cells = sheet.row(r)
        rows.append({k: str(cells[i].value).strip() for k, i in XLS_COLUMNS.items()})
    return rows


def _read(path: Path) -> list[dict[str, str]]:
    if Path(path).suffix.lower() == ".xls":
        return _read_xls(path)
    text = Path(path).read_text(encoding="utf-8-sig")
    return [
        {(k or "").strip().upper(): (v or "").strip() for k, v in rec.items()}
        for rec in csv.DictReader(text.splitlines())
    ]


def _number(raw: str | None) -> float | None:
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


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
        water = _number(row.get("WATER PERCENT"))
        if "WATER PERCENT" in row:
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": geoid,
                    "indicator_id": "env_water_area_share",
                    # Published as a percentage; the registry declares this a share.
                    "value": None if water is None else water / 100.0,
                }
            )
        if "TOPOGRAPHY" in row:
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": geoid,
                    "indicator_id": "env_topographic_variation",
                    "value": _number(row.get("TOPOGRAPHY")),
                }
            )

    return emit(records, source_file=Path(path).name, vintage=vintage)
