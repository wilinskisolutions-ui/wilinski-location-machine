"""Build the fixed candidate universe.

Every US county and every place above the population floor, in the 50 states and DC,
enumerated from Census geography **before any preference is known** (GOAL.md Principle 1).
Nothing enters because it came up in conversation; nothing is dropped for seeming unlikely.

Output: `data/processed/universe.parquet`, plus `place_county_weights.parquet` for the
places that straddle county lines.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from wlm.geo import (
    MIN_PLACE_POPULATION,
    PlaceCountyCrosswalk,
    STATE_FIPS,
    classify_place,
    is_in_scope,
    norm_fips,
)
from wlm.paths import PROCESSED

UNIVERSE_COLUMNS = [
    "geo_level", "geo_id", "name", "state_usps", "state_fips",
    "county_geoid", "population", "land_sqmi", "lat", "lon", "place_class",
]


@dataclass
class BuildReport:
    """The numbers that show the universe is what it claims to be.

    Printed on every build. A silent universe build is an unverifiable one — these counts
    are how a reviewer confirms nothing was quietly dropped.
    """

    counties: int = 0
    places_total: int = 0
    places_kept: int = 0
    places_below_floor: int = 0
    places_no_population: int = 0
    places_unmatched_county: int = 0
    places_multi_county: int = 0
    incorporated: int = 0
    cdp: int = 0
    out_of_scope: int = 0
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"counties                {self.counties:>7,}",
            f"places examined         {self.places_total:>7,}",
            f"  kept (>= {MIN_PLACE_POPULATION:,})      {self.places_kept:>7,}",
            f"    incorporated        {self.incorporated:>7,}",
            f"    census designated   {self.cdp:>7,}",
            f"  below floor           {self.places_below_floor:>7,}",
            f"  no population figure  {self.places_no_population:>7,}",
            f"  spanning >1 county    {self.places_multi_county:>7,}",
            f"  no county match       {self.places_unmatched_county:>7,}",
            f"out-of-scope rows       {self.out_of_scope:>7,}  (territories)",
            f"UNIVERSE TOTAL          {self.counties + self.places_kept:>7,}",
        ]
        if self.warnings:
            lines.append("")
            lines += [f"  warning: {w}" for w in self.warnings]
        return "\n".join(lines)


# ------------------------------------------------------------------------------- readers


def read_gazetteer(path: Path) -> list[dict[str, str]]:
    """Read a Census Gazetteer file.

    Gazetteer files are tab-delimited and pad both headers and values with whitespace, so
    everything is stripped on the way in.
    """
    text = path.read_text(encoding="utf-8-sig")
    rows: list[dict[str, str]] = []
    for rec in csv.DictReader(text.splitlines(), delimiter="\t"):
        rows.append({(k or "").strip().upper(): (v or "").strip() for k, v in rec.items()})
    return rows


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


# -------------------------------------------------------------------------------- builds


def build_counties(rows: list[dict[str, str]], population: dict[str, int], report: BuildReport) -> pl.DataFrame:
    out = []
    for r in rows:
        geoid = norm_fips(r["GEOID"], 5)
        if not is_in_scope(geoid):
            report.out_of_scope += 1
            continue
        out.append(
            {
                "geo_level": "county",
                "geo_id": geoid,
                "name": r.get("NAME", ""),
                "state_usps": r.get("USPS") or STATE_FIPS[geoid[:2]],
                "state_fips": geoid[:2],
                "county_geoid": geoid,
                "population": population.get(geoid),
                "land_sqmi": _float(r.get("ALAND_SQMI")),
                "lat": _float(r.get("INTPTLAT")),
                "lon": _float(r.get("INTPTLONG")),
                "place_class": None,
            }
        )
    report.counties = len(out)
    return pl.DataFrame(out, schema_overrides={"population": pl.Int64, "place_class": pl.Utf8})


def build_places(
    rows: list[dict[str, str]],
    population: dict[str, int],
    crosswalk: PlaceCountyCrosswalk,
    report: BuildReport,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    out: list[dict] = []
    weights: list[dict] = []

    for r in rows:
        report.places_total += 1
        geoid = norm_fips(r["GEOID"], 7)

        if not is_in_scope(geoid):
            report.out_of_scope += 1
            continue

        pop = population.get(geoid)
        if pop is None:
            # Absence is recorded, never treated as zero (Principle 6). A place with no
            # population figure cannot be filtered on, so it is excluded and counted.
            report.places_no_population += 1
            continue
        if pop < MIN_PLACE_POPULATION:
            report.places_below_floor += 1
            continue

        links = crosswalk.counties_for(geoid)
        if not links:
            report.places_unmatched_county += 1
            continue
        if len(links) > 1:
            report.places_multi_county += 1

        klass = classify_place(r.get("LSAD"))
        report.incorporated += klass == "incorporated"
        report.cdp += klass == "cdp"

        out.append(
            {
                "geo_level": "place",
                "geo_id": geoid,
                "name": r.get("NAME", ""),
                "state_usps": r.get("USPS") or STATE_FIPS[geoid[:2]],
                "state_fips": geoid[:2],
                "county_geoid": crosswalk.primary_county(geoid),
                "population": pop,
                "land_sqmi": _float(r.get("ALAND_SQMI")),
                "lat": _float(r.get("INTPTLAT")),
                "lon": _float(r.get("INTPTLONG")),
                "place_class": klass,
            }
        )
        weights.extend(
            {"place_geoid": geoid, "county_geoid": ln.county_geoid, "weight": ln.weight}
            for ln in links
        )

    report.places_kept = len(out)
    places = pl.DataFrame(out, schema_overrides={"population": pl.Int64})
    wdf = pl.DataFrame(weights, schema={"place_geoid": pl.Utf8, "county_geoid": pl.Utf8, "weight": pl.Float64})
    return places, wdf


def build(
    *,
    counties_file: Path,
    places_file: Path,
    population: dict[str, int],
    crosswalk: PlaceCountyCrosswalk,
    out_dir: Path = PROCESSED,
    write: bool = True,
) -> tuple[pl.DataFrame, pl.DataFrame, BuildReport]:
    report = BuildReport()

    counties = build_counties(read_gazetteer(counties_file), population, report)
    places, weights = build_places(read_gazetteer(places_file), population, crosswalk, report)

    universe = pl.concat([counties, places], how="vertical").select(UNIVERSE_COLUMNS)

    dupes = universe.filter(pl.col("geo_id").is_duplicated())
    if dupes.height:
        report.warnings.append(f"{dupes.height} duplicate geo_id rows — investigate before scoring")
    if report.places_unmatched_county:
        report.warnings.append(
            f"{report.places_unmatched_county} place(s) had no county match and were excluded; "
            "a systematic gap here would bias the universe"
        )

    if write:
        out_dir.mkdir(parents=True, exist_ok=True)
        universe.write_parquet(out_dir / "universe.parquet")
        weights.write_parquet(out_dir / "place_county_weights.parquet")

    return universe, weights, report
