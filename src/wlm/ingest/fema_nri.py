"""FEMA National Risk Index — 18 natural hazards as expected annual loss.

This is what turns "is somewhere warm risky?" from a feeling into a number, and it is the
necessary counterweight to a warm-climate preference: warm-and-coastal means hurricanes,
warm-and-inland means heat and drought.

**Sourced from ArcGIS, not hazards.fema.gov.** That host returns 403 to every header
combination — a WAF block rather than an egress policy denial — so the static NRI download
is unreachable. FEMA publishes the same table as a public feature service, which is.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path

import polars as pl

from wlm.geo import is_in_scope, norm_fips
from wlm.ingest.base import emit

SOURCE_ID = "fema_nri"
VINTAGE = "2023"

SERVICE = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
    "National_Risk_Index_Counties/FeatureServer/0"
)
PAGE_SIZE = 2000

# NRI field -> registered indicator id. `*_RISKS` are composite risk scores per hazard.
FIELD_MAP: dict[str, str] = {
    "RISK_SCORE": "hazard_nri_composite",
    "HRCN_RISKS": "hazard_nri_hurricane",
    "WFIR_RISKS": "hazard_nri_wildfire",
    "HWAV_RISKS": "hazard_nri_heatwave",
    "DRGT_RISKS": "hazard_nri_drought",
    "TRND_RISKS": "hazard_nri_tornado",
}

FIPS_FIELD = "STCOFIPS"

# Expected annual loss of *population* (life), per hazard, plus the denominator.
#
# Why this exists alongside the percentiles above: NRI's headline RISK_SCORE reflects
# expected annual **loss**, which scales with how much there is to lose. Los Angeles scores
# 100 partly because Los Angeles contains enormous exposure value. Used raw, it penalises
# populous counties — which would fight this household's amenity preference for a reason
# that has nothing to do with their safety.
#
# EALP divided by population is the measure a person actually cares about: how likely this
# place is to hurt *them*.
# All 17 hazards NRI scores for loss of life. Summing every hazard rather than a chosen
# few avoids quietly deciding which dangers count.
EALP_FIELDS = [
    "AVLN_EALP", "CFLD_EALP", "CWAV_EALP", "ERQK_EALP", "HAIL_EALP", "HWAV_EALP",
    "HRCN_EALP", "ISTM_EALP", "LNDS_EALP", "LTNG_EALP", "IFLD_EALP", "SWND_EALP",
    "TRND_EALP", "TSUN_EALP", "VLCN_EALP", "WFIR_EALP", "WNTW_EALP",
]
POPULATION_FIELD = "POPULATION"


def fetch_features(
    *, service: str = SERVICE, fields: dict[str, str] | None = None, pause: float = 0.2
) -> list[dict]:
    """Page through the feature service and return raw attribute dicts."""
    import requests

    fields = fields or FIELD_MAP
    out_fields = ",".join([FIPS_FIELD, POPULATION_FIELD, *fields, *EALP_FIELDS])
    features: list[dict] = []
    offset = 0

    while True:
        params = {
            "where": "1=1",
            "outFields": out_fields,
            "returnGeometry": "false",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "f": "json",
        }
        url = f"{service}/query?{urllib.parse.urlencode(params)}"
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        payload = resp.json()
        if "error" in payload:
            raise RuntimeError(f"NRI service error: {payload['error']}")

        batch = [f.get("attributes", {}) for f in payload.get("features", [])]
        features.extend(batch)
        if len(batch) < PAGE_SIZE or not payload.get("exceededTransferLimit"):
            break
        offset += PAGE_SIZE
        time.sleep(pause)

    return features


def save_raw(features: list[dict], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(features))
    return path


def ingest(
    path: Path, *, vintage: str = VINTAGE, field_map: dict[str, str] | None = None
) -> pl.DataFrame:
    """Read saved NRI attributes and emit long-form records."""
    field_map = field_map or FIELD_MAP
    features = json.loads(Path(path).read_text())
    records: list[dict] = []

    for row in features:
        raw = row.get(FIPS_FIELD)
        if not raw:
            continue
        geoid = norm_fips(raw, 5)
        if not is_in_scope(geoid):
            continue
        # Per-capita fatality risk: summed expected annual loss of life across hazards,
        # per 100,000 residents. Exposure-normalised, so it says nothing about how much
        # property a county happens to contain.
        pop = row.get(POPULATION_FIELD)
        eal_sum, saw_any = 0.0, False
        for field in EALP_FIELDS:
            v = row.get(field)
            if v not in ("", None):
                try:
                    eal_sum += float(v)
                    saw_any = True
                except (TypeError, ValueError):
                    pass
        records.append(
            {
                "geo_level": "county",
                "geo_id": geoid,
                "indicator_id": "hazard_fatality_risk_per100k",
                "value": (eal_sum / float(pop) * 100_000) if (saw_any and pop) else None,
            }
        )

        for field, indicator in field_map.items():
            value = row.get(field)
            # NRI leaves a hazard blank where it does not apply to a county. Blank means
            # "not assessed", which is not the same claim as zero risk (Principle 6).
            records.append(
                {
                    "geo_level": "county",
                    "geo_id": geoid,
                    "indicator_id": indicator,
                    "value": value if value not in ("", None) else None,
                }
            )

    return emit(records, source_file=Path(path).name, vintage=vintage)
