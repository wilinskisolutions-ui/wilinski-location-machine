"""Shared contract for every ingest module.

All sources, however different their raw formats, emit one shape:

    geo_level | geo_id | indicator_id | value | vintage | source_file

`emit` refuses any `indicator_id` not in `config/indicators.yaml`. That is Principle 2 made
mechanical: an ingest module cannot invent a column, so it cannot give one place a dimension
another place does not have.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import yaml

from wlm.paths import CONFIG

LONG_COLUMNS = ["geo_level", "geo_id", "indicator_id", "value", "vintage", "source_file"]

LONG_SCHEMA = {
    "geo_level": pl.Utf8,
    "geo_id": pl.Utf8,
    "indicator_id": pl.Utf8,
    "value": pl.Float64,
    "vintage": pl.Utf8,
    "source_file": pl.Utf8,
}

# Expected GEOID widths. A wrong-width id silently fails to join, producing a place that
# looks like it has missing data when it actually has a typo.
GEOID_WIDTH = {"state": 2, "county": 5, "place": 7, "metro": 5, "district": 7}


class IngestError(ValueError):
    """An ingest module emitted something the registry does not allow."""


_registry_cache: dict[str, dict] | None = None


def registry(path: Path = CONFIG / "indicators.yaml", *, reload: bool = False) -> dict[str, dict]:
    """Registered indicators, keyed by id."""
    global _registry_cache
    if _registry_cache is None or reload:
        data = yaml.safe_load(path.read_text()) or {}
        _registry_cache = {i["id"]: i for i in data.get("indicators", [])}
    return _registry_cache


def emit(
    records: list[dict],
    *,
    source_file: str,
    vintage: str,
    reg: dict[str, dict] | None = None,
    strict_width: bool = True,
) -> pl.DataFrame:
    """Validate records and return them in the common long form.

    Each record needs `geo_level`, `geo_id`, `indicator_id`, `value`. A `value` of None is
    allowed and preserved — missing is a real state, not a zero (Principle 6).
    """
    reg = reg if reg is not None else registry()

    unknown: set[str] = set()
    mismatched: list[str] = []
    bad_width: list[str] = []
    rows: list[dict] = []

    for rec in records:
        iid = rec.get("indicator_id")
        entry = reg.get(iid)
        if entry is None:
            unknown.add(str(iid))
            continue

        level = rec.get("geo_level")
        expected_level = entry.get("geo_level")
        if level != expected_level:
            mismatched.append(f"{iid}: emitted '{level}', registry says '{expected_level}'")
            continue

        geo_id = str(rec.get("geo_id", ""))
        want = GEOID_WIDTH.get(level)
        if strict_width and want and len(geo_id) != want:
            bad_width.append(f"{iid}: geo_id '{geo_id}' is {len(geo_id)} chars, expected {want}")
            continue

        value = rec.get("value")
        if value is not None:
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = None  # unparseable is missing, not zero

        rows.append(
            {
                "geo_level": level,
                "geo_id": geo_id,
                "indicator_id": iid,
                "value": value,
                "vintage": vintage,
                "source_file": source_file,
            }
        )

    problems = []
    if unknown:
        problems.append(
            f"{len(unknown)} unregistered indicator_id(s): {', '.join(sorted(unknown))}\n"
            "  Register them in config/indicators.yaml first — nothing is scored that is "
            "not registered."
        )
    if mismatched:
        problems.append("geo_level disagrees with the registry:\n  " + "\n  ".join(mismatched))
    if bad_width:
        problems.append("malformed GEOIDs:\n  " + "\n  ".join(bad_width[:10]))
    if problems:
        raise IngestError("\n\n".join(problems))

    return pl.DataFrame(rows, schema=LONG_SCHEMA)


def write_interim(df: pl.DataFrame, source_id: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{source_id}.parquet"
    df.write_parquet(path)
    return path
