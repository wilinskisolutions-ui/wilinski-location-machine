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
make test       # run the test suite (90 tests, no network needed)
make demo       # run the whole chain on synthetic fixtures
make data       # download the real sources (needs the egress allowlist)
```

`validate` needs PyYAML alone. The pipeline stages need `pip install -e ".[pipeline]"`.

`make demo` is the quickest way to see what exists: it builds a universe, ingests three
sources, computes percentiles and coverage, then shows scoring **refusing** to run on
synthetic input.

## Status

**Phase 1 — Universe: built.** The universe builder, provenance layer, three ingest
modules, and the features stage all run end to end. They run on *synthetic fixtures* only,
because the data hosts are still blocked — and the synthetic guardrail makes it impossible
for those fixtures to reach a real result.

| Phase | Deliverable | Status |
|---|---|---|
| 0 — Charter | Principles, methodology, registries, scaffolding | done |
| 1 — Universe | Fixed candidate set, pipeline proven on 3-4 sources | **built, awaiting real data** |
| 2 — Ingest | 40-60 indicators, coverage report | |
| 3 — Questionnaire | Question bank, elicited weights, calibration set | |
| 4 — Engine | Scoring, sensitivity, anti-bias diagnostics, report | |
| 5 — Shortlist | Top ~25 deep dive, blind evaluation | |
| 6 — Field | Visit plan and final decision | |

Phase 2 is blocked on the network allowlist in `docs/network-allowlist.md` — the pipeline
is written and tested, it just has no real data to run on yet.
