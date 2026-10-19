"""Measure what reusing the handbook from cache is actually worth.

Runs all 12 practice documents twice:

**cached** — the system prompt (instructions + handbook) is byte-identical on
every call, so the gateway can reuse the prefix.

**uncached** — a unique nonce is prepended to the very first tokens of
**every model request**, so no prefix can match one already stored. Per
*document* is not enough: a run makes three requests, and requests 2 and 3
would share request 1's prefix. The first version of this experiment made
exactly that mistake and showed cache hits on 22 of 36 "uncached" calls.

The uncached set runs **first**, so a cache warmed by the other setup cannot
contaminate it.

Every model request's raw usage is saved to `output/cache_test.json`. The
proof is the gateway's own `cache_read_tokens` field, per call, not a
summary.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic_ai.messages import ModelResponse  # noqa: E402

import runlog  # noqa: E402
from agent import RunDeps, build_agent  # noqa: E402
from config import MODEL_NAME, PROJECT_ROOT  # noqa: E402
from cost import Meter  # noqa: E402

DOCS = PROJECT_ROOT / "data" / "practice_docs"
KEY = PROJECT_ROOT / "data" / "practice_key.json"
OUT = PROJECT_ROOT / "output" / "cache_test.json"
CONCURRENCY = 4


def price(usage) -> dict:
    """One request's tokens and dollars, through the same math as everything else."""
    m = Meter()
    m.record_run_usage(usage)
    d = m.as_dict()
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "cache_read_tokens": int(getattr(usage, "cache_read_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(usage, "cache_write_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "uncached_input_tokens": d["input_tokens"] - d["cached_input_tokens"],
        "usd": d["usd"],
    }


async def run_doc(setup: str, filename: str, defeat_cache: bool, sem) -> list[dict]:
    async with sem:
        agent = build_agent(defeat_cache=defeat_cache)
        result = await agent.run(
            f"Assess the vendor document at: {DOCS / filename}",
            deps=RunDeps(document=filename),
        )
        calls = []
        for i, msg in enumerate(result.all_messages()):
            if isinstance(msg, ModelResponse) and getattr(msg, "usage", None):
                calls.append(
                    {
                        "setup": setup,
                        "document": filename,
                        "model": MODEL_NAME,
                        "request_index": len(calls) + 1,
                        **price(msg.usage),
                    }
                )
        return calls


async def run_setup(setup: str, files: list[str], nonce: bool) -> list[dict]:
    sem = asyncio.Semaphore(CONCURRENCY)

    calls: list[dict] = []
    if nonce:
        results = await asyncio.gather(*(run_doc(setup, f, True, sem) for f in files))
    else:
        # Prime the cache with one document, then fan the rest out: otherwise
        # several start before the first has written and each pays the write.
        first = await run_doc(setup, files[0], False, sem)
        rest = await asyncio.gather(*(run_doc(setup, f, False, sem) for f in files[1:]))
        results = [first, *rest]
    for r in results:
        calls.extend(r)
    return calls


def summarise(calls: list[dict]) -> dict:
    docs = {c["document"] for c in calls}
    return {
        "documents": len(docs),
        "model_calls": len(calls),
        "input_tokens": sum(c["input_tokens"] for c in calls),
        "cache_read_tokens": sum(c["cache_read_tokens"] for c in calls),
        "cache_write_tokens": sum(c["cache_write_tokens"] for c in calls),
        "output_tokens": sum(c["output_tokens"] for c in calls),
        "calls_with_cache_hits": sum(1 for c in calls if c["cache_read_tokens"] > 0),
        "usd": round(sum(c["usd"] for c in calls), 6),
    }


async def main() -> None:
    files = [e["file"] for e in json.loads(KEY.read_text(encoding="utf-8"))]

    print(f"\n  Uncached setup — {len(files)} documents, unique nonce per call")
    uncached = await run_setup("uncached", files, nonce=True)
    print(f"    {len(uncached)} model calls, ${sum(c['usd'] for c in uncached):.4f}")

    print(f"\n  Cached setup — {len(files)} documents, byte-identical prefix")
    cached = await run_setup("cached", files, nonce=False)
    print(f"    {len(cached)} model calls, ${sum(c['usd'] for c in cached):.4f}")

    payload = {
        "model": MODEL_NAME,
        "summary": {"uncached": summarise(uncached), "cached": summarise(cached)},
        "calls": uncached + cached,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    u, c = payload["summary"]["uncached"], payload["summary"]["cached"]
    print(f"\n  {'':12}{'calls':>7}{'input':>10}{'cache rd':>10}{'cache wr':>10}{'out':>8}{'USD':>10}")
    for name, s in (("uncached", u), ("cached", c)):
        print(f"  {name:12}{s['model_calls']:>7}{s['input_tokens']:>10,}"
              f"{s['cache_read_tokens']:>10,}{s['cache_write_tokens']:>10,}"
              f"{s['output_tokens']:>8,}{s['usd']:>10.4f}")
    hits = u["calls_with_cache_hits"]
    verdict = "VALID — zero cache reads" if hits == 0 else f"INVALID — {hits} call(s) hit cache"
    print(f"\n  uncached run: {verdict} ({hits}/{u['model_calls']} calls)")
    print(f"  saving: ${u['usd'] - c['usd']:.4f}  ({(u['usd'] - c['usd']) / u['usd'] * 100:.1f}%)")
    runlog.assert_traps_clean("cache experiment, 24 document runs")
    print(f"\n  wrote {OUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
