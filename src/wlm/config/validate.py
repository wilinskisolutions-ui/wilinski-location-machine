"""Validate the configuration registries.

Run:  python -m wlm.config.validate   (or: make validate)

Checks the invariants that GOAL.md states as principles, so a violation is caught
mechanically rather than by someone remembering. Exits non-zero on any error.

Deliberately stdlib-only apart from PyYAML: the validator must run anywhere, with no
install step, in a project whose whole premise is reproducibility.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config"
DOCS = ROOT / "docs"

# "district" is school-district geography. It does not nest inside counties or places,
# so an indicator sourced at district level declares `crosswalk_from: district` and the
# level it lands at in `geo_level`.
GEO_LEVELS = {"county", "place", "metro", "state", "district"}
CURVES = {"higher_better", "lower_better", "ideal_band", "ideal_point"}
TRANSFORMS = {"none", "log", "sqrt", "per_capita"}
MONOTONE = {"higher_better", "lower_better"}

# Whether the preferred direction is the same for everyone. Nobody wants more crime or
# dirtier air, so asking which way they prefer it is a wasted question — only the
# trade-off weight is elicitable. Town size and winter temperature genuinely differ.
DIRECTIONS = {"universal", "personal"}

errors: list[str] = []
warnings: list[str] = []
notes: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load(name: str, key: str) -> list[dict]:
    path = CONFIG / name
    if not path.exists():
        err(f"{name}: missing")
        return []
    data = yaml.safe_load(path.read_text()) or {}
    items = data.get(key)
    if not isinstance(items, list):
        err(f"{name}: expected a top-level '{key}:' list")
        return []
    return items


def dupes(items: list[dict], label: str) -> None:
    seen: set[str] = set()
    for it in items:
        i = it.get("id")
        if not i:
            err(f"{label}: entry with no id: {it!r:.80}")
        elif i in seen:
            err(f"{label}: duplicate id '{i}'")
        else:
            seen.add(i)


def check_domains(domains: list[dict]) -> None:
    dupes(domains, "domains")
    scoring_total = 0.0
    for d in domains:
        did, w = d.get("id"), d.get("default_weight")
        if not isinstance(w, (int, float)):
            err(f"domain '{did}': default_weight must be a number")
            continue
        if w < 0:
            err(f"domain '{did}': default_weight is negative")
        if d.get("scoring"):
            scoring_total += w
        elif w != 0:
            err(f"domain '{did}': non-scoring domains must have default_weight 0, got {w}")
        if "locked" in d and not isinstance(d["locked"], bool):
            err(f"domain '{did}': 'locked' must be true or false")

        # Principle 10 — sensitive dimensions ship at weight zero.
        if d.get("sensitive") and w != 0:
            err(
                f"domain '{did}': PRINCIPLE 10 VIOLATION — sensitive domain has "
                f"default_weight {w}, must be 0 until explicitly opted in"
            )
    if abs(scoring_total - 100.0) > 1e-6:
        err(f"scoring domain default_weights sum to {scoring_total}, expected 100")


def check_sources(sources: list[dict]) -> None:
    dupes(sources, "sources")
    catalog = (DOCS / "data-sources.md").read_text() if (DOCS / "data-sources.md").exists() else ""
    if not catalog:
        err("docs/data-sources.md: missing — every source needs a narrative entry")
    for s in sources:
        sid = s.get("id")
        for field in ("name", "url", "geo_levels", "vintage", "license"):
            if not s.get(field):
                err(f"source '{sid}': missing required field '{field}'")
        url = s.get("url", "")
        if not url.startswith("https://"):
            err(f"source '{sid}': url must be https, got '{url}'")
        bad = set(s.get("geo_levels") or []) - GEO_LEVELS
        if bad:
            err(f"source '{sid}': unknown geo_levels {sorted(bad)}")
        # Cross-doc drift: the machine registry and the narrative catalog must agree.
        host = urlparse(url).netloc.removeprefix("www.")
        if catalog and host and host not in catalog:
            err(f"source '{sid}': host '{host}' absent from docs/data-sources.md")


def check_indicators(indicators: list[dict], domains: list[dict], sources: list[dict]) -> None:
    dupes(indicators, "indicators")
    dmap = {d["id"]: d for d in domains if d.get("id")}
    smap = {s["id"]: s for s in sources if s.get("id")}
    used_domains: set[str] = set()
    n_provisional = 0

    for ind in indicators:
        iid = ind.get("id")
        dom, src = ind.get("domain"), ind.get("source")

        if dom not in dmap:
            err(f"indicator '{iid}': unknown domain '{dom}'")
        elif not dmap[dom].get("scoring"):
            err(f"indicator '{iid}': domain '{dom}' is non-scoring and cannot hold indicators")
        else:
            used_domains.add(dom)

        if src not in smap:
            err(f"indicator '{iid}': unknown source '{src}' (not in config/sources.yaml)")

        geo = ind.get("geo_level")
        xfrom = ind.get("crosswalk_from")
        if geo not in GEO_LEVELS:
            err(f"indicator '{iid}': geo_level '{geo}' not in {sorted(GEO_LEVELS)}")
        elif src in smap:
            offered = smap[src].get("geo_levels") or []
            if xfrom is None:
                # No crosswalk: the source must natively provide the level it lands at.
                if geo not in offered:
                    err(
                        f"indicator '{iid}': geo_level '{geo}' not offered by source '{src}' "
                        f"(offers {offered}) — add 'crosswalk_from' if it is derived"
                    )
            else:
                # Crosswalked: the source provides `crosswalk_from`, the pipeline maps it
                # onto `geo_level`. Recorded here so the derivation is visible in the
                # registry rather than buried in an ingest module.
                if xfrom not in GEO_LEVELS:
                    err(f"indicator '{iid}': crosswalk_from '{xfrom}' not in {sorted(GEO_LEVELS)}")
                elif xfrom not in offered:
                    err(
                        f"indicator '{iid}': crosswalk_from '{xfrom}' not offered by source "
                        f"'{src}' (offers {offered})"
                    )
                if xfrom == geo:
                    err(f"indicator '{iid}': crosswalk_from equals geo_level ('{geo}') — drop it")

        tr = ind.get("transform", "none")
        if tr not in TRANSFORMS:
            err(f"indicator '{iid}': transform '{tr}' not in {sorted(TRANSFORMS)}")

        if not ind.get("unit"):
            err(f"indicator '{iid}': missing 'unit' — raw-value curves are unit-dependent")

        direction = ind.get("direction")
        if direction not in DIRECTIONS:
            err(f"indicator '{iid}': direction must be one of {sorted(DIRECTIONS)}, got {direction!r}")
        elif direction == "universal" and ind.get("curve") in ("ideal_band", "ideal_point"):
            # A band expresses a personal ideal by definition; calling it universal would
            # let the questionnaire skip asking where that ideal actually sits.
            err(f"indicator '{iid}': curve '{ind['curve']}' expresses a personal ideal but "
                "direction says 'universal'")

        # Principle 10, both directions: the sensitive flag and the sensitive domain
        # must agree, so nothing sensitive can hide in a weighted domain.
        in_sensitive_domain = bool(dmap.get(dom, {}).get("sensitive"))
        flagged = bool(ind.get("sensitive"))
        if in_sensitive_domain and not flagged:
            err(f"indicator '{iid}': in sensitive domain but not flagged 'sensitive: true'")
        if flagged and not in_sensitive_domain:
            err(f"indicator '{iid}': flagged sensitive but domain '{dom}' is not a sensitive domain")

        if ind.get("provisional"):
            n_provisional += 1

        check_curve(ind, iid)

    for did, d in dmap.items():
        if d.get("scoring") and did not in used_domains:
            err(f"domain '{did}': scoring domain has no indicators")

    unused = sorted(set(smap) - {i.get("source") for i in indicators})
    if unused:
        notes.append(f"{len(unused)} source(s) registered but not yet used by a seed indicator: {', '.join(unused)}")
    if n_provisional:
        notes.append(f"{n_provisional} indicator(s) carry provisional curve params awaiting Phase 3 elicitation")


def check_curve(ind: dict, iid: str) -> None:
    curve = ind.get("curve")
    params = ind.get("curve_params") or {}

    if curve not in CURVES:
        err(f"indicator '{iid}': curve '{curve}' not in {sorted(CURVES)}")
        return

    if curve in MONOTONE:
        if params:
            err(f"indicator '{iid}': curve '{curve}' operates on percentiles and takes no curve_params")
        return

    # Non-monotone curves act on RAW values and are meaningless without params.
    if curve == "ideal_band":
        lo, hi = params.get("lo"), params.get("hi")
        if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
            err(f"indicator '{iid}': ideal_band requires numeric 'lo' and 'hi'")
        elif lo >= hi:
            err(f"indicator '{iid}': ideal_band needs lo < hi, got lo={lo} hi={hi}")
        sh = params.get("shoulder")
        if sh is None:
            err(f"indicator '{iid}': ideal_band requires 'shoulder' (decay width outside the band)")
        elif not isinstance(sh, (int, float)) or sh <= 0:
            err(f"indicator '{iid}': ideal_band shoulder must be a positive number, got {sh!r}")
        # Optional per-side overrides, for quantities whose scale is not linear.
        for side in ("shoulder_lo", "shoulder_hi"):
            if (v := params.get(side)) is not None and (not isinstance(v, (int, float)) or v <= 0):
                err(f"indicator '{iid}': ideal_band {side} must be a positive number, got {v!r}")

    elif curve == "ideal_point":
        if not isinstance(params.get("target"), (int, float)):
            err(f"indicator '{iid}': ideal_point requires a numeric 'target'")
        tol = params.get("tol")
        if not isinstance(tol, (int, float)) or tol <= 0:
            err(f"indicator '{iid}': ideal_point requires a positive 'tol', got {tol!r}")


def main() -> int:
    domains = load("domains.yaml", "domains")
    sources = load("sources.yaml", "sources")
    indicators = load("indicators.yaml", "indicators")

    if domains:
        check_domains(domains)
    if sources:
        check_sources(sources)
    if indicators and domains and sources:
        check_indicators(indicators, domains, sources)

    scoring = [d for d in domains if d.get("scoring")]
    print(f"domains     {len(domains):>4}  ({len(scoring)} scoring, {len(domains) - len(scoring)} questionnaire-only)")
    print(f"sources     {len(sources):>4}")
    print(f"indicators  {len(indicators):>4}")

    for n in notes:
        print(f"\n  note: {n}")
    for w in warnings:
        print(f"\n  warning: {w}")

    if errors:
        print(f"\nFAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nOK — all registries valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
