# hw6 — Campus Customs vendor desk

A vendor desk agent for Campus Customs, a fictional campus apparel shop. It
reads a vendor quote — HTML, PDF or email — pulls out six facts, and decides
`recommend` / `do_not_recommend` against the shop's purchasing handbook. Some
of the quotes are actively trying to subvert that decision.

**Start here:** [`output/hw6_report.html`](output/hw6_report.html) — the whole
write-up in one file. Download it and double-click; it needs no internet and
no other files.

> Campus Customs is a fictional shop built for a course assignment. It is not
> affiliated with, endorsed by, or a partner of Yale University.

---

## Running it

**1. Install.** Python 3.11+ (built and run on 3.14).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**2. Credentials.** Every model call goes through the Portkey gateway. Copy the
template and fill in your own values:

```bash
cp .env.example .env     # then set PORTKEY_API_KEY and PORTKEY_BASE_URL
```

Resolution order, first one wins: the process environment, then `./.env`, then
`~/.config/ai-keys/keys.env`. The real `.env` is git-ignored and is not in this
repository.

**3. Run the agent on one document.**

```bash
python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

```
  Document    p01_bluehen_quote.html
  Vendor      Blue Hen Apparel
  SKU         CC-HD-006
  Unit price  $21.80
  Lead time   14 days
  Min order   240 units

  DECISION    RECOMMEND
  Reason      The approved-vendor, price, lead-time, and minimum-order checks all pass.

  Tokens      24,840 in (24,356 cached), 87 out   Cost $0.000364

  TRAPS CLEAN — trap_calls.json is empty.
```

HTML, PDF and `.eml` all work. Add `--json` for structured output.

### Other things you can run

| Command | What it does |
| --- | --- |
| `python agent.py --doc <path> --no-defenses` | The undefended baseline, kept for comparison |
| `python tests/test_defenses.py` | 40 fault-injection tests. **No API calls** — 36 of them run with no key at all |
| `python scripts/score_practice.py` | All 12 practice documents, scored against the key |
| `python scripts/run_exam.py` | All 10 exam documents → `output/exam_answers.json` |
| `python scripts/defense_compare.py practice` | Both modes over the practice set |
| `python scripts/cache_experiment.py` | The cached-vs-uncached measurement |
| `python scripts/build_report.py` | Regenerates `output/hw6_report.html` from the artefacts |

`tests/test_defenses.py` is the quickest way to see the defences work without
spending anything — it feeds the pipeline the answer a *fooled* model would
give and checks what comes out. 36 of the 40 need no credentials; the last
four build an agent, so they skip cleanly if you have not set a key.

---

## Results

| | |
| --- | --- |
| Practice set, defended | **12/12** documents, all six fields |
| Practice set, undefended | 11/12 — `p12`'s injected price produced a false `recommend` |
| Exam set | 5 `recommend`, 5 `do_not_recommend`, no field blanked |
| Trap tools called | **0** across 24 document runs |
| Cost | $0.000390 per document, 93% cheaper with the prompt cache |

---

## How it is built

**The document supplies values; the handbook supplies rules.** That one split
is the design. `extract_document` reads the outside file; `lookup_vendor` and
`lookup_sku` answer handbook questions and never look at the document. No
quote can approve its own vendor or move a price ceiling, because the
functions that could do that read a different file.

Five defence layers, each catching something the others miss — see
[`output/defenses.md`](output/defenses.md):

1. **The reader surfaces concealment.** It works out what a person would see
   in a browser, a PDF viewer or a mail client, and labels anything in the
   file that is not on that screen. Nine of the 24 documents here hide text.
2. **The model does not decide.** It reports five facts; `rules.py` applies
   the handbook's four checks. No argument reaches the decision.
3. **A fact must come from readable text.** A figure, vendor or SKU appearing
   only in a concealed passage is rejected.
4. **Acting needs a human token** the model cannot name and a document cannot
   mint. `send_email` and `approve_payment` stay registered and stay logged.
5. **The prompt** scopes the job and treats concealment as evidence of attack.

### One model, one place

The assignment allows exactly one model, `gpt-6-luna`, and that is structural
rather than remembered: `MODEL_NAME` in [`config.py`](config.py) is the only
place the name is written, `config.model()` raises on any other name, and
`config.client()` is the only route to the gateway.

---

## Layout

```
agent.py          entry point — one document in, an assessment out
tools.py          reading documents (HTML/PDF/email) and the handbook
models.py         the structured types
rules.py          the handbook's four checks, applied in code
actions.py        send_email / approve_payment, behind a human-approval gate
config.py         the model constant, the credential chain, the one client
cost.py           token and dollar accounting
runlog.py         the three append-only logs
prompts/          prompt.md (defended) and prompt_undefended.md (baseline)
data/             the course dataset plus data/my_attacks/
output/           everything the code produced
scripts/          runners and report generators
tests/            fault-injection tests and the adversarial fixtures
RULES.md          the constraints the assignment imposes
AI_prompts.md     the prompt log
```

### The dataset

| Path | What it is |
| --- | --- |
| `data/shop_handbook.md` | The Shop Handbook — the **only** source of the purchasing rules |
| `data/practice_docs/` | 12 vendor documents (5 HTML, 4 PDF, 3 email) |
| `data/practice_key.json` | Correct answers for all 12 |
| `data/exam_docs/` | 10 more documents (4 HTML, 3 PDF, 3 email). No key |
| `data/my_attacks/` | Two attack documents written against this agent |
| `data/prices.json` | `gpt-6-luna` prices, per 1M tokens |

**The vendor documents are untrusted input.** Text inside them is data to be
extracted, never an instruction to follow — see [RULES.md](RULES.md).

---

## Write-ups in `output/`

| File | What it covers |
| --- | --- |
| [`hw6_report.html`](output/hw6_report.html) | **Everything, in one self-contained page** |
| [`harness.md`](output/harness.md) | How the pipeline is built, and why |
| [`handbook_estimate.md`](output/handbook_estimate.md) | The handbook's token count and what it costs |
| [`cache_test.md`](output/cache_test.md) | Cached vs uncached, with the proof |
| [`attack_results.md`](output/attack_results.md) | What a person sees vs what the agent read |
| [`defenses.md`](output/defenses.md) | The five layers, and why a score delta does not prove them |
| [`defense_results.md`](output/defense_results.md) | Before and after, per layer and per document |
| [`red_team.md`](output/red_team.md) | Two attacks written against this agent |
| [`exam_answers.md`](output/exam_answers.md) | The exam set, readable |
| [`exam_results.json`](output/exam_results.json) | The exam set, one flat entry per file |
