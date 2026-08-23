"""CDC county-level injury mortality — firearm and drug overdose death rates.

Sourced from `data.cdc.gov` rather than WONDER itself, which is form-gated and cannot be
queried programmatically. Same underlying vital-statistics data.

These belong in safety because they are built from death certificates, so coverage is close
to complete where FBI crime reporting — which is voluntary — has holes.

**How suppression actually works in this dataset**, having checked rather than assumed:
counts are *binned* for privacy (`1-9`, `10-50`) but the rate is published anyway, and
every zero-rate row carries a genuine count of 0. So rates are usable throughout.

The residual caution is statistical, not one of missingness: a rate derived from a binned
count of 1-9 in a small county is volatile, and a run of quiet years there will read as
safety. Phase 4 weight-sensitivity is where that shows up.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "cdc_wonder"
VINTAGE = "2023"
ENDPOINT = "https://data.cdc.gov/resource/psx4-wq38.json"

# CDC `intent` value -> registered indicator id.
INTENT_MAP: dict[str, str] = {
    "FA_Deaths": "safety_firearm_death_rate",
    "Drug_OD": "safety_overdose_death_rate",
}

# Markers CDC uses where a cell is withheld or unstable.
SUPPRESSED = {"", "*", "suppressed", "unreliable", "na", "n/a", None}


def fetch(period: str = "2023", *, endpoint: str = ENDPOINT, limit: int = 50_000) -> list[dict]:
    import requests

    intents = "','".join(INTENT_MAP)
    params = {
        "$limit": limit,
        "$where": f"period='{period}' AND intent in('{intents}')",
    }
    resp = requests.get(endpoint, params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


def save_raw(records: list[dict], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records))
    return path


def ingest(path: Path, *, vintage: str = VINTAGE) -> tuple[pl.DataFrame, dict]:
    rows = json.loads(Path(path).read_text())
    records: list[dict] = []
    suppressed = 0

    for row in rows:
        indicator = INTENT_MAP.get((row.get("intent") or "").strip())
        raw_geoid = (row.get("geoid") or "").strip()
        if indicator is None or not raw_geoid.isdigit():
            continue
        geoid = norm_fips(raw_geoid, 5)
        if not is_in_scope(geoid):
            continue

        rate = row.get("rate")
        count = str(row.get("count_sup", "")).strip().lower()
        if count in SUPPRESSED or rate in SUPPRESSED:
            suppressed += 1
            value = None
        else:
            try:
                value = float(rate)
            except (TypeError, ValueError):
                suppressed += 1
                value = None

        records.append(
            {"geo_level": "county", "geo_id": geoid, "indicator_id": indicator, "value": value}
        )

    return emit(records, source_file=Path(path).name, vintage=vintage), {
        "rows": len(records),
        "suppressed_or_unstable": suppressed,
    }
