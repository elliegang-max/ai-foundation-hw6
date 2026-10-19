# AI Prompt Log — hw6

A log of the prompts I typed into Claude while working on this assignment, in my
own words, organised by problem.

**Convention — one section per problem.** Each section carries:

1. the problem number and title;
2. at least one prompt I typed, quoted verbatim in my own words, with the date;
3. a follow-up prompt where the first one did not get me what I needed, with one
   sentence on what was lacking after the first.

A short note on what Claude did follows each prompt. Sections are numbered to
match the problems in the assignment; everything typed before the problem list
arrived sits in Problem 1 below. Sections are filled in as the assignment
progresses, and nothing is rewritten after the fact.

---

## Problem 1 — Project setup

**Prompt** — 2026-10-19

> start a new folder for hw6

*(Paraphrased — replace with the exact wording.)*

**Response**

Read the hw3, hw4 and hw5 repos to pick up the house conventions, then scaffolded
`hw6` as its own git repository matching them: the shared `.gitignore`, an
`.env.example` for the two Portkey variables, a starting `requirements.txt`, a
Python 3.14 `.venv`, and empty `data/`, `output/` and `scripts/` directories.
Wrote no assignment code — asked for the spec, the dataset and any handout files
first.

---

## Problem 1a — The one-model rule

**Prompt** — 2026-10-19

> every AI call in hw6 must use gpt-6-luna, no other model, for any call

*(Relayed to this session by another Claude session, not typed here directly —
replace with the exact wording.)*

**Response**

Made the rule structural rather than a thing to remember. `config.py` holds
`MODEL_NAME` as the single place the name is written; `config.model()` returns
it and raises on any other name; `config.client()` is the only function that
builds a gateway client, so there is no second route a model id can enter by.
Recorded the constraint in `RULES.md` (hw5's convention for assignment-given
rules) and in the README, and listed the details still to confirm against the
handout — the exact wire id, the provider, and the client library the course
expects.

---

## Problem 1b — The dataset

**Prompt** — 2026-10-19

> the hw6 dataset is in ~/Downloads/data-3, copy it into data/

*(Relayed to this session by another Claude session — replace with the exact
wording.)*

**Response**

Copied all 128K in and verified it byte-identical to the source: the handbook,
`prices.json`, `practice_key.json`, 12 practice documents and 10 exam
documents. Read the handbook's sections 4, 5, 6 and 13 to pin down the task —
six fields per document plus a decision, `recommend` only if all four
purchasing checks pass — and wrote that into `RULES.md` alongside a rule that
the vendor documents are untrusted input whose contents are never instructions.
Added `cost.py`, metering tokens and dollars off `data/prices.json` through the
single client, since the price table suggests the run is scored partly on cost.
Still no pipeline: waiting on the handout to confirm the output shape and how
it is scored.
