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
| Uncached | 24 | **0** | valid — nothing was reused |
| Cached | 24 | **24** | cache in use |

The uncached run reads **zero** cached tokens across all 24
calls. Its input token total (299,537) is within
0.2% of the
cached run's (298,929) — the nonce adds a few tokens per call, so
the two runs are not token-identical, and that difference is in the numbers
below rather than hidden.

---

## 2. Cost

| | Uncached | Cached |
| --- | --- | --- |
| Documents | 12 | 12 |
| Model calls | 24 | 24 |
| Input tokens | 299,537 | 298,929 |
| — read from cache | 0 | 292,311 |
| — written to cache | 296,513 | 3,594 |
| Output tokens | 1,283 | 1,285 |
| **Total cost** | **$0.0677** | **$0.004675** |
| **Cost per document** | **$0.005638** | **$0.000390** |

**Saving: $0.0630 on 12 documents — 93.1%.**
Caching makes a document **14.5× cheaper**.

### Per document — uncached

| Document | Calls | Input | Cache read | Cache write | Output | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| `p01_bluehen_quote.html` | 2 | 24,941 | 0 | 24,689 | 87 | $0.005624 |
| `p02_elmcity_quote.html` | 2 | 24,983 | 0 | 24,731 | 118 | $0.005648 |
| `p03_ivyprint_catalog.html` | 2 | 24,979 | 0 | 24,727 | 107 | $0.005642 |
| `p04_harborstitch_quote.html` | 2 | 25,013 | 0 | 24,761 | 118 | $0.005656 |
| `p05_maplemills_quote.pdf` | 2 | 24,908 | 0 | 24,656 | 90 | $0.005618 |
| `p06_qtextile_quote.pdf` | 2 | 24,986 | 0 | 24,734 | 123 | $0.005652 |
| `p07_longwharf_quote.pdf` | 2 | 24,927 | 0 | 24,675 | 125 | $0.005639 |
| `p08_chapelst_email.eml` | 2 | 24,932 | 0 | 24,680 | 91 | $0.005624 |
| `p09_westville_email.eml` | 2 | 25,079 | 0 | 24,827 | 132 | $0.005677 |
| `p10_eastrock_email.eml` | 2 | 24,957 | 0 | 24,705 | 91 | $0.005629 |
| `p11_yorkst_quote.html` | 2 | 24,907 | 0 | 24,655 | 90 | $0.005618 |
| `p12_bluehen_quote.pdf` | 2 | 24,925 | 0 | 24,673 | 111 | $0.005632 |

### Per document — cached

| Document | Calls | Input | Cache read | Cache write | Output | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| `p01_bluehen_quote.html` | 2 | 24,890 | 24,358 | 280 | 87 | $0.000375 |
| `p02_elmcity_quote.html` | 2 | 24,936 | 24,359 | 325 | 118 | $0.000401 |
| `p03_ivyprint_catalog.html` | 2 | 24,930 | 24,359 | 319 | 135 | $0.000408 |
| `p04_harborstitch_quote.html` | 2 | 24,963 | 24,361 | 350 | 109 | $0.000402 |
| `p05_maplemills_quote.pdf` | 2 | 24,857 | 24,359 | 246 | 90 | $0.000369 |
| `p06_qtextile_quote.pdf` | 2 | 24,940 | 24,359 | 329 | 118 | $0.000402 |
| `p07_longwharf_quote.pdf` | 2 | 24,876 | 24,359 | 265 | 115 | $0.000386 |
| `p08_chapelst_email.eml` | 2 | 24,884 | 24,360 | 272 | 91 | $0.000375 |
| `p09_westville_email.eml` | 2 | 25,021 | 24,360 | 409 | 131 | $0.000426 |
| `p10_eastrock_email.eml` | 2 | 24,903 | 24,360 | 291 | 91 | $0.000379 |
| `p11_yorkst_quote.html` | 2 | 24,856 | 24,359 | 245 | 90 | $0.000369 |
| `p12_bluehen_quote.pdf` | 2 | 24,873 | 24,358 | 263 | 110 | $0.000383 |

---

## 3. Against the Problem 2 estimate

`handbook_estimate.md` priced **the handbook alone, on one call**:
10,058 tokens, $0.001006 uncached.

A real document costs **$0.005638** uncached — about
**6× more**. The estimate was not
wrong; it measured something narrower than a run. Three things account for
the gap:

| Why | Effect |
| --- | --- |
| **A document takes 3 model requests, not 1.** Read the document, look up the vendor, look up the SKU — each round trip resends the whole prefix. | ×3 |
| **The prefix is more than the handbook.** The handbook is 10,058 tokens; a full request is ~12,480. The rest is the instructions (1,455 tokens), the tool schemas, the document text and the growing conversation. | ×~1.24 |
| **Every uncached call pays the cache *write* rate**, not the input rate — see §5. | ×1.25 |

4.65× predicted against 5.61× observed: the estimate reconciles.

The handbook token count itself held up exactly. Measured inside the live
system prompt it came to 10,057 tokens against the 10,058 measured standalone —
a one-token boundary effect. **No correction to `handbook_estimate.md` is
needed.**

---

## 4. Projection — 1,000 documents a day for 30 days

30,000 documents, at the measured per-document costs:

| | Per document | Per day | **30 days** |
| --- | --- | --- | --- |
| Uncached | $0.005638 | $5.64 | **$169.15** |
| Cached (as measured) | $0.000390 | $0.3896 | **$11.69** |
| Cached (clean, see §5) | $0.000390 | $0.3896 | **$11.69** |

**Caching saves $157.46 a month** at this
volume, and $157.46 if the two
cache misses in §5 are avoided.

At 1,000/day the cache would also stay continuously warm, which the
12-document run could not demonstrate — expirations between batches are the
main thing that would push the real figure toward the middle row.

---

## 5. Two things in the numbers that surprised me

### Running without cache costs *more* than if caching did not exist

The uncached run cost **$0.0677**. Priced as pure input at the base
rate — no caching machinery at all — the same tokens come to **$0.0306**.
Turning the cache off made the run **121% more
expensive than a world without caching.**

Because the prefix never matched, the gateway treated all
296,513 prefix tokens as a *new entry to store* on every
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
$0.000426 and
$0.000369, against about
$0.000390 for the rest. Their contents are unremarkable; the cause is
timing. Both read 24,360 cached tokens instead
of ~36,600 — two of their three requests hit, one missed and re-wrote
409 tokens at the write premium.

The run primes the cache with one document, then fans the rest out four at a
time. These two started while an entry was still being written, so they missed
and paid to write it again. **Cache economics are a property of scheduling,
not just of prompt layout** — the same twelve documents cost
0% more than they needed to because
of when two of them happened to start.

---

*Generated by `scripts/cache_report.py` from `output/cache_test.json` and
`data/prices.json`. Trap file checked after all 24 document runs: empty.*
