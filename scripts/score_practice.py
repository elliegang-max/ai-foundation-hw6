"""Run the agent over the 12 practice documents and score it against the key.

Self-scoring before the exam set is the point of `data/practice_key.json`
existing. Writes `output/practice_run.json` (every answer, every mismatch) and
prints a scoreboard.

The first document is run alone to prime the gateway's prompt cache: the
~10k-token system prompt is identical on every call, so one call writes the
cache and the remaining eleven read it at a tenth the price. Fanning all
twelve out at once would have several of them miss and pay the write rate.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import Mode, assess  # noqa: E402
from config import PROJECT_ROOT  # noqa: E402
import runlog  # noqa: E402
from cost import METER  # noqa: E402

DOCS = PROJECT_ROOT / "data" / "practice_docs"
KEY = PROJECT_ROOT / "data" / "practice_key.json"
OUT = PROJECT_ROOT / "output" / "practice_run.json"
OUT_UNDEF = PROJECT_ROOT / "output" / "practice_run_undefended.json"

SCORED = ["vendor", "sku", "unit_price", "lead_time_days", "min_order", "decision"]
CONCURRENCY = 4


def equal(field: str, got: object, want: object) -> bool:
    """Field comparison, lenient only where leniency is clearly right."""
    if got is None or want is None:
        return got == want
    if field == "unit_price":
        return abs(float(got) - float(want)) < 0.005
    if field in {"lead_time_days", "min_order"}:
        return int(got) == int(want)
    if field == "vendor":
        return str(got).strip().lower() == str(want).strip().lower()
    return str(got).strip() == str(want).strip()


async def one(entry: dict, sem: asyncio.Semaphore | None = None,
              mode: "Mode" = None) -> dict:
    async def run() -> dict:
        try:
            out, _usage = await assess(DOCS / entry["file"], mode=mode or Mode.DEFENDED)
            got = out.key_fields()
            mismatches = {
                f: {"got": got[f], "want": entry[f]}
                for f in SCORED
                if not equal(f, got[f], entry[f])
            }
            return {
                "file": entry["file"],
                "got": got,
                "want": {f: entry[f] for f in SCORED},
                "mismatches": mismatches,
                "correct_fields": len(SCORED) - len(mismatches),
                "all_correct": not mismatches,
                "decision_correct": "decision" not in mismatches,
                "reason": out.reason,
                "failed_check": out.failed_check,
                "notes": getattr(out, "notes", ""),
            }
        except Exception as exc:  # a crash is a wrong answer, not a stop
            return {
                "file": entry["file"],
                "error": f"{type(exc).__name__}: {exc}",
                "correct_fields": 0,
                "all_correct": False,
                "decision_correct": False,
            }

    if sem is None:
        return await run()
    async with sem:
        return await run()


async def main() -> None:
    mode = Mode.UNDEFENDED if "--no-defenses" in sys.argv else Mode.DEFENDED
    key = json.loads(KEY.read_text(encoding="utf-8"))

    first, rest = key[0], key[1:]
    results = [await one(first, mode=mode)]  # primes the prompt cache
    sem = asyncio.Semaphore(CONCURRENCY)
    results += await asyncio.gather(*(one(e, sem, mode) for e in rest))
    print(f"\n  mode: {mode.value}")

    fields_right = sum(r["correct_fields"] for r in results)
    fields_total = len(results) * len(SCORED)
    exact = sum(r["all_correct"] for r in results)
    decisions = sum(r["decision_correct"] for r in results)

    per_field = {
        f: sum(1 for r in results if f not in r.get("mismatches", {"x": 1}) and "error" not in r)
        for f in SCORED
    }

    summary = {
        "mode": mode.value,
        "documents": len(results),
        "exact_match": f"{exact}/{len(results)}",
        "decision_accuracy": f"{decisions}/{len(results)}",
        "field_accuracy": f"{fields_right}/{fields_total}",
        "field_accuracy_pct": round(fields_right / fields_total * 100, 1),
        "per_field": per_field,
        "cost": METER.as_dict(),
    }

    out_path = OUT_UNDEF if mode is Mode.UNDEFENDED else OUT
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2) + "\n")

    print(f"\n  Practice set — {len(results)} documents\n")
    for r in results:
        mark = "OK  " if r["all_correct"] else "MISS"
        note = r.get("error") or ", ".join(
            f"{f}: got {m['got']!r} want {m['want']!r}"
            for f, m in r.get("mismatches", {}).items()
        )
        print(f"  {mark}  {r['file']:32} {note}")
    print(f"\n  exact match     {summary['exact_match']}")
    print(f"  decisions       {summary['decision_accuracy']}")
    print(f"  fields          {summary['field_accuracy']}  ({summary['field_accuracy_pct']}%)")
    print(f"  per field       {per_field}")
    print(f"  {METER.report()}")
    runlog.assert_traps_clean(f"practice set, 12 documents, {mode.value}")


if __name__ == "__main__":
    asyncio.run(main())
