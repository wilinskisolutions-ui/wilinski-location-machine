"""District-level education from the Urban Institute Education Data API, mapped to counties.

**This is a substitute, and the difference is the whole point of the Phase 1 decision.**
`GOAL.md` chose Stanford's SEDA *learning growth* — how much students improve per year —
because district proficiency largely measures how wealthy the neighbours are. Scoring on
income-confounded measures would push the ranking toward expensive places while calling it
school quality, and would then collide with the cost domain.

SEDA's download links are JavaScript-gated and the household chose not to fetch it by hand,
so what follows is the best that is retrievable without a key:

  * `edu_graduation_rate`        EDFacts adjusted-cohort rate, cohort-weighted to county
  * `edu_student_teacher_ratio`  CCD enrollment over teacher FTE
  * `edu_spend_per_pupil`        CCD current elementary/secondary expenditure over enrollment
  * `edu_district_choice_count`  how many districts a county actually contains

Graduation and spending are more income-confounded than learning growth, less so than raw
proficiency. Every one carries `quality: substitute` in the registry with that reason, and
`output/coverage.md` repeats it, so nobody later reads these as the thing that was specified.

**Two caveats that are recorded rather than smoothed over.** EDFacts publishes graduation as
a *binned range* for small cohorts (`grad_rate_low` 60, `grad_rate_high` 69), so a midpoint
is an approximation and not a measurement. And people choose a **district**, not a county;
aggregating to county is a real loss of resolution, and a county with one excellent and one
failing district reads as mediocre.

**On sentinels.** This publisher marks withheld cells with small negatives — -1, -2, -3 —
exactly the trap CDC's -999 sprang. `ingest.base.emit` rejects those, but it only sees the
*county* value: a -3 inside a district would corrupt the weighted mean before emit ever
looked. So they are rejected here, at read time, and counted.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "urban_educationdata"
BASE = "https://educationdata.urban.org/api/v1/school-districts"

# Endpoint, the year pinned, and the file it lands in. Vintages differ per endpoint because
# finance and EDFacts lag the directory; each is recorded rather than averaged into one.
ENDPOINTS = {
    "directory": (f"{BASE}/ccd/directory/2021/", "ccd_directory_2021.json", "2021"),
    "finance": (f"{BASE}/ccd/finance/2019/", "ccd_finance_2019.json", "2019"),
    "grad": (f"{BASE}/edfacts/grad-rates/2019/", "edfacts_gradrates_2019.json", "2019"),
}

# EDFacts codes every demographic breakdown; 99 means "all students" on each axis. A row is
# the district total only when every axis is 99 — otherwise the same district appears once
# per subgroup and would be counted many times over.
ALL_STUDENTS = ("race", "disability", "econ_disadvantaged", "lep", "homeless", "foster_care")

# Grades in a K-12 run, used to turn a county's total enrollment into the size of cohort a
# complete return would cover. One year group is roughly a thirteenth of the whole.
GRADES_K12 = 13

# How much of that expected cohort must actually report before a county graduation rate
# describes the county rather than a corner of it.
#
# Pima County, Arizona is why this exists. Its rate came out at 34% for a county of 1.08
# million — computed from a single school of 68 pupils, because the other 82 districts,
# Tucson Unified among them, filed nothing. A number that looks like a county and describes
# 0.3% of it is worse than no number at all.
MIN_COHORT_COVERAGE = 0.5

# EDFacts protects small cohorts by publishing a *range* instead of a value. A narrow band
# ("60-69") still says something; "0-49" says almost nothing, and its midpoint is an
# arithmetic artifact rather than a measurement. Anything wider than this is dropped.
MAX_BIN_WIDTH = 20

# The staffing ratio needs the same representativeness test as graduation, for the same
# reason. Washoe County, Nevada filed no teacher count for its 66,524-pupil district, so the
# county ratio was being computed from Pyramid Lake High School's 126 pupils — a school
# standing in for a county of half a million.
MIN_STAFF_COVERAGE = 0.5


def fetch(url: str, *, timeout: int = 300) -> list[dict]:
    """Page through one endpoint. The API returns `next` until exhausted."""
    import urllib.request

    rows: list[dict] = []
    page = 0
    while url:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read())
        rows.extend(payload.get("results", []))
        url = payload.get("next")
        page += 1
        if page > 400:  # a paging bug should fail loudly, not spin
            raise RuntimeError(f"{SOURCE_ID}: runaway pagination after {page} pages")
    return rows


def save_raw(records: list[dict], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records))
    return path


def _positive(value) -> float | None:
    """A count, a rate and a dollar amount are all non-negative in reality.

    Anything below zero here is the publisher saying "withheld", so it becomes missing
    rather than a number (Principle 6).
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value) if value >= 0 else None


def ingest(folder: Path) -> tuple[pl.DataFrame, dict]:
    """Read the three files and aggregate districts to counties."""
    folder = Path(folder)
    directory = json.loads((folder / ENDPOINTS["directory"][1]).read_text())
    finance = json.loads((folder / ENDPOINTS["finance"][1]).read_text())
    grads = json.loads((folder / ENDPOINTS["grad"][1]).read_text())

    stats = {
        "sentinels_rejected": 0,
        "districts_without_county": 0,
        "grad_rates_dropped_unrepresentative": 0,
        "ratios_dropped_unrepresentative": 0,
        "grad_bins_too_wide": 0,
        "counties_without_a_district": 0,
    }

    # --- district -> county, plus enrollment and staffing ---
    county_of: dict[str, str] = {}
    rows: list[dict] = []
    for record in directory:
        leaid = str(record.get("leaid") or "").strip()
        raw_county = record.get("county_code")
        if not leaid or raw_county in (None, ""):
            stats["districts_without_county"] += 1
            continue
        county = norm_fips(str(raw_county), 5)
        if not is_in_scope(county):
            continue
        county_of[leaid] = county

        enrollment = _positive(record.get("enrollment"))
        teachers = _positive(record.get("teachers_total_fte"))
        rows.append(
            {
                "county": county,
                "enrollment": enrollment,
                # Enrollment counted only where the same district also reported staff.
                # Summing all enrollment against only the reported teachers put Washoe
                # County, Nevada at 3,520 pupils per teacher: its 66,524-pupil district
                # filed no staff count, so the whole county rode on one 19-teacher school.
                "paired_enrollment": enrollment if (teachers and enrollment) else None,
                "teachers": teachers if (teachers and enrollment) else None,
                "operating": 1 if (enrollment or 0) > 0 else 0,
            }
        )

    districts = pl.DataFrame(rows) if rows else pl.DataFrame()
    if districts.is_empty():
        return emit([], source_file="urban_educationdata", vintage="2019-2021"), stats

    by_county = districts.group_by("county").agg(
        pl.col("enrollment").sum().alias("enrollment"),
        pl.col("paired_enrollment").sum().alias("paired_enrollment"),
        pl.col("teachers").sum().alias("teachers"),
        pl.col("operating").sum().alias("districts"),
    )
    enrollment_of = dict(zip(by_county["county"], by_county["enrollment"]))

    # --- spending, joined on leaid ---
    spend_rows = []
    for record in finance:
        leaid = str(record.get("leaid") or "").strip()
        county = county_of.get(leaid)
        if county is None:
            continue
        spend = _positive(record.get("exp_current_elsec_total"))
        pupils = _positive(record.get("enrollment_fall_responsible"))
        if record.get("exp_current_elsec_total") is not None and spend is None:
            stats["sentinels_rejected"] += 1
        if spend is None or not pupils:
            continue
        spend_rows.append({"county": county, "spend": spend, "pupils": pupils})

    # --- graduation, all-students rows only, cohort-weighted ---
    grad_rows = []
    for record in grads:
        if not all(record.get(axis) == 99 for axis in ALL_STUDENTS):
            continue
        leaid = str(record.get("leaid") or "").strip()
        county = county_of.get(leaid)
        if county is None:
            continue
        rate = _positive(record.get("grad_rate_midpt"))
        cohort = _positive(record.get("cohort_num"))
        if record.get("grad_rate_midpt") is not None and rate is None:
            stats["sentinels_rejected"] += 1
        if rate is None or not cohort:
            continue
        low, high = record.get("grad_rate_low"), record.get("grad_rate_high")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            if high - low > MAX_BIN_WIDTH:
                stats["grad_bins_too_wide"] += 1
                continue
        # Published 0-100; the registry declares this indicator a share.
        grad_rows.append({"county": county, "rate": rate / 100.0, "cohort": cohort})

    records: list[dict] = []

    def add(county: str, indicator: str, value: float | None) -> None:
        if value is not None:
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": county,
                    "indicator_id": indicator,
                    "value": value,
                }
            )

    for row in by_county.iter_rows(named=True):
        enrolled = row["enrollment"] or 0
        covered = row["paired_enrollment"] or 0
        if row["teachers"] and covered and (
            not enrolled or covered >= MIN_STAFF_COVERAGE * enrolled
        ):
            add(row["county"], "edu_student_teacher_ratio", covered / row["teachers"])
        elif row["teachers"] and covered:
            stats["ratios_dropped_unrepresentative"] += 1
        # Zero districts is not a county with no schools — it is a county whose schools are
        # coded elsewhere. Virginia does this throughout: James City County's pupils belong
        # to a Williamsburg-James City division filed under the city. Reporting 0 on a
        # higher-is-better indicator would rank it last for a filing convention.
        if row["districts"] > 0:
            add(row["county"], "edu_district_choice_count", float(row["districts"]))
        else:
            stats["counties_without_a_district"] += 1

    if spend_rows:
        spend = (
            pl.DataFrame(spend_rows)
            .group_by("county")
            .agg(pl.col("spend").sum(), pl.col("pupils").sum())
        )
        for row in spend.iter_rows(named=True):
            if row["pupils"]:
                add(row["county"], "edu_spend_per_pupil", row["spend"] / row["pupils"])

    if grad_rows:
        grad = (
            pl.DataFrame(grad_rows)
            .group_by("county")
            .agg(
                # Cohort-weighted: a 40-pupil district must not outvote a 4,000-pupil one.
                ((pl.col("rate") * pl.col("cohort")).sum() / pl.col("cohort").sum()).alias("rate"),
                pl.col("cohort").sum().alias("cohort"),
            )
        )
        for row in grad.iter_rows(named=True):
            enrolled = enrollment_of.get(row["county"]) or 0
            expected = enrolled / GRADES_K12
            if expected and row["cohort"] < MIN_COHORT_COVERAGE * expected:
                stats["grad_rates_dropped_unrepresentative"] += 1
                continue
            add(row["county"], "edu_graduation_rate", row["rate"])

    stats["counties"] = len({r["geo_id"] for r in records})
    stats["districts_mapped"] = len(county_of)
    return emit(records, source_file="urban_educationdata", vintage="2019-2021"), stats
