# Wilinski Location Machine

Deciding where to live in the US by weighing evidence over **every** county and
place in the country over 5,000 people — rather than by reading whatever the internet is
currently writing about.

## Why

Researching relocation kept returning the same names: Greenville SC, Raleigh, Charlotte,
Florida, Texas. That is the shape of the internet's retrieval bias, not evidence about
fit — recent articles outrank old ones, relocation content is an SEO industry funded by
the places that profit from inbound moves, and migration coverage is self-reinforcing.
A shortlist built that way looks the same for a retired couple, a young family, and a
remote-working introvert, which is proof it encodes nothing about anyone in particular.

About 3,100 counties and 19,000 incorporated places exist here, plus thousands of
unincorporated communities. Any process that keeps
returning the same dozen is not searching.

## How

Score **~3,100 counties and ~5,000 places** on identical indicators drawn from versioned
public datasets — Census, BLS, BEA, NOAA, FEMA, EPA, and others — weighted by preferences
elicited through forced trade-offs, with diagnostics that check the output is not tracking
popularity.

Read **[`GOAL.md`](GOAL.md)** first — it is the constitution, and it wins over anything
that contradicts it. Then **[`CONTEXT.md`](CONTEXT.md)** for current state.

## Documents

| File | What it is |
|---|---|
| [`GOAL.md`](GOAL.md) | The constitution: mission, ten principles, definition of done. Changes rarely. |
| [`CONTEXT.md`](CONTEXT.md) | Living state: decisions, household facts, open questions, next actions. Updated every session. |
| [`docs/anti-bias.md`](docs/anti-bias.md) | The five biases and the mechanism defeating each. The intellectual core. |
| [`docs/methodology.md`](docs/methodology.md) | How a place gets a score — geography, curves, aggregation, sensitivity. |
| [`docs/data-sources.md`](docs/data-sources.md) | Source catalog with URLs, vintages, licenses, and caveats. |
| [`docs/network-allowlist.md`](docs/network-allowlist.md) | Hosts to allow so ingest can run in-session. |
| [`questionnaire/README.md`](questionnaire/README.md) | Question design and weight elicitation. |

## Usage

```bash
make validate   # check config registries against the GOAL.md principles
make test       # run the test suite (no network needed)
make demo       # run the whole chain on synthetic fixtures
make data       # download every source (~250MB) into data/raw with checksums
make universe   # build the candidate universe
make features   # ingest everything and compute percentiles
make coverage   # report what has data and what does not, with reasons
make questionnaire PERSON=practice   # try the questionnaire safely
make calibrate  # check elicited weights against places they already know
make score      # rank counties, then towns inside the winners, with rank bands
make diagnostics # hype residual, blind export, political with/without
make report     # the readable ranking - refuses any rank without its band
make audit      # check the system against the ten principles in GOAL.md
```

`validate` needs PyYAML alone. The pipeline stages need `pip install -e ".[pipeline]"`.

`make demo` is the quickest way to see what exists: it builds a universe, ingests three
sources, computes percentiles and coverage, then shows scoring **refusing** to run on
synthetic input.

## Status

**Phase 4 — Engine: built.** A real universe of **9,885 candidates** (3,144 counties, 6,741
places) with **46 of 65 indicators populated** from live federal data. The chain runs end to
end: scoring, rank bands, the anti-bias diagnostics, and a readable report. `make audit`
reports **10 of 10 principles passing**. Every remaining data gap has a named reason in
`output/coverage.md`.

**What is still missing is the household, not the machinery.** Every weight in the system is
a placeholder nobody chose, and the pipeline says so at every stage that uses one.

| Phase | Deliverable | Status |
|---|---|---|
| 0 — Charter | Principles, methodology, registries, scaffolding | done |
| 1 — Universe | Fixed candidate set, pipeline proven on 3-4 sources | done |
| 2 — Ingest | 46 of 65 indicators on real data, coverage report | done |
| 3 — Questionnaire | Local instrument, elicitation, calibration | **built, awaiting answers** |
| 4 — Engine | Scoring, rank bands, anti-bias diagnostics, report | built, running on placeholders |
| 5 — Shortlist | Top ~25 deep dive, blind evaluation | |
| 6 — Field | Visit plan and final decision | |

Phase 3 is blocked on the household, not on data: the calibration set of 15-20 known
places rated 1-10. Without it there is no way to check that fitted weights reproduce
judgements they already hold.
