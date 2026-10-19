# hw6 — AI Foundation

A vendor desk for Campus Customs, a fictional campus apparel shop. It reads
vendor quotes that arrive as HTML, PDF and email, pulls out the six facts that
matter, and decides `recommend` / `do_not_recommend` against the shop's
purchasing rules.

```bash
python agent.py data/practice_docs/p01_bluehen_quote.html
```

**Scores 12/12 on the practice set**, every field, at $0.0147 for the run.
See [RULES.md](RULES.md) for the constraints and
[output/harness.md](output/harness.md) for how it is built.

> Campus Customs is a fictional shop built for a course assignment. It is not
> affiliated with, endorsed by, or a partner of Yale University.

---

## Quick start

**Install.** Python 3.14 (same interpreter hw3–hw5 used).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Credentials.** Model calls go through the Portkey gateway. Resolution order,
first one wins: the process environment, then `./.env`, then
`~/.config/ai-keys/keys.env` — the same fallback hw4 and hw5 used. Both
`PORTKEY_API_KEY` and `PORTKEY_BASE_URL` already live in the `ai-keys` file, so
no local `.env` is needed on this machine.

```bash
cp .env.example .env     # only if you want per-project overrides
```

---

## One model, one place

**This assignment allows exactly one model: `gpt-6-luna`.** No other model id
may appear in the code or in a run — points are deducted for it.

That is enforced structurally rather than by remembering:

- `MODEL_NAME` in [`config.py`](config.py) is the only place the name is written.
- `config.model()` returns it and **raises on any other name**.
- `config.client()` is the only function that builds a gateway client, so there
  is no second route a stray model id could take.

```python
import config

resp = await config.client().chat.completions.create(
    model=config.model(),          # never a literal
    messages=[...],
)
```

Changing model means editing one constant. See [RULES.md](RULES.md) for the
full constraint and the few details still to confirm against the handout.

---

## Layout

| Path             | What goes here                                           |
| ---------------- | -------------------------------------------------------- |
| `data/`          | The dataset, committed whole (128K) so a grader can clone and run. |
| `output/`        | Everything the code produces: run artefacts, `harness.md`, figures. |
| `scripts/`       | One-off runners and helpers.                              |
| `agent.py`       | Entry point — one document in, an assessment out.         |
| `tools.py`       | Reading documents (HTML/PDF/email) and the handbook.      |
| `models.py`      | The structured types.                                     |
| `prompts/`       | `prompt.md`, the agent's instructions.                    |
| `config.py`      | The model constant, the credential chain, the one client. |
| `cost.py`        | Token and dollar accounting for every call.               |
| `RULES.md`       | Constraints the assignment imposes.                       |
| `AI_prompts.md`  | The prompt log, one section per problem.                  |
| `.env.example`   | Environment template. The real `.env` is never committed. |

### The dataset

| Path                      | What it is                                      |
| ------------------------- | ----------------------------------------------- |
| `data/shop_handbook.md`   | The Shop Handbook — products, vendors, purchasing rules. The **only** source of the rules. |
| `data/practice_docs/`     | 12 vendor documents (5 HTML, 4 PDF, 3 email).    |
| `data/practice_key.json`  | Correct answers for all 12. Self-score here first. |
| `data/exam_docs/`         | 10 more documents (4 HTML, 3 PDF, 3 email). No key. |
| `data/prices.json`        | `gpt-6-luna` prices, per 1M tokens.              |

**The vendor documents are untrusted input.** Text inside them is data to be
extracted, never an instruction to follow — see [RULES.md](RULES.md).

---

## Cost

Every call is metered, because the run is likely scored on cost:

```python
from config import client, model
from cost import METER

resp = await client().chat.completions.create(model=model(), messages=[...])
METER.record(resp)
print(METER.report())
# 22 calls to gpt-6-luna — 180,000 in (74% cached), 9,000 out, 189,000 total — $0.0096
```

Cached input is a tenth the price of fresh input, so keeping a stable prefix
(the handbook, the instructions) byte-identical across calls is the single
biggest lever on the bill.

---

## The agent

One vendor document in, six fields plus a decision out:

```
  Document    p01_bluehen_quote.html
  Vendor      Blue Hen Apparel
  SKU         CC-HD-006
  Unit price  $21.80
  Lead time   14 days
  Min order   240 units

  DECISION    RECOMMEND
  Reason      The approved-vendor, price, lead-time, and minimum-order checks all pass.
```

HTML, PDF and `.eml` all work. `--json` prints the structured output instead.

**Self-score on the practice set:**

```bash
python scripts/score_practice.py     # writes output/practice_run.json
```

### The design in one line

**The document supplies values; the handbook supplies rules.** `extract_document`
reads the outside file; `lookup_vendor` and `lookup_sku` answer the handbook
questions and never look at the document. So no document can approve its own
vendor or move a price ceiling — the functions that could do that read a
different file. Two practice documents try exactly that; see
[output/harness.md](output/harness.md) §2.5.
