"""Census geography: FIPS codes, GEOIDs, and the place-to-county crosswalk.

The universe is defined from these codes and nothing else, which is what makes Principle 1
("the universe is fixed before preferences are known") true in practice rather than by
intention.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 50 states + DC. Territories are deliberately absent: Puerto Rico's 78 municipios and the
# island areas are a separate scoping decision, logged as an open question rather than
# quietly included or quietly dropped.
STATE_FIPS: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}
USPS_TO_FIPS: dict[str, str] = {v: k for k, v in STATE_FIPS.items()}

TERRITORY_FIPS = frozenset({"60", "66", "69", "72", "78"})

# LSAD 57 is "census designated place" — an unincorporated community. Everything else in
# the places file is an incorporated municipality (city, town, village, borough).
CDP_LSAD = "57"

MIN_PLACE_POPULATION = 5_000


class GeoError(ValueError):
    """A malformed or out-of-scope geographic identifier."""


# --------------------------------------------------------------------------- identifiers


def norm_fips(value: str | int, width: int) -> str:
    """Zero-pad a FIPS component. Census files lose leading zeros through spreadsheets."""
    s = str(value).strip()
    if not s.isdigit():
        raise GeoError(f"FIPS component is not numeric: {value!r}")
    if len(s) > width:
        raise GeoError(f"FIPS component {s!r} is longer than {width} digits")
    return s.zfill(width)


def county_geoid(state: str | int, county: str | int) -> str:
    """5-digit county GEOID: 2-digit state + 3-digit county."""
    return norm_fips(state, 2) + norm_fips(county, 3)


def place_geoid(state: str | int, place: str | int) -> str:
    """7-digit place GEOID: 2-digit state + 5-digit place."""
    return norm_fips(state, 2) + norm_fips(place, 5)


def state_of(geoid: str) -> str:
    """State FIPS prefix of any GEOID."""
    if len(geoid) < 2:
        raise GeoError(f"GEOID too short to carry a state: {geoid!r}")
    return geoid[:2]


def is_in_scope(geoid: str) -> bool:
    """True when the GEOID sits in the 50 states or DC."""
    return state_of(geoid) in STATE_FIPS


def usps_of(geoid: str) -> str:
    st = state_of(geoid)
    if st not in STATE_FIPS:
        raise GeoError(f"state FIPS {st!r} is out of scope (territory or invalid)")
    return STATE_FIPS[st]


def classify_place(lsad: str | None) -> str:
    """'cdp' for census designated places, 'incorporated' otherwise."""
    return "cdp" if (lsad or "").strip() == CDP_LSAD else "incorporated"


# ---------------------------------------------------------------- place-county crosswalk


@dataclass(frozen=True)
class PlaceCountyLink:
    """One place's share of one county.

    Places routinely straddle county lines, so this is deliberately many-to-many.
    `weight` is the share of the place's population falling in that county, and the weights
    for a place sum to 1. `docs/methodology.md` section 1 specifies population weighting
    across intersecting counties; this is the table that makes it possible.
    """

    place_geoid: str
    county_geoid: str
    weight: float


class PlaceCountyCrosswalk:
    """Maps places onto counties.

    Two sources can populate this and both produce the same table:

    1. **Census place-county relationship files** — authoritative, preferred.
    2. **Centroid point-in-polygon** against TIGER county boundaries — a fallback that
       assigns each place to exactly one county and therefore loses the split for places
       spanning county lines.

    Which relationship-file URL is current could not be verified while the data hosts were
    blocked, so the source is resolved and pinned at first real download.
    """

    def __init__(self, links: list[PlaceCountyLink]):
        self._by_place: dict[str, list[PlaceCountyLink]] = {}
        for link in links:
            self._by_place.setdefault(link.place_geoid, []).append(link)

    def __len__(self) -> int:
        return len(self._by_place)

    def counties_for(self, place: str) -> list[PlaceCountyLink]:
        return self._by_place.get(place, [])

    def primary_county(self, place: str) -> str | None:
        """The county holding the largest share of the place's population."""
        links = self.counties_for(place)
        if not links:
            return None
        return max(links, key=lambda ln: ln.weight).county_geoid

    def unmatched(self, places: list[str]) -> list[str]:
        """Places with no county assignment — reported, never silently dropped."""
        return [p for p in places if p not in self._by_place]

    @classmethod
    def from_rows(cls, rows: list[dict]) -> PlaceCountyCrosswalk:
        """Build from rows carrying place GEOID, county GEOID and an optional weight.

        Weights are normalized per place. A place listed once gets weight 1.0.
        """
        raw: dict[str, list[tuple[str, float]]] = {}
        for r in rows:
            pl = str(r["place_geoid"]).zfill(7)
            co = str(r["county_geoid"]).zfill(5)
            w = float(r.get("weight", 1.0) or 0.0)
            raw.setdefault(pl, []).append((co, w))

        links: list[PlaceCountyLink] = []
        for pl, pairs in raw.items():
            total = sum(w for _, w in pairs)
            if total <= 0:  # no usable weights - split evenly rather than drop the place
                share = 1.0 / len(pairs)
                links.extend(PlaceCountyLink(pl, co, share) for co, _ in pairs)
            else:
                links.extend(PlaceCountyLink(pl, co, w / total) for co, w in pairs)
        return cls(links)

    @classmethod
    def from_file(cls, path: Path) -> PlaceCountyCrosswalk:
        """Read a delimited crosswalk file.

        Accepts comma or tab separation and is tolerant about column naming, because
        Census relationship files are not consistent between vintages.
        """
        import csv

        text = path.read_text(encoding="utf-8-sig")
        delimiter = "\t" if "\t" in text.splitlines()[0] else ","
        rows: list[dict] = []
        for rec in csv.DictReader(text.splitlines(), delimiter=delimiter):
            norm = {(k or "").strip().lower(): (v or "").strip() for k, v in rec.items()}
            place = norm.get("place_geoid") or norm.get("geoid_place") or norm.get("placefp")
            county = norm.get("county_geoid") or norm.get("geoid_county") or norm.get("countyfp")
            if not place or not county:
                continue
            rows.append(
                {
                    "place_geoid": place,
                    "county_geoid": county,
                    "weight": norm.get("weight") or norm.get("pop_share") or 1.0,
                }
            )
        return cls.from_rows(rows)


# ---------------------------------------------------------------- real-file constructors

COUNTY_SEPARATOR = "~~~"


def county_name_index(rows: list[dict[str, str]]) -> dict[tuple[str, str], str]:
    """(USPS, upper-cased county name) -> county GEOID, built from the Gazetteer.

    Needed because `national_place2020.txt` names a place's counties rather than coding
    them. Names are matched within a state, since county names repeat across states.
    """
    index: dict[tuple[str, str], str] = {}
    for row in rows:
        geoid = norm_fips(row["GEOID"], 5)
        if not is_in_scope(geoid):
            continue
        index[(row.get("USPS", ""), row.get("NAME", "").strip().upper())] = geoid
    return index


def parse_place_codes(
    path: Path, index: dict[tuple[str, str], str]
) -> tuple[list[dict], dict[str, str], list[str]]:
    """Read `national_place2020.txt`.

    Returns (crosswalk rows, place_geoid -> 'cdp'|'incorporated', unmatched county names).

    Multiple counties are separated by `~~~`. Rows carry weight 0, meaning "no population
    split known" — `PlaceCountyCrosswalk.from_rows` then divides evenly. PEP weights
    override these wherever they exist.
    """
    rows: list[dict] = []
    classes: dict[str, str] = {}
    unmatched: list[str] = []

    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    header = [h.strip().upper() for h in lines[0].split("|")]
    col = {name: i for i, name in enumerate(header)}

    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) < len(header):
            continue
        usps = parts[col["STATE"]].strip()
        geoid = place_geoid(parts[col["STATEFP"]], parts[col["PLACEFP"]])
        if not is_in_scope(geoid):
            continue

        classes[geoid] = (
            "cdp" if "DESIGNATED" in parts[col["TYPE"]].upper() else "incorporated"
        )

        for name in parts[col["COUNTIES"]].split(COUNTY_SEPARATOR):
            name = name.strip()
            if not name:
                continue
            county = index.get((usps, name.upper()))
            if county is None:
                unmatched.append(f"{usps}/{name}")
                continue
            rows.append({"place_geoid": geoid, "county_geoid": county, "weight": 0})

    return rows, classes, unmatched


def build_crosswalk(
    place_code_rows: list[dict], pep_weight_rows: list[dict]
) -> tuple[PlaceCountyCrosswalk, dict[str, int]]:
    """Combine both crosswalk sources, preferring real population weights.

    PEP supplies place x county population for incorporated places. Census designated
    places are absent from PEP, so they fall back to an even split across their listed
    counties — recorded in the returned stats rather than hidden, since an even split is a
    guess and roughly 1,300 places span more than one county.
    """
    weighted_places = {r["place_geoid"] for r in pep_weight_rows}
    combined = list(pep_weight_rows)
    combined += [r for r in place_code_rows if r["place_geoid"] not in weighted_places]

    stats = {
        "places_with_population_weights": len(weighted_places),
        "places_evenly_split": len(
            {r["place_geoid"] for r in place_code_rows if r["place_geoid"] not in weighted_places}
        ),
    }
    return PlaceCountyCrosswalk.from_rows(combined), stats


# ------------------------------------------------------------------- geographic fallback


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in statute miles."""
    import math

    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_county(lat: float, lon: float, centroids: dict[str, tuple[float, float]],
                   same_state: str | None = None) -> str | None:
    """County whose centroid is closest to a point, optionally constrained to one state.

    A fallback for places whose county could not be matched by name. The live case is
    **Connecticut**, which replaced its eight counties with nine planning regions for
    Census purposes in 2022: the 2020 place-codes file still names the old counties while
    the 2024 Gazetteer carries the new regions, so 216 name lookups fail.

    Implemented generally rather than as a Connecticut special case, because the same thing
    will happen again the next time a state redraws. Centroid distance is approximate — for
    a large county a place's centroid may be nearer a neighbour's centre — so its use is
    counted in the build report rather than passing silently.
    """
    best, best_d = None, float("inf")
    for geoid, (clat, clon) in centroids.items():
        if same_state and not geoid.startswith(same_state):
            continue
        d = haversine_miles(lat, lon, clat, clon)
        if d < best_d:
            best, best_d = geoid, d
    return best


def read_population_centroids(path: Path) -> dict[str, tuple[float, float]]:
    """County GEOID -> population-weighted centroid (lat, lon).

    A county's geometric centroid can sit far from where anyone lives — empty uplands,
    desert, water. For anything people actually experience (climate, air, travel time)
    the population-weighted centre is the honest reading. Dauphin County's geometric
    centroid is 7.5 miles north of its population centroid, biasing its winter temperature
    about 3F colder than Harrisburg itself.
    """
    import csv

    out: dict[str, tuple[float, float]] = {}
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    for row in csv.DictReader(text.splitlines()):
        row = {(k or "").strip().upper(): (v or "").strip() for k, v in row.items()}
        try:
            geoid = county_geoid(row["STATEFP"], row["COUNTYFP"])
            out[geoid] = (float(row["LATITUDE"]), float(row["LONGITUDE"]))
        except (KeyError, ValueError, GeoError):
            continue
    return out
