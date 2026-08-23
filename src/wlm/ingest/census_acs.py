"""Census ACS 5-year ingest.

The ACS API returns a matrix: first row is the header, the rest are values. Geography
arrives as separate components (`state` + `place`, or `state` + `county`) which must be
concatenated and zero-padded into a GEOID — the padding is the part that silently breaks
joins if skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from wlm.geo import county_geoid, is_in_scope, place_geoid
from wlm.ingest.base import emit

SOURCE_ID = "census_acs5"

# ACS variable -> registered indicator id. Extend as Phase 2 adds indicators.
VARIABLE_MAP: dict[str, str] = {
    "B01003_001E": "form_population",
}

POPULATION_VARIABLE = "B01003_001E"


class ACSError(ValueError):
    """Malformed ACS response."""


def parse_acs(path: Path) -> list[dict[str, str]]:
    """Turn an ACS matrix response into dict rows keyed by column name."""
    payload = json.loads(Path(path).read_text())
    if not payload or not isinstance(payload, list):
        raise ACSError(f"{path}: empty or non-list ACS payload")
    header, *rows = payload
    return [dict(zip(header, row)) for row in rows]


def row_geoid(row: dict[str, str]) -> tuple[str, str] | None:
    """Return (geo_level, geoid) for an ACS row, or None if geography is absent."""
    state = row.get("state")
    if not state:
        return None
    if (place := row.get("place")) is not None:
        return "place", place_geoid(state, place)
    if (county := row.get("county")) is not None:
        return "county", county_geoid(state, county)
    return None


def population_map(*paths: Path) -> dict[str, int]:
    """GEOID -> total population, across any mix of place and county ACS responses.

    Out-of-scope geographies (territories) are dropped here so the universe builder never
    sees them. Unparseable counts are omitted rather than zeroed — a place with no
    population figure must be reported as such, not treated as empty.
    """
    out: dict[str, int] = {}
    for path in paths:
        for row in parse_acs(Path(path)):
            geo = row_geoid(row)
            if geo is None:
                continue
            _, geoid = geo
            if not is_in_scope(geoid):
                continue
            raw = row.get(POPULATION_VARIABLE)
            try:
                value = int(float(raw))
            except (TypeError, ValueError):
                continue
            if value >= 0:
                out[geoid] = value
    return out


def ingest(paths: list[Path], *, vintage: str, variable_map: dict[str, str] | None = None) -> pl.DataFrame:
    """Emit long-form records for every mapped ACS variable."""
    variable_map = variable_map or VARIABLE_MAP
    records: list[dict] = []

    for path in paths:
        path = Path(path)
        for row in parse_acs(path):
            geo = row_geoid(row)
            if geo is None:
                continue
            level, geoid = geo
            if not is_in_scope(geoid):
                continue
            for variable, indicator_id in variable_map.items():
                if variable not in row:
                    continue
                records.append(
                    {
                        "geo_level": level,
                        "geo_id": geoid,
                        "indicator_id": indicator_id,
                        "value": row[variable],
                    }
                )

    return emit(records, source_file=",".join(Path(p).name for p in paths), vintage=vintage)


# --------------------------------------------------------------------- bulk summary file

BULK_GEO_PREFIX = {"1600000US": "place", "0500000US": "county"}


def parse_acs_bulk(path: Path, variable: str = "B01003_E001") -> dict[str, int]:
    """Read a pipe-delimited ACS table-based summary file.

    Used instead of the API, which now requires a registered key. GEO_IDs are
    self-describing (`1600000US4232800` is a place), so the 92MB geography lookup file is
    unnecessary.

    This is the only source covering **census designated places** — PEP omits them — so it
    is what keeps unincorporated communities in the universe.
    """
    out: dict[str, int] = {}
    with Path(path).open(encoding="utf-8-sig", errors="replace") as fh:
        header = fh.readline().rstrip("\n").split("|")
        try:
            col = header.index(variable)
        except ValueError as exc:
            raise ACSError(f"{path}: no column {variable!r} in {header}") from exc

        for line in fh:
            parts = line.rstrip("\n").split("|")
            if len(parts) <= col:
                continue
            geo = parts[0]
            for prefix in BULK_GEO_PREFIX:
                if geo.startswith(prefix):
                    geoid = geo[len(prefix):]
                    break
            else:
                continue
            if not is_in_scope(geoid):
                continue
            try:
                value = int(float(parts[col]))
            except ValueError:
                continue
            # ACS uses large negative sentinels (-555555555 and friends) for suppressed
            # or not-applicable cells. Those are missing, not populations.
            if value >= 0:
                out[geoid] = value
    return out


def population_from_bulk(path: Path) -> dict[str, int]:
    return parse_acs_bulk(path, "B01003_E001")


# ----------------------------------------------------------------- derived indicators

# indicator -> (numerator table/variable, denominator or None, geo level)
#
# Several of these are ratios across two ACS tables. Expressing them here rather than in the
# feature stage keeps the derivation next to its source, and means the registry's `unit`
# ("ratio", "share") is what actually gets emitted.
DERIVED: dict[str, tuple[str, str | None, str]] = {
    # Tax as a share of home value, not dollars: a high-tax cheap house and a low-tax
    # expensive one are not comparable in dollars.
    "cost_property_tax_rate": ("b25103:B25103_E001", "b25077:B25077_E001", "county"),
    # Affordability relative to local wages, which is the number that decides whether a
    # place is livable on its own salaries.
    "cost_income_to_home_ratio": ("b25077:B25077_E001", "b19013:B19013_E001", "place"),
    "form_mean_commute": ("b08013:B08013_E001", "b08303:B08303_E001", "place"),
    "sens_foreign_born_share": ("b05002:B05002_E013", "b05002:B05002_E001", "place"),
    "comm_same_house_1yr": ("b07003:B07003_E004", "b07003:B07003_E001", "place"),
    "comm_median_age": ("b01002:B01002_E001", None, "place"),
    "form_population": ("b01003:B01003_E001", None, "place"),
}

GEO_WIDTH = {"county": 5, "place": 7}


def _table_values(raw_dir: Path, spec: str) -> dict[str, float]:
    table, variable = spec.split(":")
    path = Path(raw_dir) / f"acsdt5y2023-{table}.dat"
    return {k: float(v) for k, v in parse_acs_bulk(path, variable).items()}


def build_indicators(
    raw_dir: Path,
    universe: "pl.DataFrame | None" = None,
    *,
    vintage: str = "2019-2023",
    derived: dict | None = None,
) -> "pl.DataFrame":
    """Emit every ACS-derived indicator, including cross-table ratios."""
    import polars as pl  # local import keeps the module importable without polars

    derived = derived or DERIVED
    cache: dict[str, dict[str, float]] = {}
    records: list[dict] = []

    for indicator, (num_spec, den_spec, level) in derived.items():
        for spec in (num_spec, den_spec):
            if spec and spec not in cache:
                cache[spec] = _table_values(raw_dir, spec)

        numerator = cache[num_spec]
        denominator = cache[den_spec] if den_spec else None
        width = GEO_WIDTH[level]

        for geoid, value in numerator.items():
            if len(geoid) != width:
                continue
            if denominator is not None:
                base = denominator.get(geoid)
                # A zero or absent denominator makes the ratio undefined, not zero.
                value = (value / base) if (base and base > 0) else None
            records.append(
                {"geo_level": level, "geo_id": geoid, "indicator_id": indicator, "value": value}
            )

    # Density needs land area, which lives on the universe rather than in ACS.
    if universe is not None:
        population = cache.get("b01003:B01003_E001") or _table_values(
            raw_dir, "b01003:B01003_E001"
        )
        places = universe.filter(pl.col("geo_level") == "place")
        for geo_id, land in zip(places["geo_id"], places["land_sqmi"]):
            pop = population.get(geo_id)
            records.append(
                {
                    "geo_level": "place",
                    "geo_id": geo_id,
                    "indicator_id": "form_population_density",
                    "value": (pop / land) if (pop is not None and land and land > 0) else None,
                }
            )

    return emit(records, source_file="acsdt5y2023-*.dat", vintage=vintage)
