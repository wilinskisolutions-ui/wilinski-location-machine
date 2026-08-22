# GOAL — Wilinski Location Machine

> **This file is the constitution.** It changes rarely, and only by explicit decision
> logged in `CONTEXT.md`. Every session — human or model — reads this file first.
> If anything in this project contradicts this file, this file wins.

---

## Mission

Determine where the Wilinski household — two partners — should actually live in the United States, by scoring
**every** US county and **every** incorporated place above ~5,000 people against a set of
weighted preferences they define themselves — using versioned public data, identical
treatment for every candidate, and diagnostics that prove the answer is not tracking
internet popularity.

The output is not a list of places that are good. It is a ranked, explained, and
uncertainty-quantified list of places that are good **for these two people**, with the
reasoning legible enough to argue with.

---

## The failure mode this project exists to prevent

Every time this household researched relocation — through search engines, articles, or AI
assistants — the same names came back: **Greenville SC, Raleigh, Charlotte, Florida,
Texas.**

That is not signal. It is the shape of the internet's retrieval bias:

- Recent articles outrank old ones, so wherever is *currently* being written about wins.
- Relocation content is an SEO industry. Realtors, chambers of commerce, and moving
  companies manufacture "best places to live" content for the places that profit from
  inbound moves.
- Migration momentum is self-reinforcing. A place grows, so it gets covered, so more
  people move there, so it gets covered more.

A shortlist produced this way is manufactured by content economics, not by fit. It would
look identical for a retired couple, a young family, and a remote-working introvert —
which is proof it encodes nothing about *them*.

**Roughly 3,100 counties and 19,000 incorporated places exist in the United States.**
Any process that keeps surfacing the same dozen is not searching. This project searches.

---

## The ten principles

These are non-negotiable. Code that violates one of them is a bug, regardless of how good
its output looks.

1. **The universe is fixed before preferences are known.** Candidates are enumerated from
   Census geography, once, before anyone answers a single question. Nothing is ever added
   because it came up in conversation, and nothing is removed because it seems unlikely.

2. **Every place is scored on identical indicators.** No place gets extra dimensions
   because more was known about it. No place is skipped because it seemed too small,
   too obscure, or too improbable.

3. **Every number traces to a source.** Each value carries a source URL, a dataset
   vintage, and a file checksum. A number whose provenance cannot be stated does not
   enter the pipeline.

4. **No LLM supplies a number.** The model writes the code, reads the output, and
   explains the result. It is never itself the data source. If a value came out of a
   language model's memory rather than a downloaded file, it is not evidence.

5. **No web content enters a ranking.** Articles, listicles, forum threads, and search
   results are the contamination this project was built to remove. Qualitative research
   is permitted in Phase 5 only, on an already-fixed shortlist, and is labeled as
   qualitative — it may inform a final human judgment, never a score.

6. **Missing data is flagged, never silently zeroed.** A place that lacks a value must
   not be penalized as though the true value were bad, nor rewarded by exclusion. Every
   place carries a data-coverage figure, and every ranking can be re-run using only
   fully-covered indicators.

7. **Preferences are elicited by forced trade-off, never by "rate 1–5."** Asked to rate
   importance, people rate everything important. Weights come from constrained budget
   allocation, pairwise comparison, and MaxDiff — methods where choosing one thing
   necessarily costs another.

8. **Both partners are scored separately, and disagreement is surfaced.** Two people are
   not one preference vector. Each is scored with their own weights; the joint result
   always shows where the two of them conflict, rather than averaging the conflict away.

9. **Every ranking ships with a sensitivity band.** Weights are estimates, so ranks are
   estimates. If a place's position swings wildly under small changes to the weights,
   the output says so. A rank presented without its stability is a false precision.

10. **Sensitive dimensions default to weight zero.** Political climate, religion,
    diaspora and demographic composition, and social policy are ingested and visible in
    every place profile, but contribute nothing to any score until explicitly enabled.
    They are the household's to turn on, deliberately, never a default assumption.

---

## Definition of done

The project is complete when there exists:

- A **ranked shortlist of ~10 places**, drawn from the full universe, each with a written
  explanation of its five largest strengths and three largest weaknesses.
- A **sensitivity band** on every rank, so coin-flips are labeled as coin-flips.
- A **hype-residual report** demonstrating that fit score is not explained by internet
  popularity, plus a standing "high-fit, low-hype" section.
- A **calibration check** showing the fitted weights reproduce the household's own ratings
  of 20 places they already know.
- A **blind evaluation** in which the household rated name-stripped profiles, with the
  reveal compared against their named preferences.
- A **field-validation plan** — what to verify in person, and what would falsify the
  ranking.

The project is *not* done when the model produces a confident list. It is done when the
household can defend the list, including to themselves in five years.

---

## Anti-goals

This project is explicitly **not**:

- A general-purpose US city database or a product for anyone else.
- A real-estate tool. It does not find houses, price properties, or time markets.
- A substitute for visiting. Its purpose is to decide *where to spend the visits*.
- An optimizer that produces one right answer. It narrows ~8,000 candidates to a
  defensible handful; humans decide among them.
- A place to relitigate settled questions. Decisions live in `CONTEXT.md` with dates and
  rationale so they are made once.

---

## Amendment rule

Principles change only when the household explicitly decides to change them. Any amendment is
recorded in the `CONTEXT.md` decision log with the date, the old rule, the new rule, and
the reason. A principle silently violated in code is a bug to fix, not an amendment.
