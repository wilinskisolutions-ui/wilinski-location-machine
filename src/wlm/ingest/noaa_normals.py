"""NOAA 1991-2020 Climate Normals.

The case deliberately deferred from Phase 1, because climate is measured at **stations**
(points) and the universe is made of **counties** (areas). Every other source arrives
already keyed to a county.

Two things make it tractable:

1. NOAA publishes one bulk archive covering all ~15,600 stations, so this is a single
   download rather than thousands of requests.
2. Each county has a centroid on the universe table, so stations can be weighted by
   inverse distance to it.

**This is the annual/seasonal product, so the normals are seasonal, not monthly.** The
indicators are named for what the data is — winter and summer means, not January and July.
Humidity and sunshine are not in this product at all; they are recorded as a known gap
rather than approximated.
"""

from __future__ import annotations

import csv
import io
import tarfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl

from wlm.ingest.base import emit

SOURCE_ID = "noaa_normals"
VINTAGE = "1991-2020"

# NOAA column -> registered indicator id.
FIELD_MAP: dict[str, str] = {
    "DJF-TAVG-NORMAL": "climate_temp_winter_mean",
    "JJA-TAVG-NORMAL": "climate_temp_summer_mean",
    "DJF-TMIN-NORMAL": "climate_winter_low",
    "JJA-TMAX-NORMAL": "climate_summer_high",
    "ANN-PRCP-NORMAL": "climate_annual_precip",
    "ANN-SNOW-NORMAL": "climate_annual_snowfall",
    "ANN-HTDD-NORMAL": "climate_heating_degree_days",
    "ANN-CLDD-NORMAL": "climate_cooling_degree_days",
}

# Weighting parameters. A county's climate is taken from stations near its centroid:
# beyond MAX_DISTANCE_MI a station says little about it, and more than MAX_STATIONS adds
# noise rather than signal.
MAX_STATIONS = 5
MAX_DISTANCE_MI = 75.0
EARTH_RADIUS_MI = 3958.7613


@dataclass
class Station:
    station_id: str
    lat: float
    lon: float
    values: dict[str, float]


def _float(raw: str | None) -> float | None:
    if raw in (None, "", "None"):
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    # NOAA uses -9999 and friends for missing. Those are absent readings, not temperatures.
    return None if v <= -999 else v


def read_stations(archive: Path, fields: dict[str, str] | None = None) -> list[Station]:
    """Read every station record from the bulk normals tarball."""
    fields = fields or FIELD_MAP
    stations: list[Station] = []

    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not member.name.endswith(".csv"):
                continue
            handle = tar.extractfile(member)
            if handle is None:
                continue
            rows = list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8", errors="replace")))
            if not rows:
                continue
            row = rows[0]
            lat, lon = _float(row.get("LATITUDE")), _float(row.get("LONGITUDE"))
            if lat is None or lon is None:
                continue
            values = {
                indicator: value
                for column, indicator in fields.items()
                if (value := _float(row.get(column))) is not None
            }
            if values:
                stations.append(Station(row.get("STATION", member.name), lat, lon, values))
    return stations


def _haversine_miles(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    p1 = np.radians(lat)
    p2 = np.radians(lats)
    dp = p2 - p1
    dl = np.radians(lons - lon)
    a = np.sin(dp / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def to_counties(
    stations: list[Station],
    counties: pl.DataFrame,
    *,
    max_stations: int = MAX_STATIONS,
    max_distance_mi: float = MAX_DISTANCE_MI,
    centroids: dict[str, tuple[float, float]] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """Weight station readings onto county centroids by inverse distance.

    Each indicator is averaged over the nearest stations that actually report it, so a
    county is not left blank just because its closest station happens to lack snowfall.
    A county with no station within range is left missing rather than filled from far away
    (Principle 6).
    """
    lats = np.array([s.lat for s in stations])
    lons = np.array([s.lon for s in stations])

    indicators = sorted({k for s in stations for k in s.values})
    # value matrix: NaN where a station does not report that indicator
    matrix = np.full((len(stations), len(indicators)), np.nan)
    for i, s in enumerate(stations):
        for j, ind in enumerate(indicators):
            if ind in s.values:
                matrix[i, j] = s.values[ind]

    records: list[dict] = []
    stats = {"counties_matched": 0, "counties_no_station": 0}

    for row in counties.iter_rows(named=True):
        # Population-weighted centroid where available: climate should be measured where
        # people live, not at the county's geometric middle.
        override = (centroids or {}).get(row["geo_id"])
        lat, lon = override if override else (row.get("lat"), row.get("lon"))
        if lat is None or lon is None:
            stats["counties_no_station"] += 1
            continue

        distances = _haversine_miles(lat, lon, lats, lons)
        in_range = np.where(distances <= max_distance_mi)[0]
        if in_range.size == 0:
            stats["counties_no_station"] += 1
            continue

        matched_any = False
        for j, indicator in enumerate(indicators):
            candidates = in_range[~np.isnan(matrix[in_range, j])]
            if candidates.size == 0:
                continue
            nearest = candidates[np.argsort(distances[candidates])[:max_stations]]
            # +1 mile guards against a station sitting exactly on the centroid.
            weights = 1.0 / (distances[nearest] + 1.0)
            value = float(np.sum(matrix[nearest, j] * weights) / np.sum(weights))
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": row["geo_id"],
                    "indicator_id": indicator,
                    "value": value,
                }
            )
            matched_any = True

        stats["counties_matched"] += matched_any
        stats["counties_no_station"] += not matched_any

    return records, stats


def ingest(
    archive: Path,
    counties: pl.DataFrame,
    *,
    vintage: str = VINTAGE,
    centroids: dict[str, tuple[float, float]] | None = None,
) -> tuple[pl.DataFrame, dict]:
    stations = read_stations(Path(archive))
    records, stats = to_counties(stations, counties, centroids=centroids)
    stats["stations_read"] = len(stations)
    return emit(records, source_file=Path(archive).name, vintage=vintage), stats
