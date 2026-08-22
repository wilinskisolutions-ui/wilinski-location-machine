# Anti-bias — the five mechanisms

This is the intellectual core of the project. Each countermeasure below is a **build
requirement with a named artifact**, not an aspiration. If a countermeasure has no
artifact, it is not implemented.

---

## 1. Recency bias

**The bias.** Search engines and language models weight recent content. Whatever is
currently being written about wins, regardless of whether anything changed on the ground.
A place profiled in this month's articles outranks an identical place profiled in 2011.

**Why it produces the observed shortlist.** Greenville, Raleigh, and Charlotte are in a
sustained content cycle. Retrieval finds the cycle, not the place.

**Countermeasure.** Every ranking input comes from a versioned bulk dataset with a pinned
vintage and a recorded checksum. No web content ever enters a score (Principle 5). The
pipeline is reproducible: re-running it next year with the same pinned vintages produces
identical output, and any change is attributable to a deliberate version bump.

**Artifact.** `data/raw/MANIFEST.json` — one row per source file: URL, vintage, retrieval
date, SHA-256. Scoring refuses to run against an unmanifested file.

---

## 2. SEO and content-marketing bias

**The bias.** Relocation content is an industry. Realtors, developers, chambers of
commerce, and moving companies fund content for the places that profit from inbound
moves. Places with no economic interest in attracting you produce no content about
themselves and are therefore invisible.

**Why it matters here.** Invisibility is uncorrelated with quality. A town that is a
superb fit and has no marketing budget cannot be found by searching.

**Countermeasure.** The universe is enumerated from Census TIGER/Gazetteer files **before
any preference is known** (Principle 1), and every member is scored on identical
indicators (Principle 2). A place with zero internet presence receives exactly the same
treatment as one with ten thousand articles, because presence is not an input.

**Artifact.** `data/processed/universe.parquet`, built and committed in Phase 1, with a
row count assertion. Any later change to the universe is a logged decision, not a
side effect.

---

## 3. Migration-momentum bias

**The bias.** A place grows, so it gets covered; coverage draws more people; growth
becomes the story. Recent in-migration is thereby laundered into apparent evidence of
quality. It is partly self-fulfilling and partly a lagging indicator of prices that have
already risen.

**Countermeasure.** Measure the hype directly and check the ranking against it. Build a
**hype index** from IRS/Census county migration flows, Zillow price appreciation, and
search-interest data. Then regress fit score on hype index and report the residual. Fit
that is *explained* by hype is suspect; fit that survives controlling for hype is the
signal we want.

Every report carries a standing **high-fit / low-hype** section: places in the top decile
of fit and the bottom half of hype. This is the direct antidote to the original complaint.

**Artifact.** `src/wlm/diagnostics/hype.py` → `output/hype_residual.md`, plus the
high-fit/low-hype table in the main report.

**Note.** The hype index is a *diagnostic*, never an input. It never adds to or subtracts
from a score. Penalizing popularity would be its own bias.

---

## 4. Data-coverage bias

**The bias.** Large, wealthy, well-instrumented places report more data. If a missing
value is treated as zero or as average, place size silently becomes a scoring dimension.
This is the most common way tools like this quietly break.

**Countermeasure.** Missing is a distinct state, never a value (Principle 6). Every place
carries a `coverage` figure: the share of weighted indicators for which it has real data.
Aggregation renormalizes over present indicators only, so a place is neither punished nor
rewarded for a gap. Every ranking can be re-run restricted to indicators with near-complete
national coverage; if the top 25 changes materially between the two runs, the gap is the
finding and gets reported.

**Known worst offender.** FBI crime data — agency reporting is voluntary and coverage is
genuinely poor in some states. Flagged explicitly rather than imputed.

**Artifact.** `coverage` column on every row; `output/coverage_report.md`; the
complete-indicators-only robustness re-run.

---

## 5. The household's own priors

**The bias.** The household has already heard of Raleigh. Familiarity feels like
preference, and a name carries every article ever read about it. This bias survives all
four countermeasures above, because it lives in the reader rather than the data.

**Countermeasure — blind evaluation.** Shortlist profiles are presented with names,
states, and identifying details stripped: population, climate, costs, and indicator
values only. The household rates the profiles blind. Names are revealed afterward and the
blind ratings are compared against the named ones. Divergence is informative in both
directions — it exposes both unearned affection and unearned dismissal.

**Countermeasure — calibration set.** Before any ranking is trusted, the household rates
20 places they genuinely know: current residence, previous homes, places visited, and
places actively rejected. The fitted weights must approximately reproduce those ratings.
**If the model cannot recover judgments the household already holds, the weights are wrong
and the ranking is not yet trustworthy.** Skipping this step is the most common way
projects like this fail — they produce confident output that was never validated against
anything.

**Artifact.** `src/wlm/diagnostics/blind.py` → `output/blind_profiles.md`;
`profiles/calibration.yaml` and `output/calibration_fit.md`.

---

## The stacking trap

**Specific to this household, and the reason it is written down.**

The household describes itself as more conservative. A political preference expressed at
the state level points at Texas, Florida, Tennessee, and the Carolinas — which is
precisely where migration-momentum bias (#3) already points. **The bias and the preference
stack.** Following both would reproduce the original shortlist by a different route and
feel like independent confirmation.

Three requirements follow, all due in Phase 4:

1. **Every ranking is produced twice** — with and without the political layer — and the
   rank delta is reported per place. The cost of the filter is always visible.
2. **Counter-axis surfacing.** High-fit places on the other side of the political axis are
   always shown, so the trade-off is a choice rather than an invisible exclusion.
3. **County granularity is the substantive fix.** Partisan lean varies far more *within*
   states than between them. There are strongly conservative counties in Oregon, Michigan,
   Minnesota, and Pennsylvania whose climate, cost, and amenity profiles differ completely
   from the Sunbelt. A state-level heuristic cannot see them; a 3,100-county universe can.
   **This is the concrete payoff of choosing the wide net.**

---

## Diagnostics summary

| Diagnostic | Question it answers | Output |
|---|---|---|
| Hype residual | Is fit explained by popularity? | `output/hype_residual.md` |
| High-fit / low-hype | What are we missing that nobody writes about? | main report section |
| Coverage report | Is size masquerading as quality? | `output/coverage_report.md` |
| Complete-only re-run | Does the answer survive dropping patchy indicators? | rank-delta table |
| Weight sensitivity | Is this rank real or a coin flip? | stability band per place |
| Political with/without | What does the filter cost? | rank-delta table |
| Blind evaluation | Do they like the place or the name? | `output/blind_profiles.md` |
| Calibration fit | Do the weights reproduce known judgments? | `output/calibration_fit.md` |
