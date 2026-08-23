"""County presidential margin, for the sensitive layer only.

`sens_partisan_lean` exists because of the stacking trap in `docs/anti-bias.md`: a
conservative preference points at the same Sunbelt metros the internet already over-promotes,
so the *cost* of that filter has to be measurable. County granularity is the substantive part
— partisan lean varies far more within states than between them, and there are strongly
conservative counties in Oregon, Michigan and Pennsylvania whose climate and cost profiles
look nothing like Texas. A state-level heuristic cannot see them.

This indicator is `direction: personal` and sits at weight zero unless explicitly opted into
(Principle 10), and the engine drops it outright when it is not.

**On the source.** The authoritative file is MIT Election Data and Science Lab, *County
Presidential Election Returns 2000-2024*, `doi:10.7910/DVN/VOQCHQ`, file 13573089. Harvard
Dataverse will not serve it without a guestbook response — a form, the same class of gate
that blocks SEDA — and the household chose not to fill one in. So the numbers come from a
long-standing public mirror of the same returns, recorded under its own source id rather
than filed as though it were MIT's own copy. The DOI is kept here so the provenance names
both what was used and what it stands in for, and so swapping in the authoritative file
later is a one-line change.

Margin is signed: positive means the Republican candidate led, negative the Democratic one.
Sign matters because the curve is `ideal_point` — the household names a position, and
distance from it is what scores, so the axis must have two directions.
"""

from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "countypres_mirror"
MIRRORS = "https://raw.githubusercontent.com/tonmcg/US_County_Level_Election_Results_08-24/master"

# What this mirrors, kept so provenance names the authoritative record.
AUTHORITATIVE = "doi:10.7910/DVN/VOQCHQ (MIT Election Data and Science Lab), file 13573089"

FILES = {2024: "2024_US_County_Level_Presidential_Results.csv",
         2020: "2020_US_County_Level_Presidential_Results.csv"}

VINTAGE = "2024"

# Alaska is excluded, and the reason is a trap rather than a gap.
#
# Alaska does not report presidential results by borough — it reports by State House
# District, and this file numbers those districts 02001-02040 in the county FIPS column.
# Three of them collide exactly with real borough codes: 02013 is Aleutians East Borough but
# House District 13, 02016 is Aleutians West, and **02020 is Anchorage Municipality** — so a
# straight join would have handed Alaska's largest population centre the politics of one
# small district inside it, and the number would have looked entirely reasonable.
#
# Twenty-eight boroughs therefore have no value here. That is reported, not patched: an
# invented Alaskan margin would be exactly the kind of number Principle 4 forbids.
EXCLUDED_STATES = {"02"}


def urls() -> list[str]:
    return [f"{MIRRORS}/{name}" for name in FILES.values()]


def _read(path: Path) -> dict[str, float]:
    """county GEOID -> signed two-party margin, as a share."""
    out: dict[str, float] = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("county_fips") or "").strip()
            if not raw.isdigit():
                continue
            geoid = norm_fips(raw, 5)
            if not is_in_scope(geoid) or geoid[:2] in EXCLUDED_STATES:
                continue
            try:
                gop, dem = float(row["per_gop"]), float(row["per_dem"])
            except (TypeError, ValueError, KeyError):
                continue
            total = gop + dem
            if total <= 0:
                continue
            # Two-party margin, renormalised so third parties do not shift the axis.
            out[geoid] = (gop - dem) / total
    return out


def ingest(folder: Path, *, year: int = 2024, vintage: str = VINTAGE) -> tuple[pl.DataFrame, dict]:
    folder = Path(folder)
    margins = _read(folder / FILES[year])

    records = [
        {"geo_level": "county", "geo_id": geoid,
         "indicator_id": "sens_partisan_lean", "value": margin}
        for geoid, margin in sorted(margins.items())
    ]
    stats = {
        "counties": len(records),
        "year": year,
        "excluded_states": sorted(EXCLUDED_STATES),
        "mirrors": AUTHORITATIVE,
        # Reported so a coverage gap is visible rather than inferred from a row count.
        "most_republican": max(margins.values()) if margins else None,
        "most_democratic": min(margins.values()) if margins else None,
    }
    return emit(records, source_file=FILES[year], vintage=vintage), stats
