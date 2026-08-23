"""County Health Rankings — one file, many domains.

The highest value per line of code in the whole pipeline: a single county CSV carrying
health outcomes, provider access, social capital, recreation access and unemployment.
Columns are `5-digit FIPS Code` plus `<Measure> raw value`, so adding an indicator later
means adding one line to MEASURE_MAP.

Compiled by the Robert Wood Johnson Foundation from federal sources (NCHS, BLS, CMS and
others), which is why it can cover measures that would otherwise be five separate ingests.
"""

from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "chr_rwjf"
VINTAGE = "2025"

FIPS_COLUMN = "5-digit FIPS Code"

# Indicators where CHR's orientation is the reciprocal of the registry's.
INVERT = {"health_pcp_ratio"}

# CHR measure name -> registered indicator id.
MEASURE_MAP: dict[str, str] = {
    "Life Expectancy raw value": "health_life_expectancy",
    "Primary Care Physicians raw value": "health_pcp_ratio",
    "Social Associations raw value": "comm_social_associations",
    "Access to Parks raw value": "rec_park_access",
    "Unemployment raw value": "econ_unemployment_rate",
}


def _rows(path: Path) -> list[dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(text.splitlines()))


def available_measures(path: Path) -> list[str]:
    """Every `… raw value` column in the file — used when adding indicators."""
    rows = _rows(path)
    return sorted(k for k in (rows[0] if rows else {}) if k.endswith("raw value"))


def ingest(
    path: Path, *, vintage: str = VINTAGE, measure_map: dict[str, str] | None = None
) -> tuple[pl.DataFrame, dict]:
    measure_map = measure_map or MEASURE_MAP
    rows = _rows(path)
    present = {m: i for m, i in measure_map.items() if rows and m in rows[0]}
    absent = sorted(set(measure_map) - set(present))

    records: list[dict] = []
    for row in rows:
        raw = (row.get(FIPS_COLUMN) or "").strip()
        if not raw or not raw.isdigit():
            continue
        geoid = norm_fips(raw, 5)
        # CHR includes state rollup rows with county part "000"; those are not counties.
        if geoid.endswith("000") or not is_in_scope(geoid):
            continue
        for measure, indicator in present.items():
            value = (row.get(measure) or "").strip()
            parsed = None
            if value != "":
                try:
                    parsed = float(value)
                except ValueError:
                    parsed = None
            if parsed is not None and indicator in INVERT:
                # CHR publishes providers per head; the registry asks for people per
                # provider, which is what "lower is better" means for this indicator.
                parsed = (1.0 / parsed) if parsed > 0 else None
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": geoid,
                    "indicator_id": indicator,
                    "value": parsed,
                }
            )

    return emit(records, source_file=Path(path).name, vintage=vintage), {
        "measures_found": len(present),
        "measures_absent": absent,
    }
