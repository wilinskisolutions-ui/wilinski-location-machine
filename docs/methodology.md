# Methodology — how a place gets a score

Every decision here was made in Phase 0 so later phases do not relitigate them. Changes
are logged in `CONTEXT.md`.

---

## 1. Geography

Two levels, scored together:

- **County** (~3,143) — the primary unit. Most federal data lands natively at county
  level: hazard, health, climate, employment, income, childcare, elections.
- **Place** (~7,000-8,000 places ≥5,000 population, incorporated and census-designated)
  — the sub-unit people actually
  live in. Carries local taxes, schools, density, walkability, and municipal character.

Places join to counties by FIPS and to metros by CBSA code. A place inherits its county's
and metro's context indicators while keeping its own local ones. This is what stops
"Raleigh" from being one undifferentiated blob: the metro supplies the job market and the
airport, the place supplies the tax rate and the density.

Where a place spans multiple counties, county-level values are population-weighted across
the intersecting counties.

---

## 2. The indicator registry

`config/indicators.yaml` is the single source of truth. **Nothing is scored that is not
registered.** Each entry:

```yaml
- id: hazard_nri_composite
  domain: climate_environment
  label: FEMA National Risk Index, composite
  source: fema_nri              # must exist in docs/data-sources.md
  geo_level: county
  vintage: "2023"
  curve: lower_better
  transform: none               # none | log | sqrt | per_capita
  sensitive: false              # true → forced to weight 0 unless opted in
  notes: 18 hazards, composite expected annual loss score
```

---

## 3. Normalization and preference curves

Raw values are not comparable — dollars, inches of rain, and ratios share no scale. Each
indicator is mapped to a **desirability** in `[0, 1]`, where 1 is ideal for this household.

**Monotone curves** operate on the **percentile rank** within the universe. Percentile is
used rather than z-score because it is robust to the extreme outliers that are everywhere
in US place data (one county's income, another's land area).

| Curve | Definition |
|---|---|
| `higher_better` | `d = pct(v)` |
| `lower_better` | `d = 1 − pct(v)` |

**Non-monotone curves** operate on the **raw value**, because the household states them in
raw units.

| Curve | Definition |
|---|---|
| `ideal_band(lo, hi)` | `d = 1` inside the band; decays smoothly outside over a shoulder width |
| `ideal_point(x, tol)` | `d = exp(−((v − x) / tol)²)` |

**This distinction is load-bearing.** "We want a town between 50,000 and 250,000 people"
is a band on a raw value. A z-score or a percentile cannot express it — under
`higher_better` a 4-million-person county beats the ideal town, which is exactly backwards.
Getting this wrong is the single most common failure mode in tools of this kind, and it
fails silently: the output still looks like a ranking.

---

## 4. Aggregation

Two stages, both **weighted geometric mean**:

```
D_domain = exp( Σ wᵢ · ln(max(dᵢ, ε)) / Σ wᵢ )     ε = 0.01
Score    = exp( Σ w_d · ln(max(D_d, ε)) / Σ w_d )
```

**Why geometric rather than arithmetic.** A weighted arithmetic mean is fully
compensatory: a place that is excellent on nine domains and catastrophic on healthcare
averages out near the top. Real relocation decisions are not like that — one intolerable
dimension disqualifies a place regardless of the rest. The geometric mean punishes low
values disproportionately, so a near-zero domain drags the whole score down. The `ε` floor
keeps the penalty severe but finite, so a single missing-adjacent value cannot annihilate
an otherwise strong candidate.

**Missing data.** Both sums run over **present indicators only**, renormalizing the
weights. A place is neither penalized nor rewarded for a gap (Principle 6). Each row
carries `coverage` = share of weighted indicators actually present.

**Weakest link.** Every row also carries `worst_domain` and its value, so a high total
score built on one severe weakness is visible at a glance rather than buried.

**Domain influence is normalized to match domain weight.** In log space the outer sum is a
weighted arithmetic mean, so a domain's pull on the ranking is `w_d × spread(ln D_d)` — and
that spread is not something the household chose. It falls out of how many overlapping
indicators the domain happens to hold. Measured on the real data against the first
household's weights:

| Domain | Weight | Indicators | Spread | Influence |
|---|---|---|---|---|
| cost_housing | 12 | 6 | 0.723 | **8.68** |
| climate_environment | 12 | 16 | 0.559 | **6.71** |
| family_childcare | 8 | 2 | 0.944 | **7.55** |
| recreation_lifestyle | 8 | 11 | 0.511 | **4.09** |

Climate carried the joint-highest weight and came seventh of ten on influence, below a
domain carrying two-thirds of it — sixteen overlapping climate measures average into a
smooth score that separates almost nobody, while two childcare measures separate sharply.
Nominal weight and real influence had come apart, invisibly.

So `engine.influence_scale` rescales each domain's log score about its own mean to a common
spread before the outer sum, with the factor clamped to `[0.5, 2.5]` so a domain where
places genuinely do score alike cannot have its remaining noise blown up without limit.
Influence then equals `w_d × (common spread)` and tracks weight (measured correlation
0.9999 after the fix, with climate first). The factors are reported per run; the raw,
interpretable 0–1 domain score is what appears in the report, and `worst_domain` is always
the raw figure. The atlas page applies the same factors in `score.js`, held to the engine
by `tests/test_atlas.py`, so moving the weights there ranks by the same rule.

Redundant indicators were also retired to `scoring: false`, which shrinks the disparity at
its source — the rescaling handles what is left.

---

## 4a. Where the weights come from

Principle 7 says weights come from forced trade-offs, never from a rating scale. That
remains the design; what changed is **which question the trade-offs answer.**

The block shows pairs of real places with the names hidden and records which is preferred.
The original intent was to *estimate* a weight per attribute from those choices by logistic
regression. That is beyond what twenty-five choices can support. A design sweep on the real
data fitted a simulated respondent with three strong, coherent preferences against pure
random answers, at every attribute-pool size from eight to seventeen:

| Attributes | Coherent respondent (median LOO) | Random (95th pct) | Separation |
|---|---|---|---|
| 8 | 0.700 | 0.748 | −0.048 |
| 9 | 0.700 | 0.680 | +0.020 |
| 10 | 0.680 | 0.640 | +0.040 |
| 17 | 0.620 | 0.640 | −0.020 |

Separation is zero everywhere. No choice of attributes rescues it — the shortage is data,
not design, and asking enough questions to fix it would take the block past thirty-five.

So the block now **checks** rather than estimates. The household states its weights
directly, and the same choices test whether those weights predict their behaviour:

```
for each pair:  U(side) = Σ_d  w_d / n_d  ·  desirability(indicator, side)
predicted      = the side with the higher U
agreement      = share of choices predicted correctly
p              = P(X ≥ correct | X ~ Binomial(n, 0.5))
```

This has **no free parameters**, so it is an ordinary binomial test: under the null it is
exactly a coin flip, and twenty-five choices give it real power. Scoring runs through the
household's own elicited curves, so an `ideal_band` indicator is judged against the band
they gave rather than assumed to be more-is-better, and weight is split evenly across the
indicators shown from a domain so a domain gains nothing by appearing more often.

**On the first real respondent it returns 54% of 24 choices, p=0.42** — his almost-flat
allocation does not predict his choices better than a coin. That is a finding about his
weights, not a failure of the test, and it is reported on the page rather than averaged
away. The test cannot say whether his choices are inconsistent or his stated weights are
wrong; that is his to resolve, and deliberately not something this layer settles by fitting
weights to the choices.

*A methodological caution, recorded because it was nearly shipped as a finding:* an earlier
run of this check reported 75% at p=0.011 for the same respondent. `choice_tasks` is seeded,
so regenerating after the question rewrite produces `choice_7` showing a **different pair** —
that run was comparing his answers against questions he never saw. Replayed answers are
only meaningful against the exact question set that produced them.

`fit_choices` is retained and still runs, gated on cross-validated accuracy. When it clears
the gate its weights are blended in and its within-domain weights are used; when it does
not, the within-domain weights come from the household's own band answers rather than from
a rejected fit — the gate used to apply to one output of the fit and not the other.

---

## 5. Knockouts

Deal-breakers are **hard filters**, not heavy weights — "must be within 90 minutes of an
international airport" is a constraint, not a preference. They apply as a boolean mask
after scoring, never before, so the eliminated set stays inspectable.

Every knockout reports **how many places it eliminated** and **the highest-scoring place it
removed**. A filter that alone removes 90% of the universe is a decision the household
should make consciously, and the report forces that.

---

## 6. Two people

Each partner has their own weight vector in `profiles/`. The pipeline scores the universe
**twice**, then reports:

- `score_a`, `score_b` — individual scores
- `score_joint` — geometric mean of the two, so a place one partner hates cannot win
- `disagreement` = `|score_a − score_b|`, plus the domains driving it

Averaging two people into one preference vector destroys exactly the information a couple
needs. A place ranked 4th jointly with high disagreement is a different situation from one
ranked 4th with both partners aligned, and the report distinguishes them.

---

## 7. Sensitivity

Weights are elicited estimates, so ranks are estimates. Each run draws ~1,000 perturbed
weight vectors from a Dirichlet distribution centered on the stated weights, with the
concentration parameter tuned to roughly ±20% relative jitter, and re-scores the universe.

Every place reports `rank_p05`, `rank_median`, `rank_p95`. A place whose 90% band spans
hundreds of positions is labeled unstable. **Reporting a rank without its band is false
precision** (Principle 9) — with ~8,000 candidates and a dozen weights, many adjacent ranks
are indistinguishable.

---

## 8. Explanation

For every place in the shortlist, the report decomposes the score into per-indicator
contributions `wᵢ · ln(dᵢ)` and lists the **five largest contributors** and **three largest
drags**, each with its raw value, national percentile, and source.

The deliverable is not a number. It is an argument the household can check and disagree
with.

---

## 9. Pipeline stages

```
universe  →  ingest  →  features  →  scoring  →  diagnostics  →  report
```

| Stage | Responsibility | Output |
|---|---|---|
| `universe` | Enumerate counties and places from Census geography | `data/processed/universe.parquet` |
| `ingest` | One module per source; fetch, checksum, normalize to long form | `data/interim/<source>.parquet` |
| `features` | Join to universe, apply transforms, compute percentiles | `data/processed/features.parquet` |
| `scoring` | Apply curves, weights, aggregation, knockouts | `data/processed/scores.parquet` |
| `diagnostics` | Hype residual, coverage, sensitivity, political delta | `output/*.md` |
| `report` | Ranked HTML + explanations | `output/report.html` |

Every stage is a pure function of its inputs. Re-running from pinned raw files reproduces
the output exactly — which is what makes Principle 3 checkable rather than aspirational.

**Common long form for all ingest modules:**

```
geo_level | geo_id | indicator_id | value | vintage | source_file
```

One shape for every source means new sources plug in without touching the scoring code.
