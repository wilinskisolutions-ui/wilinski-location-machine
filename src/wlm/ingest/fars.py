"""NHTSA FARS — road fatalities by county.

Per-capita road death rates run several times higher in rural counties than dense metros
and frequently exceed the absolute risk difference from crime, which is why safety was
broadened beyond crime in Phase 1. This is that indicator.

FARS is a crash census rather than a survey: every fatal crash on a public road is in here,
so coverage does not have the voluntary-reporting gaps that FBI crime data does.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter
from pathlib import Path

import polars as pl

from wlm.geo import county_geoid, is_in_scope
from wlm.ingest.base import emit

SOURCE_ID = "nhtsa_fars"
VINTAGE = "2023"

MEMBER = "accident.csv"
# FARS uses 999/998 for unknown county rather than leaving the field blank.
UNKNOWN_COUNTY = {"0", "999", "998", "997"}

# Minimum population for a per-capita rate to mean anything.
#
# Places carry a 5,000 floor but counties do not, and the smallest are tiny: Loving County,
# Texas has about 64 residents, so a couple of deaths on the highway running through it
# produced 6,250 per 100,000 -- the highest in the country by two orders of magnitude, and
# entirely an artifact of the denominator. Those deaths are mostly pass-through traffic,
# not residents.
#
# Below this threshold the rate is left missing rather than published as a number that
# would dominate any ranking it entered. This is the same reasoning CDC applies to its own
# small-count suppression.
MIN_POPULATION_FOR_RATE = 1_000


def _rows(path: Path):
    with zipfile.ZipFile(Path(path)) as z:
        name = next(n for n in z.namelist() if n.endswith(MEMBER))
        with z.open(name) as fh:
            # FARS ships latin-1, not utf-8.
            yield from csv.DictReader(io.TextIOWrapper(fh, encoding="latin-1", errors="replace"))


def ingest(
    path: Path, population: dict[str, int], *, vintage: str = VINTAGE
) -> tuple[pl.DataFrame, dict]:
    deaths: Counter[str] = Counter()
    unknown = 0

    for row in _rows(path):
        state, county = (row.get("STATE") or "").strip(), (row.get("COUNTY") or "").strip()
        if county in UNKNOWN_COUNTY or not state:
            unknown += 1
            continue
        try:
            geoid = county_geoid(state, county)
            fatals = int(float(row.get("FATALS") or 0))
        except ValueError:
            continue
        if is_in_scope(geoid):
            deaths[geoid] += fatals

    records = []
    too_small = 0
    for geoid, pop in population.items():
        # A county with no fatal crash genuinely had none, so zero is a real value here —
        # unlike a missing measurement. But a rate needs a usable denominator.
        if not pop:
            value = None
        elif pop < MIN_POPULATION_FOR_RATE:
            value = None
            too_small += 1
        else:
            value = deaths.get(geoid, 0) / pop * 100_000
        records.append(
            {
                "geo_level": "county",
                "geo_id": geoid,
                "indicator_id": "safety_traffic_fatality_rate",
                "value": value,
            }
        )

    return emit(records, source_file=Path(path).name, vintage=vintage), {
        "counties_with_deaths": len(deaths),
        "crashes_unknown_county": unknown,
        "counties_below_rate_threshold": too_small,
    }
