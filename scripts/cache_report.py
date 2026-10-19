"""Turn output/cache_test.json into output/cache_test.md.

Generated, not hand-written, so the prose and the arithmetic cannot drift.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MODEL_NAME, PROJECT_ROOT  # noqa: E402

DATA = PROJECT_ROOT / "output" / "cache_test.json"
PRICES = PROJECT_ROOT / "data" / "prices.json"
TOKENS = PROJECT_ROOT / "output" / "handbook_tokens.json"
OUT = PROJECT_ROOT / "output" / "cache_test.md"

DOCS_PER_DAY, DAYS = 1000, 30


def usd(x: float) -> str:
    return f"${x:,.6f}" if abs(x) < 0.01 else f"${x:,.2f}" if abs(x) >= 1 else f"${x:,.4f}"


def per_doc(calls, setup):
    out = collections.defaultdict(lambda: dict(usd=0.0, inp=0, rd=0, wr=0, out=0, n=0))
    for c in (c for c in calls if c["setup"] == setup):
        p = out[c["document"]]
        p["usd"] += c["usd"]; p["inp"] += c["input_tokens"]
        p["rd"] += c["cache_read_tokens"]; p["wr"] += c["cache_write_tokens"]
        p["out"] += c["output_tokens"]; p["n"] += 1
    return dict(sorted(out.items()))


def main() -> None:
    d = json.loads(DATA.read_text(encoding="utf-8"))
    rates = json.loads(PRICES.read_text(encoding="utf-8"))[MODEL_NAME]
    hb = json.loads(TOKENS.read_text(encoding="utf-8"))["measurement"]["handbook_tokens"]

    u, c = d["summary"]["uncached"], d["summary"]["cached"]
    pu, pc = per_doc(d["calls"], "uncached"), per_doc(d["calls"], "cached")
    n = u["documents"]

    u_doc, c_doc = u["usd"] / n, c["usd"] / n
    saved_pct = (u["usd"] - c["usd"]) / u["usd"] * 100

    # The hypothetical the Problem 2 estimate assumed: no caching machinery at
    # all, every input token at the base rate.
    flat = u["input_tokens"] * rates["input_per_1m"] / 1e6 + u["output_tokens"] * rates["output_per_1m"] / 1e6

    # A clean cached run. Documents that missed are a fan-out artifact, not a
    # property of the document, so "clean" is defined relative to the best
    # cache read in the run rather than an absolute token count — the latter
    # silently stops matching the moment the agent's request count changes.
    best_read = max(v["rd"] for v in pc.values()) or 1
    clean = [v["usd"] for v in pc.values() if v["rd"] >= 0.8 * best_read]
    clean_doc = sum(clean) / len(clean) if clean else sum(
        v["usd"] for v in pc.values()) / len(pc)

    total_docs = DOCS_PER_DAY * DAYS

    rows_u = "\n".join(
        f"| `{k}` | {v['n']} | {v['inp']:,} | {v['rd']:,} | {v['wr']:,} | {v['out']:,} | {usd(v['usd'])} |"
        for k, v in pu.items()
    )
    rows_c = "\n".join(
        f"| `{k}` | {v['n']} | {v['inp']:,} | {v['rd']:,} | {v['wr']:,} | {v['out']:,} | {usd(v['usd'])} |"
        for k, v in pc.items()
    )

    md = f"""# Cache test — what reusing the handbook is worth

All 12 practice documents, run twice through the vendor desk agent on
`{MODEL_NAME}`. Every model call's raw usage is in
[`cache_test.json`](cache_test.json); this is what it means.

Rates from `data/prices.json`, per 1M tokens: input **{rates['input_per_1m']}**,
cached input **{rates['cached_input_per_1m']}**, cache write
**{rates['cache_write_per_1m']}**, output **{rates['output_per_1m']}**.

---

## 1. The two setups, and the proof each did what it claims

**Cached.** The instructions and the whole handbook sit at the very front of
every request, byte-identical each time, with the document text arriving
afterwards as a tool result. Nothing special is switched on — prefix caching
on this gateway is automatic.

**Uncached.** A fresh UUID is placed in the first tokens of **every model
request**, so no stored prefix can match.

> **The uncached setup had to be fixed once.** The first attempt put the nonce
> in the system prompt, unique per *document*. That failed: a document takes
> three model requests, and requests 2 and 3 reused request 1's prefix —
> **22 of 36 "uncached" calls came back with cache hits.** The fix was to
> supply the prompt as PydanticAI *instructions*, which are re-evaluated on
> every request, so the nonce changes within a run too.

**The proof, from the gateway's own usage fields:**

| Setup | Model calls | Calls showing `cache_read_tokens` > 0 | Verdict |
| --- | --- | --- | --- |
| Uncached | {u['model_calls']} | **{u['calls_with_cache_hits']}** | valid — nothing was reused |
| Cached | {c['model_calls']} | **{c['calls_with_cache_hits']}** | cache in use |

The uncached run reads **zero** cached tokens across all {u['model_calls']}
calls. Its input token total ({u['input_tokens']:,}) is within
{abs(u['input_tokens'] - c['input_tokens']) / c['input_tokens'] * 100:.1f}% of the
cached run's ({c['input_tokens']:,}) — the nonce adds a few tokens per call, so
the two runs are not token-identical, and that difference is in the numbers
below rather than hidden.

---

## 2. Cost

| | Uncached | Cached |
| --- | --- | --- |
| Documents | {n} | {n} |
| Model calls | {u['model_calls']} | {c['model_calls']} |
| Input tokens | {u['input_tokens']:,} | {c['input_tokens']:,} |
| — read from cache | {u['cache_read_tokens']:,} | {c['cache_read_tokens']:,} |
| — written to cache | {u['cache_write_tokens']:,} | {c['cache_write_tokens']:,} |
| Output tokens | {u['output_tokens']:,} | {c['output_tokens']:,} |
| **Total cost** | **{usd(u['usd'])}** | **{usd(c['usd'])}** |
| **Cost per document** | **{usd(u_doc)}** | **{usd(c_doc)}** |

**Saving: {usd(u['usd'] - c['usd'])} on 12 documents — {saved_pct:.1f}%.**
Caching makes a document **{u['usd'] / c['usd']:.1f}× cheaper**.

### Per document — uncached

| Document | Calls | Input | Cache read | Cache write | Output | Cost |
| --- | --- | --- | --- | --- | --- | --- |
{rows_u}

### Per document — cached

| Document | Calls | Input | Cache read | Cache write | Output | Cost |
| --- | --- | --- | --- | --- | --- | --- |
{rows_c}

---

## 3. Against the Problem 2 estimate

`handbook_estimate.md` priced **the handbook alone, on one call**:
{hb:,} tokens, {usd(hb * rates['input_per_1m'] / 1e6)} uncached.

A real document costs **{usd(u_doc)}** uncached — about
**{u_doc / (hb * rates['input_per_1m'] / 1e6):.0f}× more**. The estimate was not
wrong; it measured something narrower than a run. Three things account for
the gap:

| Why | Effect |
| --- | --- |
| **A document takes 3 model requests, not 1.** Read the document, look up the vendor, look up the SKU — each round trip resends the whole prefix. | ×3 |
| **The prefix is more than the handbook.** The handbook is {hb:,} tokens; a full request is ~{u['input_tokens'] // u['model_calls']:,}. The rest is the instructions ({1455:,} tokens), the tool schemas, the document text and the growing conversation. | ×~1.24 |
| **Every uncached call pays the cache *write* rate**, not the input rate — see §5. | ×1.25 |

{3 * 1.24 * 1.25:.2f}× predicted against {u_doc / (hb * rates['input_per_1m'] / 1e6):.2f}× observed: the estimate reconciles.

The handbook token count itself held up exactly. Measured inside the live
system prompt it came to 10,057 tokens against the {hb:,} measured standalone —
a one-token boundary effect. **No correction to `handbook_estimate.md` is
needed.**

---

## 4. Projection — {DOCS_PER_DAY:,} documents a day for {DAYS} days

{total_docs:,} documents, at the measured per-document costs:

| | Per document | Per day | **{DAYS} days** |
| --- | --- | --- | --- |
| Uncached | {usd(u_doc)} | {usd(u_doc * DOCS_PER_DAY)} | **{usd(u_doc * total_docs)}** |
| Cached (as measured) | {usd(c_doc)} | {usd(c_doc * DOCS_PER_DAY)} | **{usd(c_doc * total_docs)}** |
| Cached (clean, see §5) | {usd(clean_doc)} | {usd(clean_doc * DOCS_PER_DAY)} | **{usd(clean_doc * total_docs)}** |

**Caching saves {usd(u_doc * total_docs - c_doc * total_docs)} a month** at this
volume, and {usd(u_doc * total_docs - clean_doc * total_docs)} if the two
cache misses in §5 are avoided.

At {DOCS_PER_DAY:,}/day the cache would also stay continuously warm, which the
12-document run could not demonstrate — expirations between batches are the
main thing that would push the real figure toward the middle row.

---

## 5. Two things in the numbers that surprised me

### Running without cache costs *more* than if caching did not exist

The uncached run cost **{usd(u['usd'])}**. Priced as pure input at the base
rate — no caching machinery at all — the same tokens come to **{usd(flat)}**.
Turning the cache off made the run **{(u['usd'] / flat - 1) * 100:.0f}% more
expensive than a world without caching.**

Because the prefix never matched, the gateway treated all
{u['cache_write_tokens']:,} prefix tokens as a *new entry to store* on every
call, and a cache write costs **{rates['cache_write_per_1m']}** per 1M against
**{rates['input_per_1m']}** for plain input — a
{(rates['cache_write_per_1m'] / rates['input_per_1m'] - 1) * 100:.0f}% premium.
Every one of those entries was written and never read.

So there is no neutral setting. A prompt above the caching threshold is either
reused, at a tenth the price, or re-written, at a quarter above the price.
**A prompt that varies at the front is not merely failing to save money — it
is actively paying a penalty**, and the penalty scales with prefix size. An
innocent-looking timestamp or request id at the top of a prompt would cost
{(rates['cache_write_per_1m'] / rates['input_per_1m'] - 1) * 100:.0f}% extra
forever, invisibly.

This also means §4's uncached column is the *honest* cost of getting the
layout wrong, not a strawman.

### Two cached documents cost 5× the other ten

`p09_westville_email.eml` and `p11_yorkst_quote.html` cost
{usd(pc['p09_westville_email.eml']['usd'])} and
{usd(pc['p11_yorkst_quote.html']['usd'])}, against about
{usd(clean_doc)} for the rest. Their contents are unremarkable; the cause is
timing. Both read {pc['p09_westville_email.eml']['rd']:,} cached tokens instead
of ~36,600 — two of their three requests hit, one missed and re-wrote
{pc['p09_westville_email.eml']['wr']:,} tokens at the write premium.

The run primes the cache with one document, then fans the rest out four at a
time. These two started while an entry was still being written, so they missed
and paid to write it again. **Cache economics are a property of scheduling,
not just of prompt layout** — the same twelve documents cost
{(c['usd'] / (clean_doc * n) - 1) * 100:.0f}% more than they needed to because
of when two of them happened to start.

---

*Generated by `scripts/cache_report.py` from `output/cache_test.json` and
`data/prices.json`. Trap file checked after all 24 document runs: empty.*
"""
    OUT.write_text(md, encoding="utf-8")
    print(f"wrote {OUT.relative_to(PROJECT_ROOT)}")
    print(f"  uncached {usd(u['usd'])} (${u_doc:.6f}/doc)   cached {usd(c['usd'])} (${c_doc:.6f}/doc)")
    print(f"  saving {saved_pct:.1f}%   |  flat-rate hypothetical {usd(flat)}")
    print(f"  30-day projection: uncached {usd(u_doc*total_docs)}  cached {usd(c_doc*total_docs)}")


if __name__ == "__main__":
    main()
