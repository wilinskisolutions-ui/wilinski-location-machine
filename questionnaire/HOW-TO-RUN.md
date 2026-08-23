# Running the questionnaire

There are two ways to answer the same 56 questions. Pick one each — you do not need to do
both, and answers do not carry across.

| | Where answers live | Best for |
|---|---|---|
| **Laptop** (`make questionnaire`) | Only on that machine | Keeping everything local |
| **Phone** (published artifact) | On claude.ai | Answering in odd ten-minute gaps |

**One page per person, on purpose.** Whichever route you use, Emil and Winsor answer
separately and neither sees the other's answers until both have finished. That is the whole
reason the ranking can report where you disagree instead of averaging it away.

## On a phone

`make phone-pages` writes one page per person, which then gets published. Each person opens
their own link. Progress saves as you tap, so you can close it and come back.

There is a practice page too — click through as much as you like; nothing on it counts.

At the end, **Save my answers as a file** hands you a JSON file. That is the escape hatch:
if the page cannot save on its own, send that file back and it lands in the pipeline
exactly the same way.

*The trade:* answers taken this way are stored on claude.ai rather than staying on your
laptop. The local route below avoids that entirely.

## On the laptop

It runs on your own laptop. Nothing is uploaded, and the server listens on loopback only,
so it is reachable from that machine and nowhere else.

## First: a practice run

```bash
make questionnaire PERSON=practice
```

Opens `http://localhost:8765`. Click through as much as you like — **a practice session
cannot write a real profile**. That is enforced in code, not by being careful: the person
name is checked against an allowlist, so a typo cannot overwrite real answers.

Stop with `Ctrl-C`.

## The start screen

The first thing you see is the eleven categories the ranking is built from, each with a few
lines explaining exactly what it measures — which sources, which numbers, and what is still
missing. Written so it still makes sense in six months when "urban_form" has stopped meaning
anything on its own.

You can adjust any weight there and **Save weights**, which writes to
`config/domains.yaml`. Two things worth knowing:

- Those numbers are **placeholders**. The questionnaire replaces them by watching which
  trade-offs you actually make, which is more reliable than anyone's self-assessment.
- Tick **lock** on a category to keep your number instead of the elicited one. That is a
  deliberate override of the rule in `GOAL.md` that weights come from trade-offs, so it gets
  recorded in your profile — it will never be mistaken for something you were asked.

The screen is reachable any time from **Categories & weights** at the bottom of any question.

## Then the real thing, one at a time

```bash
make questionnaire PERSON=emil       # Emil answers, then Ctrl-C
make questionnaire PERSON=winsor     # Winsor answers
```

Each writes `profiles/<name>.yaml` on finishing.

**Do not compare answers until you have both finished.** The whole reason you are scored
separately is to see where you genuinely disagree; comparing first turns that into a
measure of who answered first. The tool helps — it never shows one person anything from the
other's session, and keeps results hidden until both are done.

## If you need to start again

```bash
make questionnaire PERSON=emil RESET=1
```

or click **Start over** at the bottom of any question. Both discard that person's answers
only.

## Stopping partway

Progress saves after every question. Rerun the same command and it picks up where you
stopped. About 45 minutes each; splitting it across two sittings is fine.

## What you will be asked

- **The basics** — budget, timeline, whether work ties you anywhere. Facts, not preferences.
- **Compared to Harrisburg** — warmer or colder, bigger or smaller. Anchored to home
  because absolute numbers are hard to answer honestly and comparisons are easy.
- **Which would you rather live in?** — two real places, names hidden, neither better on
  everything. This is where the actual weights come from: what you give up reveals more
  than what you say matters. Names are hidden on purpose, so reputation cannot do the
  choosing for you.
- **100 points** across everything that could matter.
- **Places you know** — rate only those you have really lived in, visited properly, or
  seriously considered. **Skip anything you only know by reputation.** A rating built on
  what you have read imports exactly the bias this project exists to remove.

You will not be asked whether you prefer more crime or dirtier air. Those have one sensible
answer, so asking wastes your time — how much you would trade away for them is measured by
the choices instead.

## Afterwards

```bash
make calibrate
```

Checks whether the elicited weights reproduce your own ratings of places you know. If they
do not, the weights are wrong and no ranking built on them should be trusted yet — better
to find that out now than after a shortlist.
