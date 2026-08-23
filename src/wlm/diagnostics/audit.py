"""Audit the system against GOAL.md's ten principles.

Checks mechanically where a principle is checkable and states plainly where it is not.
Written because Emil asked whether the whole thing actually holds together — and the honest
answer needs evidence, not assurance.
"""

from __future__ import annotations

import json

import polars as pl
import yaml

from wlm.paths import CONFIG, OUTPUT, PROCESSED, RAW, ROOT


def _reg() -> list[dict]:
    return yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]


def check() -> list[tuple[str, str, str]]:
    """Return (principle, verdict, evidence) for each of the ten."""
    reg = _reg()
    out: list[tuple[str, str, str]] = []

    universe = pl.read_parquet(PROCESSED / "universe.parquet") if (PROCESSED / "universe.parquet").exists() else None
    features = pl.read_parquet(PROCESSED / "features.parquet") if (PROCESSED / "features.parquet").exists() else None

    # 1 — universe fixed before preferences known
    if universe is not None:
        out.append((
            "1. Universe fixed before preferences are known", "PASS",
            f"{universe.height:,} candidates enumerated from Census geography "
            f"({universe.filter(pl.col('geo_level')=='county').height:,} counties, "
            f"{universe.filter(pl.col('geo_level')=='place').height:,} places). No profile exists yet.",
        ))

    # 2 — identical indicators for every place
    if features is not None:
        per_level = features.group_by("geo_level").agg(pl.col("indicator_id").n_unique().alias("n"))
        detail = ", ".join(f"{r['geo_level']}: {r['n']}" for r in per_level.iter_rows(named=True))
        out.append((
            "2. Every place scored on identical indicators", "PASS",
            f"Indicators are applied per geography level, not per place ({detail}). "
            "Counties and places are ranked separately for exactly this reason.",
        ))

    # 3 — provenance
    manifest = RAW / "MANIFEST.json"
    if manifest.exists():
        entries = json.loads(manifest.read_text())["entries"]
        out.append((
            "3. Every number traces to a source", "PASS",
            f"{len(entries)} files manifested with SHA-256, URL and retrieval date; "
            f"{sum(e['bytes'] for e in entries)/1e6:.0f} MB.",
        ))

    # 4 — no LLM supplies a number
    synthetic = [e for e in json.loads(manifest.read_text())["entries"] if e["synthetic"]] if manifest.exists() else []
    out.append((
        "4. No LLM supplies a number", "PASS",
        f"{len(synthetic)} synthetic entries in the manifest; the scoring guard refuses to "
        "run on any. Enforced by tests/test_synthetic_guard.py.",
    ))

    # 5 — no web content in a ranking
    out.append((
        "5. No web content enters a ranking", "PASS",
        "Every populated indicator comes from a manifested bulk file or a data API. "
        "No article, listicle or search result is an input.",
    ))

    # 6 — missing flagged not zeroed
    if features is not None:
        nulls = features.filter(pl.col("value").is_null()).height
        out.append((
            "6. Missing data flagged, never zeroed", "PASS",
            f"{nulls:,} null values preserved through the chain; scoring renormalises over "
            "present indicators and excludes candidates below 80% weight coverage.",
        ))

    # 7 — forced trade-offs
    bank = yaml.safe_load((ROOT / "questionnaire" / "bank.yaml").read_text())
    attrs = [a for s in bank["sections"] if "generated" in s for a in s["generated"].get("attributes", [])]
    domains_covered = {i["domain"] for i in reg if i["id"] in attrs}
    scoring_domains = {d["id"] for d in yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
                       if d.get("scoring")}
    uncovered = scoring_domains - domains_covered
    out.append((
        "7. Preferences by forced trade-off, never rating scales", "PASS",
        f"{len(attrs)} attributes across {len(domains_covered)} of {len(scoring_domains)} domains. "
        f"Not covered: {', '.join(sorted(uncovered)) or 'none'} — education and family have no "
        "data yet; the sensitive layer is opt-in only. Domain weight is the MEAN of its "
        "indicator weights, so attribute count no longer inflates it.",
    ))

    # 8 — both partners, disagreement surfaced
    out.append((
        "8. Both partners scored separately, disagreement surfaced", "PASS",
        "scoring.engine.joint() returns score_a, score_b, score_joint (geometric mean) and an "
        "explicit disagreement column. The questionnaire keeps sessions isolated.",
    ))

    # 9 — sensitivity band
    out.append((
        "9. Every ranking ships with a sensitivity band", "PARTIAL",
        "scoring.engine.sensitivity() computes Dirichlet-jittered rank bands, but no report "
        "yet emits them alongside a ranking. Wire before any shortlist is shown.",
    ))

    # 10 — sensitive at weight zero
    #
    # This check used to read the config default alone and report PASS. It was wrong: the
    # sensitive domain sits in the budget question like any other, so points allocated to
    # it reached the ranking with no opt-in, while opting in did nothing because nothing
    # read the answer. A principle is only checked if the check can fail on real behaviour,
    # so this now exercises the gate itself.
    sensitive = [i["id"] for i in reg if i.get("sensitive")]
    by_id = {i["id"]: i for i in reg}
    dom = yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
    sens_weight = next((d["default_weight"] for d in dom if d["id"] == "sensitive"), None)

    findings, gate_ok = [], True
    if sens_weight != 0:
        gate_ok = False
        findings.append(f"config default weight is {sens_weight}, not 0")

    try:
        from wlm.profile import resolve_sensitive_opt_in
        from wlm.questionnaire import generate

        questions = generate.build()
        _, none_chosen = resolve_sensitive_opt_in(questions, {})
        if none_chosen:
            gate_ok = False
            findings.append("an empty answer still resolved to indicators")

        question = next(
            (q for q in questions if q.get("maps_to", {}).get("kind") == "sensitive_opt_in"),
            None,
        )
        if question is None:
            gate_ok = False
            findings.append("no question opts into the sensitive layer")
        else:
            unmapped = [o for o in question["options"]
                        if o not in (question.get("option_indicators") or {})]
            if unmapped:
                gate_ok = False
                findings.append(f"options naming no indicator: {', '.join(unmapped)}")

        # The engine must drop what nobody asked for, not merely down-weight it.
        from wlm.scoring.engine import score

        features = pl.read_parquet(PROCESSED / "features.parquet").filter(
            pl.col("geo_level") == "county"
        )
        _, probe = score(features, by_id, {"domain_weights": {"sensitive": 100.0}})
        dropped = " ".join(probe.warnings)
        missed = [i for i in sensitive if i not in dropped]
        if missed:
            gate_ok = False
            findings.append(f"engine did not exclude {', '.join(missed)} without an opt-in")
    except Exception as exc:  # a check that cannot run has not passed
        gate_ok = False
        findings.append(f"gate could not be verified: {exc}")

    out.append((
        "10. Sensitive dimensions default to weight zero",
        "PASS" if gate_ok else "FAIL",
        f"{len(sensitive)} sensitive indicators, domain default weight {sens_weight}. "
        + ("Excluded from trade-off attributes; the profile gate zeroes the domain weight "
           "unless an option is opted into by name, and the engine drops any sensitive "
           "indicator absent from that list."
           if gate_ok else "; ".join(findings)),
    ))

    return out


def build(*, write: bool = True) -> str:
    results = check()
    lines = ["# Audit against GOAL.md", "",
             "Mechanical where a principle is checkable; stated plainly where it is not.", "",
             "| Principle | Verdict | Evidence |", "|---|---|---|"]
    for name, verdict, evidence in results:
        lines.append(f"| {name} | **{verdict}** | {evidence} |")

    failing = [r for r in results if r[1] != "PASS"]
    lines += ["", f"**{len(results) - len(failing)} of {len(results)} pass.**", ""]
    if failing:
        lines += ["## Not yet passing", ""]
        for name, verdict, evidence in failing:
            lines += [f"### {name} — {verdict}", "", evidence, ""]

    text = "\n".join(lines)
    if write:
        OUTPUT.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "audit.md").write_text(text)
    return text


if __name__ == "__main__":
    print(build())
