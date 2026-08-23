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

from wlm.elicit import (
    blend,
    compare,
    domain_weights_from_choices,
    fit_choices,
    normalize_budget,
)
from wlm.paths import CONFIG, PROCESSED

# How far each step on the "compared to Harrisburg" scale moves a band, as a fraction of
# the indicator's national spread. One step is a noticeable but not drastic change.
STEP_FRACTION = 0.6
BAND_HALF_WIDTH = 0.5  # half-width of the accepted band, also in national standard deviations


def locked_weights() -> dict[str, float]:
    """Domain weights the household pinned by hand on the start screen.

    Principle 7 says weights come from forced trade-offs. Locking one overrides that for
    that domain — deliberately, and recorded in the profile so it is never mistaken for an
    elicited number.
    """
    domains = yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
    return {
        d["id"]: float(d["default_weight"])
        for d in domains
        if d.get("locked") and d.get("scoring")
    }


def domains_without_data() -> set[str]:
    """Domains carrying no populated indicator at all.

    A weight assigned to one of these evaporates on renormalisation. Emil could rate
    schools his top priority and it would change nothing, silently — so it is reported
    instead of swallowed.
    """
    registry = _registry()
    f = pl.read_parquet(PROCESSED / "features.parquet").filter(pl.col("value").is_not_null())
    populated = set(f["indicator_id"].unique())
    by_domain: dict[str, list[str]] = {}
    for iid, entry in registry.items():
        by_domain.setdefault(entry["domain"], []).append(iid)
    return {d for d, ids in by_domain.items() if not any(i in populated for i in ids)}


def _registry() -> dict[str, dict]:
    return {i["id"]: i for i in yaml.safe_load((CONFIG / "indicators.yaml").read_text())["indicators"]}


class OptInError(ValueError):
    """A sensitive opt-in could not be resolved to the indicators it switches on."""


def resolve_sensitive_opt_in(questions: list[dict], answers: dict) -> tuple[list[str], list[str]]:
    """Which sensitive indicators the household actually turned on.

    Returns `(labels, indicator_ids)`. The question declares the mapping, so an option can
    never drift away from the indicator it controls without this raising.

    This exists because the first version stored the option labels and nothing read them:
    opting in changed nothing, while allocating budget points to the sensitive domain gave
    it weight with no opt-in at all. Principle 10 was broken in both directions and the
    audit still passed, because the audit only inspected the config default.
    """
    question = next(
        (q for q in questions if q.get("maps_to", {}).get("kind") == "sensitive_opt_in"),
        None,
    )
    if question is None:
        return [], []

    chosen = answers.get(question["id"]) or []
    if not isinstance(chosen, list):
        return [], []

    mapping = question.get("option_indicators") or {}
    labels, indicators = [], []
    for label in chosen:
        if label not in mapping:
            raise OptInError(
                f"option {label!r} on {question['id']} names no indicator; "
                "add it to option_indicators in questionnaire/bank.yaml"
            )
        indicator = mapping[label]
        if indicator is None:  # an explicit "none of these"
            continue
        labels.append(label)
        indicators.append(indicator)
    return labels, indicators


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
    data_less = domains_without_data()
    locked = locked_weights()
    if fit.is_informative and revealed:
        weights, weight_notes = blend(stated, revealed, data_less=data_less)
        basis = "trade-off choices (65%) blended with stated allocation (35%)"
        if locked:
            # A locked weight was set deliberately on the start screen and survives
            # elicitation. This is an explicit, recorded override of Principle 7 rather
            # than a silent one — which is the difference that matters.
            weights.update(locked)
            weights = normalize_budget(weights)
            weight_notes.append(
                "locked by hand, not elicited: "
                + ", ".join(f"{k}={v:g}" for k, v in sorted(locked.items()))
            )
    else:
        weights, weight_notes = normalize_budget(stated), [
            "trade-off choices did not carry enough signal; stated allocation only"
        ]
        basis = "stated allocation only — the choices were too close to random to fit"

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

        # Read the raw value. Never re-parse the formatted string: it is rounded, unit-
        # suffixed and sometimes rescaled for display, and getting that wrong is silent.
        anchor = question.get("anchor_value")
        if anchor is None:
            continue
        anchor = float(anchor)
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
    #
    # A deal-breaker is compared against a number, so an answer that is a phrase has to
    # declare what number it means. `q_max_hub_drive` offered "Under an hour" and mapped
    # straight to a mileage threshold: the filter reached the engine as a string, failed
    # to parse, and never ran. The mapping lives in the bank next to the options it
    # translates, so rewording one cannot quietly disconnect it.
    knockouts = []
    for q in questions:
        target = q.get("maps_to", {})
        if target.get("kind") != "knockout":
            continue
        value = answers.get(q["id"])
        if value in (None, ""):
            continue

        option_values = q.get("option_values")
        if option_values is not None:
            if value not in option_values:
                raise OptInError(
                    f"{q['id']}: answer {value!r} has no numeric equivalent; add it to "
                    "option_values in questionnaire/bank.yaml"
                )
            value = option_values[value]
            if value is None:  # an explicit "no limit"
                continue

        try:
            value = float(value)
        except (TypeError, ValueError):
            raise OptInError(
                f"{q['id']}: knockout on '{target['target']}' cannot use answer {value!r} — "
                "a deal-breaker must reduce to a number"
            ) from None

        knockouts.append({"indicator": target["target"], "op": target.get("op", "max"),
                          "value": value, "from": q["id"]})

    # --- sensitive: opt-in only (Principle 10) ---
    #
    # Enforced here, not merely recorded. The sensitive domain sits in the budget question
    # like any other, so points can be allocated to it without ever opting in; without this
    # gate those points reach the ranking. Nothing downstream needs to remember the rule.
    sensitive, sensitive_indicators = resolve_sensitive_opt_in(questions, answers)
    if not sensitive_indicators and weights.get("sensitive"):
        forfeited = weights["sensitive"]
        weights["sensitive"] = 0.0
        weights = normalize_budget(weights)
        weight_notes.append(
            f"sensitive weight ({forfeited:g} points) dropped to 0 and redistributed: "
            "nothing was opted into. Principle 10 — these count only when asked for."
        )
    elif sensitive_indicators:
        # Opted in, so the domain weight stands — but only the chosen indicators carry it.
        # Turning on political lean must not also turn on religion and ancestry.
        off = [
            i for i, e in registry.items()
            if e.get("sensitive") and i not in sensitive_indicators
        ]
        weight_notes.append(
            "sensitive opted in: " + ", ".join(sorted(sensitive_indicators))
            + (f"; left off: {', '.join(sorted(off))}" if off else "")
        )

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
            "weighting_notes": weight_notes,
        },
        "domain_weights": weights,
        # Within-domain weights, straight from the trade-off fit.
        #
        # Without these, a domain weight is spread evenly over everything in it: weighting
        # climate at 30 points diluted winter temperature to about 1/16, because the domain
        # holds sixteen indicators. A couple asking for warm winters got places averaging
        # 48F instead of the 50-70F they asked for. The end-to-end test caught it.
        "indicator_weights": {k: round(v, 5) for k, v in fit.weights.items()},
        "curve_overrides": overrides,
        "knockouts": knockouts,
        "sensitive_opt_in": sensitive,
        # The resolved ids are what the engine reads. Keeping the labels too means the
        # profile still says, in the household's own words, what was agreed to.
        "sensitive_indicators": sensitive_indicators,
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
