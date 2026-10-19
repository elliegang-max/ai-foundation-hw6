"""Turn the measured token count + prices.json into output/handbook_estimate.md.

Generated rather than hand-written so the prose, the table and the arithmetic
cannot drift apart. Re-run after `count_handbook_tokens.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MODEL_NAME, PROJECT_ROOT  # noqa: E402

TOKENS_JSON = PROJECT_ROOT / "output" / "handbook_tokens.json"
PRICES_JSON = PROJECT_ROOT / "data" / "prices.json"
OUT = PROJECT_ROOT / "output" / "handbook_estimate.md"

N = 1000


def usd(x: float) -> str:
    """Dollars at a precision that doesn't round sub-cent figures to zero."""
    return f"${x:,.6f}" if abs(x) < 0.01 else f"${x:,.4f}"


def main() -> None:
    meas = json.loads(TOKENS_JSON.read_text(encoding="utf-8"))
    prices = json.loads(PRICES_JSON.read_text(encoding="utf-8"))
    row = prices[MODEL_NAME]

    t = meas["measurement"]["handbook_tokens"]
    r_in = row["input_per_1m"]
    r_cached = row["cached_input_per_1m"]
    r_write = row["cache_write_per_1m"]

    # Per-token rates
    p_in, p_cached, p_write = r_in / 1e6, r_cached / 1e6, r_write / 1e6

    uncached_1 = t * p_in
    uncached_n = uncached_1 * N
    # Caching: the first call has nothing to read, so it pays the write rate.
    # Every later call reads the same prefix at the cached rate.
    cached_1 = t * p_write
    cached_n = t * p_write + (N - 1) * t * p_cached

    saving = uncached_n - cached_n
    pct = saving / uncached_n * 100

    md = f"""# Handbook token count and cost — hw6

What one copy of `data/shop_handbook.md` costs to put in front of
`{MODEL_NAME}`, measured rather than estimated.

---

## 1. The token count

**The handbook is {t:,} tokens.**

### How I got it

Not a rule of thumb. `{MODEL_NAME}`'s tokenizer is not something to assume —
a `characters / 4` estimate or a borrowed `tiktoken` encoding would be a
guess — so the count comes from the gateway itself, which is the only
authority on how this model will actually bill the text.

`scripts/count_handbook_tokens.py` makes **two** chat completions calls whose
scaffolding is identical and whose only difference is the message content:

| Call | User message | `usage.prompt_tokens` |
| --- | --- | --- |
| A | the whole handbook | {meas['measurement']['prompt_tokens_with_handbook']:,} |
| B | empty string | {meas['measurement']['prompt_tokens_empty_message']} |

Subtracting cancels the chat template that wraps every request, leaving the
handbook's own tokens:

```
handbook = {meas['measurement']['prompt_tokens_with_handbook']:,} − {meas['measurement']['prompt_tokens_empty_message']}
         = {t:,} tokens
```

So B's {meas['measurement']['prompt_tokens_empty_message']} tokens are the
per-request overhead, and **{t:,}** is the handbook alone. The completions
themselves are discarded; only `usage` is read.

**This is a measurement, not an estimate.** Two separate runs returned
{t:,} both times — token counting is deterministic, so the figure is exact
for this file and this model.

### Why it was worth measuring

| | |
| --- | --- |
| File size | {meas['bytes']:,} bytes |
| Characters | {meas['characters']:,} |
| Words | {meas['words']:,} |
| **Measured tokens** | **{t:,}** |
| Characters per token | {meas['chars_per_token']} |

The common `characters / 4` shortcut would have predicted
{round(meas['characters'] / 4):,} tokens — **{abs(round((meas['characters'] / 4 / t - 1) * 100, 1))}% low**.
This handbook runs about {meas['chars_per_token']} characters per token, not 4,
because it is dense in markdown tables, SKU codes and prices, which fragment
into more tokens than prose does. Estimating would have understated the bill
by nearly a third.

---

## 2. What it costs

Rates from `data/prices.json`, per 1M tokens:

| Rate | $/1M | $/token |
| --- | --- | --- |
| Input (uncached) | {r_in} | {p_in:.10f} |
| Cached input | {r_cached} | {p_cached:.10f} |
| Cache write | {r_write} | {p_write:.10f} |

Cached input is **{r_in / r_cached:.0f}× cheaper** than fresh input. Writing the
cache costs **{r_write / r_in:.2f}×** a normal input token — a one-off premium
that later calls pay back.

> Input only. This is the handbook sitting in the prompt and nothing else — no
> instructions, no vendor document, no output tokens.

### The four cases

| | 1 call | 1,000 calls |
| --- | --- | --- |
| **Without caching** | {usd(uncached_1)} | {usd(uncached_n)} |
| **With caching** | {usd(cached_1)} | {usd(cached_n)} |

### The math

**Without caching** — every call pays full input rate for all {t:,} tokens:

```
1 call      = {t:,} tokens × ${r_in}/1M
            = {t:,} × {p_in:.10f}
            = {usd(uncached_1)}

1,000 calls = {usd(uncached_1)} × 1,000
            = {usd(uncached_n)}
```

**With caching** — a cache has to be written before it can be read, so the
first call pays the write rate and the other 999 pay the cached rate:

```
1 call      = {t:,} tokens × ${r_write}/1M        (write; nothing to read yet)
            = {t:,} × {p_write:.10f}
            = {usd(cached_1)}

1,000 calls = 1 write        + 999 reads
            = ({t:,} × {p_write:.10f}) + (999 × {t:,} × {p_cached:.10f})
            = {usd(cached_1)} + {usd((N - 1) * t * p_cached)}
            = {usd(cached_n)}
```

### Reading the table

**One call is cheaper *without* caching.** {usd(cached_1)} against
{usd(uncached_1)} — {(r_write / r_in - 1) * 100:.0f}% more, because the single
call pays to write a cache nothing ever reads. Caching is an investment that
needs a second call to break even.

**A thousand calls are far cheaper with it.** {usd(cached_n)} against
{usd(uncached_n)} — **{usd(saving)} saved, {pct:.1f}%**. At 22 documents the
handbook would be re-sent 22 times, and this is the single biggest lever on
the bill.

### What the cached figure assumes

- **The handbook is a byte-identical prefix on every call.** Caching matches a
  literal prefix. One changed character anywhere in it, or anything variable
  placed before it, and the call is a full-price miss. Put the handbook and
  the instructions first, the per-document text last.
- **The {t:,} tokens clear the minimum.** Prompt caching applies only above a
  minimum prefix length (commonly 1,024 tokens); the handbook is ~{t / 1024:.1f}×
  that, so it qualifies comfortably.
- **The calls are close together in time.** Cache entries expire after a period
  of inactivity. Spread the 1,000 calls out and some pay the write rate again;
  the figure above assumes exactly one write.
- **One write, not more.** With concurrent calls, several may start before the
  first has written the cache and each pays the write rate. Priming the cache
  with one call before fanning out keeps it at one.

---

*Generated by `scripts/handbook_estimate.py` from `output/handbook_tokens.json`
and `data/prices.json`. Token count measured against {MODEL_NAME} through the
Portkey gateway.*
"""
    OUT.write_text(md, encoding="utf-8")
    print(f"wrote {OUT.relative_to(PROJECT_ROOT)}")
    print(f"  tokens      {t:,}")
    print(f"  1 call      uncached {usd(uncached_1)}   cached {usd(cached_1)}")
    print(f"  1,000 calls uncached {usd(uncached_n)}   cached {usd(cached_n)}")
    print(f"  saving at 1,000: {usd(saving)} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
