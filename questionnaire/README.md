# Questionnaire — structure

Built in **Phase 3**. This file fixes the design so it is not re-argued later.

## Every question maps to something

```yaml
- id: q_climate_summer_heat
  domain: climate_environment        # must exist in config/domains.yaml
  text: "Which summer would you rather live through, every year?"
  response_type: forced_choice       # forced_choice | budget_alloc | maxdiff | numeric | boolean | free_text
  maps_to:
    kind: indicator                  # indicator | knockout | weight_domain | qualitative_note
    target: climate_temp_july_mean
    sets: curve_params               # what the answer determines
```

**A question that maps to nothing gets cut.** This mapping is what makes the instrument a
machine rather than a quiz — every answer must move a curve, a weight, or a filter, or be
recorded as an explicit qualitative note.

## Weights come from forced trade-offs

Never "rate importance 1-5" — asked that way, people rate everything important and the
weights carry no information (GOAL.md Principle 7). Instead:

| Method | Use |
|---|---|
| **Budget allocation** | 100 points across the 10 scoring domains. Spending on one costs another. |
| **Pairwise comparison** | Within a domain: "cheaper housing or shorter commute?" Repeated to derive a consistent ordering. |
| **MaxDiff** | Sets of 4-5 attributes, pick best and worst. Separates near-ties that budget allocation cannot. |

Both partners answer **independently**, before seeing each other's answers. Comparing them
is a deliverable, not a side effect (Principle 8).

## Delivery

Roughly 10 sessions of 15-20 questions in `sessions/`, not one 200-question slog — fatigue
degrades late answers, and the ordering effects are worse than the missing data.

Sequence: constraints and knockouts first (they shrink the universe cheaply), then domain
weights, then within-domain curves, then the calibration set last, when both partners have
their preferences fresh in mind.

## The calibration set

`profiles/calibration.yaml` — 20 places the household genuinely knows: current residence,
previous homes, places visited, and places actively rejected. Each rated 1-10.

The fitted weights must approximately reproduce these ratings. **If the model cannot
recover judgments the household already holds, the weights are wrong and no ranking built
on them is trustworthy.** Skipping this step is the most common way projects like this
fail: they produce confident output that was never checked against anything.
