"""Transatlantic air access, from BTS international segments.

The household has family in Europe and reads "cheap access to Europe" as implying the east
coast. This module exists to **test** that rather than encode it: it measures nonstop
European destinations from the nearest transatlantic airport and the distance to reach it,
so the ranking can show whether the east coast is a real constraint.

Europe is world area codes 400-499 in the BTS scheme — verified against Copenhagen (419),
Paris (427), Frankfurt (429), Dublin (441), Amsterdam (461), Madrid (482) and London (493).
Istanbul is 679 and correctly falls outside.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import polars as pl

from wlm.ingest.base import emit

SOURCE_ID = "bts_intl"
VINTAGE = "2024"

EUROPE_WAC_MIN, EUROPE_WAC_MAX = 400, 499
EARTH_RADIUS_MI = 3958.7613

# Airports with only token service are noise; a couple of charter flights a year is not
# "access to Europe".
MIN_ANNUAL_PASSENGERS = 10_000

# People drive past a small airport to reach a better one. Within this radius the hub with
# the most European destinations wins, not merely the closest: from Harrisburg, Dulles is
# 22 miles further than Baltimore and offers 66 European destinations against 18. Choosing
# "nearest" would have understated every place that sits between two hubs.
HUB_SEARCH_RADIUS_MI = 200.0


def read_airports(path: Path) -> dict[str, tuple[float, float]]:
    """IATA code -> (lat, lon), from the OpenFlights table."""
    out: dict[str, tuple[float, float]] = {}
    with Path(path).open(encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh):
            if len(row) < 8:
                continue
            iata = row[4].strip().strip('"')
            if not iata or iata == "\\N" or len(iata) != 3:
                continue
            try:
                out[iata] = (float(row[6]), float(row[7]))
            except ValueError:
                continue
    return out


def summarize_hubs(records: list[dict]) -> dict[str, dict]:
    """US airport -> {destinations, passengers} for European service."""
    dests: dict[str, set[str]] = defaultdict(set)
    pax: dict[str, float] = defaultdict(float)

    for row in records:
        try:
            wac = int(row.get("fg_wac", -1))
        except (TypeError, ValueError):
            continue
        if not (EUROPE_WAC_MIN <= wac <= EUROPE_WAC_MAX):
            continue
        if (row.get("type") or "").lower() != "passengers":
            continue
        try:
            total = float(row.get("total") or 0)
        except ValueError:
            continue
        usg, fg = row.get("usg_apt"), row.get("fg_apt")
        if not usg or not fg:
            continue
        dests[usg].add(fg)
        pax[usg] += total

    return {
        apt: {"destinations": len(dests[apt]), "passengers": pax[apt]}
        for apt in dests
        if pax[apt] >= MIN_ANNUAL_PASSENGERS
    }


def load_records(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text())


def to_counties(
    hubs: dict[str, dict],
    airports: dict[str, tuple[float, float]],
    counties: pl.DataFrame,
    centroids: dict[str, tuple[float, float]] | None = None,
) -> tuple[list[dict], dict]:
    """For each county, find the nearest European-serving airport and describe it."""
    coded = [(a, *airports[a]) for a in hubs if a in airports]
    missing = sorted(set(hubs) - set(airports))
    if not coded:
        return [], {"hubs": 0, "hubs_without_coordinates": len(missing)}

    lats = np.array([c[1] for c in coded])
    lons = np.array([c[2] for c in coded])
    names = [c[0] for c in coded]

    records: list[dict] = []
    counters: dict[str, int] = {}
    for row in counties.iter_rows(named=True):
        override = (centroids or {}).get(row["geo_id"])
        lat, lon = override if override else (row.get("lat"), row.get("lon"))
        if lat is None or lon is None:
            continue

        p1, p2 = np.radians(lat), np.radians(lats)
        a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(
            np.radians(lons - lon) / 2
        ) ** 2
        d = 2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

        in_range = np.where(d <= HUB_SEARCH_RADIUS_MI)[0]
        if in_range.size:
            # Best reachable hub: most destinations, nearest as the tie-break.
            i = int(min(in_range, key=lambda k: (-hubs[names[k]]["destinations"], d[k])))
            stats_key = "counties_with_hub_in_range"
        else:
            i = int(np.argmin(d))
            stats_key = "counties_nearest_only"
        counters[stats_key] = counters.get(stats_key, 0) + 1
        hub = hubs[names[i]]

        records.append({"geo_level": "county", "geo_id": row["geo_id"],
                        "indicator_id": "air_europe_hub_distance", "value": float(d[i])})
        records.append({"geo_level": "county", "geo_id": row["geo_id"],
                        "indicator_id": "air_europe_destinations", "value": hub["destinations"]})
        records.append({"geo_level": "county", "geo_id": row["geo_id"],
                        "indicator_id": "air_europe_passengers", "value": hub["passengers"]})

    return records, {
        "hubs": len(coded),
        "hubs_without_coordinates": len(missing),
        "missing_examples": missing[:5],
        **counters,
    }


def ingest(
    segments: Path,
    airports_file: Path,
    counties: pl.DataFrame,
    *,
    vintage: str = VINTAGE,
    centroids: dict[str, tuple[float, float]] | None = None,
) -> tuple[pl.DataFrame, dict]:
    hubs = summarize_hubs(load_records(segments))
    airports = read_airports(airports_file)
    records, stats = to_counties(hubs, airports, counties, centroids)
    stats["hubs_found"] = len(hubs)
    return emit(records, source_file=Path(segments).name, vintage=vintage), stats, hubs
