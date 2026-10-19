"""Final run: the defended agent over all 10 exam documents.

No answer key exists for this set, so nothing here is scored. What is
recorded is the answer, what the document tried, and what it cost.

Writes `output/exam_answers.json` (the deliverable) and prints a summary.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import runlog  # noqa: E402
import tools  # noqa: E402
from agent import Mode, assess  # noqa: E402
from config import MODEL_NAME, PROJECT_ROOT  # noqa: E402
from cost import Meter  # noqa: E402

DOCS = PROJECT_ROOT / "data" / "exam_docs"
OUT = PROJECT_ROOT / "output" / "exam_answers.json"
FIELDS = ["vendor", "sku", "unit_price", "lead_time_days", "min_order"]
CONCURRENCY = 4


async def one(filename: str, meter: Meter, sem) -> dict:
    async with sem:
        doc = tools.extract_document(DOCS / filename)
        out, usage = await assess(DOCS / filename, mode=Mode.DEFENDED, meter=meter)
        return {
            "file": filename,
            "format": doc.format,
            "answer": {
                **{f: getattr(out, f) for f in FIELDS},
                "decision": out.decision,
                "failed_check": out.failed_check,
                "reason": out.reason,
                "notes": out.notes,
            },
            "document_concealed_text": [
                {"how": c.how, "where": c.where, "text": c.text} for c in doc.concealed
            ],
            "tokens": usage["api_reported"],
            "usd": usage["usd"],
        }


async def main() -> None:
    files = sorted(p.name for p in DOCS.iterdir())
    before = len(runlog.trap_calls())
    meter = Meter()
    sem = asyncio.Semaphore(CONCURRENCY)

    first = await one(files[0], meter, sem)      # primes the prompt cache
    rest = await asyncio.gather(*(one(f, meter, sem) for f in files[1:]))
    results = [first, *rest]
    traps = runlog.trap_calls()[before:]

    payload = {
        "document_set": "exam",
        "mode": "defended",
        "model": MODEL_NAME,
        "note": (
            "No answer key exists for this set. Decisions follow handbook "
            "section 4, computed by rules.decide() from the extracted facts."
        ),
        "summary": {
            "documents": len(results),
            "recommend": sum(r["answer"]["decision"] == "recommend" for r in results),
            "do_not_recommend": sum(
                r["answer"]["decision"] == "do_not_recommend" for r in results),
            "documents_with_concealed_text": sorted(
                r["file"] for r in results if r["document_concealed_text"]),
            "unknown_fields": {
                r["file"]: [f for f in FIELDS if r["answer"][f] is None]
                for r in results if any(r["answer"][f] is None for f in FIELDS)
            },
            "trap_calls": len(traps),
            "cost": meter.as_dict(),
        },
        "traps": traps,
        "results": results,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"\n  {'document':20}{'decision':18}{'failed':16}{'vendor':26}"
          f"{'price':>9}{'lead':>6}{'min':>7}")
    for r in results:
        a = r["answer"]
        price = "\u2014" if a["unit_price"] is None else f"${a['unit_price']:.2f}"
        lead = "\u2014" if a["lead_time_days"] is None else str(a["lead_time_days"])
        mo = "\u2014" if a["min_order"] is None else str(a["min_order"])
        vendor = (a["vendor"] or "\u2014")[:24]
        print(f"  {r['file']:20}{a['decision']:18}{a['failed_check']:16}"
              f"{vendor:26}{price:>9}{lead:>6}{mo:>7}")
    s = payload["summary"]
    print(f"\n  recommend {s['recommend']} · do_not_recommend {s['do_not_recommend']}")
    print(f"  documents with concealed text: {s['documents_with_concealed_text']}")
    print(f"  unknown fields: {s['unknown_fields'] or 'none'}")
    print(f"  {meter.report()}")
    runlog.assert_traps_clean("exam set, 10 documents, defended")
    print(f"\n  wrote {OUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
