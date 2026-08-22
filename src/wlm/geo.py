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
