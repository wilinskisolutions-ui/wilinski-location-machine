"""Fetch the four sources that arrive through an API rather than as a file.

`make data` used to download only the static files in `cli.DOWNLOADS`. The API sources —
BTS air segments, FEMA NRI, CDC injury mortality and the Urban Institute school data —
were fetched by hand in an earlier session and never manifested, so a fresh clone could not
rebuild the feature table at all: `make features` died on the first missing JSON. Each is
fetched here through its module's own reader, saved where `stage_features` expects it, and
recorded in the manifest with a checksum like every other file (Principle 3).
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from wlm.manifest import Manifest
from wlm.paths import RAW

BTS_ENDPOINT = "https://data.transportation.gov/resource/xgub-n9bw.json"
BTS_YEAR = "2024"


def fetch_bts(year: str = BTS_YEAR, *, endpoint: str = BTS_ENDPOINT) -> list[dict]:
    """Every 2024 segment to a European airport (world area codes 400-499).

    `fg_wac` is a text column, so the server-side range is lexicographic and lets a few
    two-digit codes through; `bts_intl.summarize_hubs` re-checks it as an integer.
    """
    import requests

    where = f"year={year} AND fg_wac between '400' and '499'"
    rows: list[dict] = []
    offset, page = 0, 50_000
    while True:
        params = {"$where": where, "$limit": page, "$offset": offset, "$order": ":id"}
        resp = requests.get(f"{endpoint}?{urllib.parse.urlencode(params)}", timeout=180)
        resp.raise_for_status()
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < page:
            return rows
        offset += page


def _save(records: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(records))
    tmp.replace(path)
    return path


def _jobs() -> list[tuple[str, str, Path, str, Callable[[], list[dict]]]]:
    from wlm.ingest import cdc_mortality, fema_nri, urban_education

    jobs = [
        ("bts_intl", BTS_ENDPOINT, RAW / "bts_intl" / "intl_segments_2024_europe.json",
         BTS_YEAR, fetch_bts),
        ("fema_nri", fema_nri.SERVICE, RAW / "fema_nri" / "nri_counties.json",
         fema_nri.VINTAGE, fema_nri.fetch_features),
        ("cdc_wonder", cdc_mortality.ENDPOINT, RAW / "cdc_wonder" / "county_injury_2023.json",
         cdc_mortality.VINTAGE, cdc_mortality.fetch),
    ]
    for url, filename, vintage in urban_education.ENDPOINTS.values():
        jobs.append(
            ("urban_educationdata", url, RAW / "urban_educationdata" / filename, vintage,
             lambda u=url: urban_education.fetch(u))
        )
    return jobs


def fetch_all(manifest: Manifest, *, offline: bool = False) -> list[str]:
    """Fetch whatever is missing. Returns the failures, named, rather than skipping them."""
    failures: list[str] = []
    for source_id, url, path, vintage, fetcher in _jobs():
        rel = path.relative_to(RAW).as_posix()
        if manifest.verify(rel, RAW):
            print(f"  ok    {source_id:<18} {path.name}")
            continue
        if offline:
            failures.append(f"{source_id}: offline and {path.name} is absent")
            continue
        try:
            records = fetcher()
        except Exception as exc:  # every failure is reported, never absorbed
            failures.append(f"{source_id}: {type(exc).__name__}: {exc}")
            print(f"  FAIL  {source_id:<18} {exc}")
            continue
        if not records:
            failures.append(f"{source_id}: the API returned no rows")
            continue
        _save(records, path)
        manifest.record(source_id=source_id, url=url, file=path, vintage=vintage,
                        note=f"API pull, {len(records):,} records")
        print(f"  ok    {source_id:<18} {path.name}  ({len(records):,} records)")
    return failures
