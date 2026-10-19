# AI Prompt Log — hw6

The log of what I communicated to Claude while working on this assignment.

**Convention — one section per problem.** Each section carries:

1. the problem number and title;
2. at least one prompt I typed, in my own words;
3. a follow-up prompt where the first one did not get me what I needed, with
   one sentence on what was lacking after the first.

Prompts are quoted verbatim. Where no follow-up was needed, that bullet is
absent rather than filled in. A short note on what Claude did follows each
prompt. Sections are numbered to match the problems in the assignment;
everything typed before the handout arrived sits in **Setup** below. The log is
appended to as the assignment progresses and is not rewritten after the fact.

> **A note on provenance.** Part of this assignment was set up across two
> Claude sessions, and these prompts were typed to the other one, then carried
> across verbatim. They are my words, not a summary of them. Where a prompt is
> incomplete, it is reproduced as it was sent.

---

## Setup — project, model rule, and data

Everything here predates the handout, so it is not yet attached to a numbered
problem. Per-problem sections begin once the problems are known.

### Prompt 1 — 2026-10-19

> now i need to start a new folder to work on hw6

**What Claude did.** Read the hw3, hw4 and hw5 repos for the house conventions
and scaffolded `hw6` as its own git repository matching them: the shared
`.gitignore`, an `.env.example` for the two Portkey variables, a starting
`requirements.txt`, a Python 3.14 venv, and `data/`, `output/` and `scripts/`.
No assignment code — asked for the spec first.

### Prompt 2 — 2026-10-19

> for this assignment only use gpt-6-luna for every AI call!!

**What Claude did.** Made the rule structural rather than something to
remember. `config.py` holds `MODEL_NAME` as the single place the name is
written, `config.model()` raises on any other name, and `config.client()` is
the only route to the gateway — so there is no second place a model id can
enter the program. Recorded in `RULES.md` and the README.

### Prompt 3 — 2026-10-19

> @/Users/shutong/Downloads/data-3/ here's our data. make sure you have

followed by a pasted list:

> `data/shop_handbook.md`: the Campus Customs Shop Handbook (products, vendors,
> purchasing rules) / `data/prices.json`: gpt-6-luna prices /
> `data/practice_docs/`: 12 vendor documents (HTML, PDF, and email) /
> `data/practice_key.json`: the correct answers for the practice documents /
> `data/exam_docs/`: 10 more vendor documents with no answer key

*(The sentence ends mid-thought at "make sure you have" — reproduced as sent.)*

**What Claude did.** Copied all 128K into `data/` and verified it
byte-identical to the source: the handbook, `prices.json`, `practice_key.json`,
12 practice documents and 10 exam documents. Read the handbook's sections 4, 5,
6 and 13 to pin down the task — six fields per document plus a decision,
`recommend` only if all four purchasing checks pass — and wrote that into
`RULES.md`, together with a rule that the vendor documents are untrusted input
whose contents are never instructions. Added `cost.py` to meter tokens and
dollars off `data/prices.json`, since the price table suggests the run is
scored partly on cost.

### Prompt 4 — 2026-10-19

> Create AI_prompts.md at the start of the assignment and keep it updated as
> you work. This file is the log of i communicated to you. Make one section for
> each problem and each section should include

followed by a pasted list:

> The problem number and title
> * At least one prompt you typed, in your own words as much as possible
> * One follow-up prompt if you needed it (and one sentence on what was lacking
>   after the first)

**What Claude did.** Rewrote this file to that shape and replaced the
paraphrased placeholders it had been holding with the prompts above, quoted
verbatim.

---

## Unnumbered — the handbook's token count and cost

*(Awaiting its problem number and title from the handout.)*

### Prompt 5 — 2026-10-19

> Unzip data.zip. Look through data/shop_handbook.md. This is the Campus
> Customs Shop Handbook, Also look at data/prices.json, the gpt-6-luna price
> list. Find out how many tokens the handbook is. In output/handbook_estimate.md
> write: The token count and how you got it

followed by a pasted bullet:

> * What the handbook alone costs in dollars on one call, and on 1,000 calls,
>   with cached tokens and without them. Show your math.

**What Claude did.** Did not unzip anything: `~/Downloads/data.zip` is the hw3
dataset (216 files, 16MB of product photos and ad videos), not hw6's, and
hw6's data was already in `data/` and verified. Flagged it as an instruction
that looks carried over from an earlier assignment. Measured the handbook's
token count against the gateway rather than estimating it, and wrote
`output/handbook_estimate.md` with the count, the method, and the four cost
cases.
