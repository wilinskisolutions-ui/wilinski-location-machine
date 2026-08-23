"""BLS Quarterly Census of Employment and Wages — annual county file.

Two indicators come out of it:

- **Industry diversity**, as the inverse Herfindahl index of employment across NAICS
  sectors. A county whose jobs sit in one sector is fragile in a way average wages do not
  reveal; this is a resilience measure, not a prosperity one.
- **Employment growth**, comparing two annual files.

The file is a 75MB single-file dump covering every aggregation level, so the reader filters
hard: `agglvl_code` 74 is county-by-NAICS-sector, 70 is the county total.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "bls_qcew"

AGGLVL_COUNTY_SECTOR = "74"
AGGLVL_COUNTY_TOTAL = "70"
OWN_TOTAL = "0"


def _rows(path: Path):
    with zipfile.ZipFile(Path(path)) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        with z.open(name) as fh:
            yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))


def read_county_employment(path: Path) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """Return (employment by sector per county, total employment per county)."""
    by_sector: dict[str, dict[str, float]] = defaultdict(dict)
    totals: dict[str, float] = {}

    for row in _rows(path):
        area = (row.get("area_fips") or "").strip()
        if len(area) != 5 or not area.isdigit() or not is_in_scope(area):
            continue
        agglvl = (row.get("agglvl_code") or "").strip()
        try:
            emp = float(row.get("annual_avg_emplvl") or 0)
        except ValueError:
            continue

        if agglvl == AGGLVL_COUNTY_TOTAL and (row.get("own_code") or "").strip() == OWN_TOTAL:
            totals[norm_fips(area, 5)] = emp
        elif agglvl == AGGLVL_COUNTY_SECTOR:
            sector = (row.get("industry_code") or "").strip()
            if sector:
                by_sector[norm_fips(area, 5)][sector] = (
                    by_sector[norm_fips(area, 5)].get(sector, 0.0) + emp
                )
    return by_sector, totals


def diversity(sector_employment: dict[str, float]) -> float | None:
    """Inverse Herfindahl: roughly the effective number of sectors employing people."""
    total = sum(sector_employment.values())
    if total <= 0:
        return None
    hhi = sum((emp / total) ** 2 for emp in sector_employment.values() if emp > 0)
    return (1.0 / hhi) if hhi > 0 else None


def ingest(
    path: Path, *, vintage: str, prior: Path | None = None
) -> tuple[pl.DataFrame, dict]:
    by_sector, totals = read_county_employment(path)
    records: list[dict] = []

    for geoid, sectors in by_sector.items():
        records.append(
            {
                "geo_level": "county",
                "geo_id": geoid,
                "indicator_id": "econ_industry_diversity",
                "value": diversity(sectors),
            }
        )

    stats = {"counties_with_sectors": len(by_sector), "counties_with_totals": len(totals)}

    if prior is not None and Path(prior).exists():
        _, prior_totals = read_county_employment(Path(prior))
        grown = 0
        for geoid, now in totals.items():
            then = prior_totals.get(geoid)
            value = ((now - then) / then * 100.0) if (then and then > 0) else None
            grown += value is not None
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": geoid,
                    "indicator_id": "econ_employment_growth_5y",
                    "value": value,
                }
            )
        stats["counties_with_growth"] = grown

    return emit(records, source_file=Path(path).name, vintage=vintage), stats
