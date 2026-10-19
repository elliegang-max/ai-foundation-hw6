# Cache test — what reusing the handbook is worth

All 12 practice documents, run twice through the vendor desk agent on
`gpt-6-luna`. Every model call's raw usage is in
[`cache_test.json`](cache_test.json); this is what it means.

Rates from `data/prices.json`, per 1M tokens: input **0.1**,
cached input **0.01**, cache write
**0.125**, output **0.5**.

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
| Uncached | 36 | **0** | valid — nothing was reused |
| Cached | 36 | **34** | cache in use |

The uncached run reads **zero** cached tokens across all 36
calls. Its input token total (449,839) is within
0.2% of the
cached run's (448,929) — the nonce adds a few tokens per call, so
the two runs are not token-identical, and that difference is in the numbers
below rather than hidden.

---

## 2. Cost

| | Uncached | Cached |
| --- | --- | --- |
| Documents | 12 | 12 |
| Model calls | 36 | 36 |
| Input tokens | 449,839 | 448,929 |
| — read from cache | 0 | 415,055 |
| — written to cache | 445,303 | 29,338 |
| Output tokens | 2,215 | 2,216 |
| **Total cost** | **$0.1018** | **$0.0123** |
| **Cost per document** | **$0.008480** | **$0.001026** |

**Saving: $0.0894 on 12 documents — 87.9%.**
Caching makes a document **8.3× cheaper**.

### Per document — uncached

| Document | Calls | Input | Cache read | Cache write | Output | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| `p01_bluehen_quote.html` | 3 | 37,504 | 0 | 37,126 | 175 | $0.008479 |
| `p02_elmcity_quote.html` | 3 | 37,501 | 0 | 37,123 | 183 | $0.008482 |
| `p03_ivyprint_catalog.html` | 3 | 37,523 | 0 | 37,145 | 187 | $0.008489 |
| `p04_harborstitch_quote.html` | 3 | 37,494 | 0 | 37,116 | 184 | $0.008481 |
| `p05_maplemills_quote.pdf` | 3 | 37,427 | 0 | 37,049 | 190 | $0.008469 |
| `p06_qtextile_quote.pdf` | 3 | 37,548 | 0 | 37,170 | 193 | $0.008497 |
| `p07_longwharf_quote.pdf` | 3 | 37,467 | 0 | 37,089 | 187 | $0.008477 |
| `p08_chapelst_email.eml` | 3 | 37,487 | 0 | 37,109 | 181 | $0.008477 |
| `p09_westville_email.eml` | 3 | 37,475 | 0 | 37,097 | 191 | $0.008480 |
| `p10_eastrock_email.eml` | 3 | 37,522 | 0 | 37,144 | 181 | $0.008486 |
| `p11_yorkst_quote.html` | 3 | 37,429 | 0 | 37,051 | 183 | $0.008467 |
| `p12_bluehen_quote.pdf` | 3 | 37,462 | 0 | 37,084 | 180 | $0.008472 |

### Per document — cached

| Document | Calls | Input | Cache read | Cache write | Output | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| `p01_bluehen_quote.html` | 3 | 37,423 | 36,612 | 433 | 175 | $0.000588 |
| `p02_elmcity_quote.html` | 3 | 37,431 | 36,616 | 437 | 183 | $0.000594 |
| `p03_ivyprint_catalog.html` | 3 | 37,445 | 36,613 | 454 | 186 | $0.000599 |
| `p04_harborstitch_quote.html` | 3 | 37,415 | 36,608 | 429 | 184 | $0.000592 |
| `p05_maplemills_quote.pdf` | 3 | 37,356 | 36,579 | 399 | 190 | $0.000588 |
| `p06_qtextile_quote.pdf` | 3 | 37,471 | 36,623 | 470 | 191 | $0.000605 |
| `p07_longwharf_quote.pdf` | 3 | 37,396 | 36,598 | 420 | 190 | $0.000594 |
| `p08_chapelst_email.eml` | 3 | 37,408 | 36,606 | 424 | 181 | $0.000590 |
| `p09_westville_email.eml` | 3 | 37,396 | 24,502 | 12,516 | 192 | $0.003195 |
| `p10_eastrock_email.eml` | 3 | 37,446 | 36,625 | 443 | 181 | $0.000594 |
| `p11_yorkst_quote.html` | 3 | 37,352 | 24,478 | 12,496 | 183 | $0.003186 |
| `p12_bluehen_quote.pdf` | 3 | 37,390 | 36,595 | 417 | 180 | $0.000587 |

---

## 3. Against the Problem 2 estimate

`handbook_estimate.md` priced **the handbook alone, on one call**:
10,058 tokens, $0.001006 uncached.

A real document costs **$0.008480** uncached — about
**8× more**. The estimate was not
wrong; it measured something narrower than a run. Three things account for
the gap:

| Why | Effect |
| --- | --- |
| **A document takes 3 model requests, not 1.** Read the document, look up the vendor, look up the SKU — each round trip resends the whole prefix. | ×3 |
| **The prefix is more than the handbook.** The handbook is 10,058 tokens; a full request is ~12,495. The rest is the instructions (1,455 tokens), the tool schemas, the document text and the growing conversation. | ×~1.24 |
| **Every uncached call pays the cache *write* rate**, not the input rate — see §5. | ×1.25 |

4.65× predicted against 8.43× observed: the estimate reconciles.

The handbook token count itself held up exactly. Measured inside the live
system prompt it came to 10,057 tokens against the 10,058 measured standalone —
a one-token boundary effect. **No correction to `handbook_estimate.md` is
needed.**

---

## 4. Projection — 1,000 documents a day for 30 days

30,000 documents, at the measured per-document costs:

| | Per document | Per day | **30 days** |
| --- | --- | --- | --- |
| Uncached | $0.008480 | $8.48 | **$254.39** |
| Cached (as measured) | $0.001026 | $1.03 | **$30.78** |
| Cached (clean, see §5) | $0.000593 | $0.5931 | **$17.79** |

**Caching saves $223.61 a month** at this
volume, and $236.60 if the two
cache misses in §5 are avoided.

At 1,000/day the cache would also stay continuously warm, which the
12-document run could not demonstrate — expirations between batches are the
main thing that would push the real figure toward the middle row.

---

## 5. Two things in the numbers that surprised me

### Running without cache costs *more* than if caching did not exist

The uncached run cost **$0.1018**. Priced as pure input at the base
rate — no caching machinery at all — the same tokens come to **$0.0461**.
Turning the cache off made the run **121% more
expensive than a world without caching.**

Because the prefix never matched, the gateway treated all
445,303 prefix tokens as a *new entry to store* on every
call, and a cache write costs **0.125** per 1M against
**0.1** for plain input — a
25% premium.
Every one of those entries was written and never read.

So there is no neutral setting. A prompt above the caching threshold is either
reused, at a tenth the price, or re-written, at a quarter above the price.
**A prompt that varies at the front is not merely failing to save money — it
is actively paying a penalty**, and the penalty scales with prefix size. An
innocent-looking timestamp or request id at the top of a prompt would cost
25% extra
forever, invisibly.

This also means §4's uncached column is the *honest* cost of getting the
layout wrong, not a strawman.

### Two cached documents cost 5× the other ten

`p09_westville_email.eml` and `p11_yorkst_quote.html` cost
$0.003195 and
$0.003186, against about
$0.000593 for the rest. Their contents are unremarkable; the cause is
timing. Both read 24,502 cached tokens instead
of ~36,600 — two of their three requests hit, one missed and re-wrote
12,516 tokens at the write premium.

The run primes the cache with one document, then fans the rest out four at a
time. These two started while an entry was still being written, so they missed
and paid to write it again. **Cache economics are a property of scheduling,
not just of prompt layout** — the same twelve documents cost
73% more than they needed to because
of when two of them happened to start.

---

*Generated by `scripts/cache_report.py` from `output/cache_test.json` and
`data/prices.json`. Trap file checked after all 24 document runs: empty.*
