"""Religious adherence per county, from the 2020 US Religion Census.

Feeds `sens_religious_adherence`, which is `direction: personal` and sits at weight zero
unless explicitly opted into (Principle 10). There is no better or worse end of this axis —
the household names a position and distance from it is what scores.

**On the source.** ARDA hosts this dataset but exposes no link a script can follow; its
archive pages are built client-side. The Religion Census publishes the same tabulation
directly as a workbook, and its `2020 County Summary` sheet carries FIPS and adherents as a
share of population for 3,147 counties, which is exactly the column needed. So the fetch
goes there rather than to ARDA, and `arda_religion` stays registered as the archive of
record.

Adherents include children and non-attending members where a body reports them, so this
measures affiliation rather than observance. Two counties with the same share can feel
entirely different, which is a reason to treat it as one weak signal among several.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "usreligioncensus"
URL = "https://www.usreligioncensus.org/sites/default/files/2023-06/2020_USRC_Summaries.xlsx"
SHEET = "2020 County Summary"
VINTAGE = "2020"

# Adherents are counted where a congregation sits, not where its members live, so a rural
# county whose churches draw from the surrounding area can report more adherents than
# residents. Thirty counties exceed 100%, King County, Texas at 452% of its 215 people.
# Above 1.0 the figure is not a share of this county's population and does not measure what
# the indicator claims, so it becomes missing rather than clipped to a plausible-looking
# number (Principle 6).
MAX_PLAUSIBLE_SHARE = 1.0


def ingest(path: Path, *, vintage: str = VINTAGE) -> tuple[pl.DataFrame, dict]:
    import openpyxl

    workbook = openpyxl.load_workbook(Path(path), read_only=True, data_only=True)
    sheet = workbook[SHEET]
    rows = sheet.iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows)]
    index = {name: position for position, name in enumerate(header)}

    # Derived from the two counts rather than read from the sheet's own share column.
    # That column is named "Adherents as % of Population" but holds a 0-1 fraction, and
    # taking the name at its word divided it by 100 again: a country that is roughly half
    # affiliated came out at a median of 0.5%. Dividing the raw counts cannot be misread.
    fips_col = index.get("FIPS")
    pop_col = index.get("2020 Population")
    adherents_col = index.get("Adherents")
    if fips_col is None or pop_col is None or adherents_col is None:
        workbook.close()
        raise ValueError(
            f"{SOURCE_ID}: '{SHEET}' is missing FIPS, population or adherents; "
            f"found {header[:8]}"
        )

    records: list[dict] = []
    skipped = 0
    implausible = 0
    for row in rows:
        raw = row[fips_col]
        population = row[pop_col]
        adherents = row[adherents_col]
        if (
            raw in (None, "")
            or not isinstance(population, (int, float))
            or not isinstance(adherents, (int, float))
            or population <= 0
        ):
            skipped += 1
            continue
        # The sheet ends with a "Totals" row, so a non-numeric FIPS is a footer, not an error.
        text = str(int(raw)) if isinstance(raw, (int, float)) else str(raw).strip()
        if not text.isdigit():
            skipped += 1
            continue
        geoid = norm_fips(text, 5)
        if not is_in_scope(geoid):
            continue
        share = adherents / population
        if share > MAX_PLAUSIBLE_SHARE:
            implausible += 1
            continue
        records.append({"geo_level": "county", "geo_id": geoid,
                        "indicator_id": "sens_religious_adherence", "value": share})
    workbook.close()

    return emit(records, source_file=Path(path).name, vintage=vintage), {
        "counties": len(records),
        "rows_skipped": skipped,
        "over_100pct_dropped": implausible,
    }
