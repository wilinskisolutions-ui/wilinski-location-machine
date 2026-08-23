"""Turn a completed session into a preference profile.

Writes `profiles/<person>.yaml`: domain weights, curve overrides, knockouts, sensitive
opt-ins and the qualitative notes. This is the file Phase 4 scores against.

Two rules from GOAL.md are enforced here rather than assumed:
  * Principle 10 — sensitive dimensions stay at weight 0 unless explicitly opted into.
  * Principle 7 — weights come from the elicited answers, never from the placeholders in
    config/domains.yaml.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import yaml

from wlm.elicit import compare, domain_weights_from_choices, fit_choices, normalize_budget
from wlm.paths import CONFIG, PROCESSED

# How far each step on the "compared to Harrisburg" scale moves a band, as a fraction of
# the indicator's national spread. One step is a noticeable but not drastic change.
STEP_FRACTION = 0.6
BAND_HALF_WIDTH = 0.5  # half-width of the accepted band, also in national standard deviations


def _registry() -> dict[str, dict]:
    return {i["id"]: i for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]}


def _spreads() -> dict[str, tuple[float, float]]:
    """National mean and standard deviation per indicator, for scaling band offsets."""
    f = pl.read_parquet(PROCESSED / "features.parquet").filter(pl.col("value").is_not_null())
    stats = f.group_by("indicator_id").agg(
        pl.col("value").mean().alias("mean"), pl.col("value").std().alias("std")
    )
    return {r["indicator_id"]: (r["mean"], r["std"] or 0.0) for r in stats.iter_rows(named=True)}


def build_profile(session, questions: list[dict]) -> dict:
    registry = _registry()
    spreads = _spreads()
    answers = session.answers

    by_id = {q["id"]: q for q in questions}
    domain_of = {i: e["domain"] for i, e in registry.items()}
    curves = {i: e["curve"] for i, e in registry.items()}

    # --- weights from the trade-off block ---
    tasks = [q for q in questions if q["type"] == "choice_pair"]
    fit = fit_choices(tasks, answers, directions=curves)
    revealed = domain_weights_from_choices(fit, domain_of)

    # --- weights from the stated budget ---
    budget_raw = answers.get("budget_allocation") or {}
    stated = normalize_budget({k: float(v) for k, v in budget_raw.items()})

    # Blend, preferring the revealed weights when the choices carry signal. Stated
    # allocation alone is closer to self-report, which Principle 7 exists to avoid.
    if fit.is_informative and revealed:
        weights = {d: round(0.65 * revealed.get(d, 0) + 0.35 * stated.get(d, 0), 2)
                   for d in set(revealed) | set(stated)}
        weights = normalize_budget(weights)
        basis = "trade-off choices (65%) blended with stated allocation (35%)"
    else:
        weights = stated
        basis = "stated allocation only — trade-off choices did not carry enough signal"

    # --- curve overrides from the anchored band questions ---
    overrides: dict[str, dict] = {}
    for qid, value in answers.items():
        if not qid.startswith("band_"):
            continue
        indicator = qid[len("band_"):]
        question, entry = by_id.get(qid), registry.get(indicator)
        if not question or not entry or indicator not in spreads:
            continue
        try:
            offset = question["offsets"][question["options"].index(value)]
        except (ValueError, KeyError, IndexError):
            continue
        if offset is None:  # "don't care" — leave the indicator unweighted rather than guess
            overrides[indicator] = {"indifferent": True}
            continue

        anchor = float(question["anchor"].split(":")[-1].strip()
                       .replace("$", "").replace(",", "").replace("°F", "")
                       .replace('"', "").replace(" yrs", "").replace("%", "")
                       .replace("k", "000").split()[0])
        mean, std = spreads[indicator]
        step = (std or abs(mean) * 0.1) * STEP_FRACTION
        centre = anchor + offset * step
        half = (std or abs(mean) * 0.1) * BAND_HALF_WIDTH
        overrides[indicator] = {
            "curve": "ideal_band",
            "curve_params": {
                "lo": round(centre - half, 2),
                "hi": round(centre + half, 2),
                "shoulder": round(half * 2, 2),
            },
            "elicited_from": qid,
        }

    # --- knockouts ---
    knockouts = []
    for q in questions:
        target = q.get("maps_to", {})
        if target.get("kind") != "knockout":
            continue
        value = answers.get(q["id"])
        if value not in (None, ""):
            knockouts.append({"indicator": target["target"], "op": target.get("op", "max"),
                              "value": value, "from": q["id"]})

    # --- sensitive: opt-in only (Principle 10) ---
    opt_in = answers.get("q_sensitive_optin") or []
    sensitive = [o for o in opt_in if o != "None of these"] if isinstance(opt_in, list) else []

    notes = {
        q["maps_to"]["target"]: answers[q["id"]]
        for q in questions
        if q.get("maps_to", {}).get("kind") == "qualitative_note" and answers.get(q["id"])
    }

    return {
        "person": session.person,
        "elicited_on": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": basis,
        "quality": {
            "choices_answered": fit.n_choices,
            "model_accuracy": round(fit.accuracy, 3),
            "informative": fit.is_informative,
            "contradictions": fit.contradictions,
            "stated_vs_revealed": compare(stated, revealed),
        },
        "domain_weights": weights,
        "curve_overrides": overrides,
        "knockouts": knockouts,
        "sensitive_opt_in": sensitive,
        "notes": notes,
    }


def write_profile(session, questions: list[dict], path: Path) -> Path:
    if not session.can_write_profile():
        raise ValueError(f"{session.person} may not write a profile")
    profile = build_profile(session, questions)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(profile, sort_keys=False, allow_unicode=True))
    return path


def load_profile(path: Path) -> dict:
    """Read and validate a profile against the registries."""
    profile = yaml.safe_load(Path(path).read_text())
    registry = _registry()
    domains = {d["id"] for d in yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]}
    problems = []

    weights = profile.get("domain_weights") or {}
    if weights:
        unknown = set(weights) - domains
        if unknown:
            problems.append(f"unknown domains in weights: {sorted(unknown)}")
        total = sum(weights.values())
        if abs(total - 100) > 1.0:
            problems.append(f"domain weights sum to {total:.1f}, expected 100")

    for indicator in profile.get("curve_overrides") or {}:
        if indicator not in registry:
            problems.append(f"curve override for unregistered indicator '{indicator}'")

    for knockout in profile.get("knockouts") or []:
        if knockout.get("indicator") not in registry:
            problems.append(f"knockout on unregistered indicator '{knockout.get('indicator')}'")

    if problems:
        raise ValueError(f"{Path(path).name} is invalid:\n  " + "\n  ".join(problems))
    return profile
