"""Measure the Shop Handbook's token count against the gateway.

The count has to be a measurement, not a rule of thumb. `gpt-6-luna`'s
tokenizer is not something we can assume — a `chars/4` estimate or a borrowed
`tiktoken` encoding would be a guess — so this asks the model itself and reads
`usage.prompt_tokens` back.

Method: two calls with identical scaffolding, differing only in whether the
handbook is in the user message. Subtracting cancels the chat template
overhead and leaves the handbook's own tokens.

    handbook_tokens = prompt_tokens(handbook) - prompt_tokens(empty)

Output goes to output/handbook_tokens.json. Writes nothing else; costs about
a third of a cent.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import MODEL_NAME, PROJECT_ROOT, client, model  # noqa: E402

HANDBOOK = PROJECT_ROOT / "data" / "shop_handbook.md"
OUT = PROJECT_ROOT / "output" / "handbook_tokens.json"


async def prompt_tokens(content: str) -> int:
    """`usage.prompt_tokens` for a one-message prompt carrying `content`."""
    # No temperature: this model accepts only its default.
    resp = await client().chat.completions.create(
        model=model(),
        messages=[{"role": "user", "content": content}],
        # Reasoning headroom: the gateway 400s outright if the model hits the
        # output limit before finishing. The completion is thrown away — only
        # usage.prompt_tokens matters — so this just has to be large enough.
        max_completion_tokens=2000,
    )
    return int(resp.usage.prompt_tokens)


async def main() -> None:
    text = HANDBOOK.read_text(encoding="utf-8")

    with_handbook, empty = await asyncio.gather(
        prompt_tokens(text),
        prompt_tokens(""),
    )
    handbook_only = with_handbook - empty

    result = {
        "model": MODEL_NAME,
        "file": str(HANDBOOK.relative_to(PROJECT_ROOT)),
        "bytes": HANDBOOK.stat().st_size,
        "characters": len(text),
        "words": len(text.split()),
        "lines": text.count("\n") + 1,
        "measurement": {
            "method": (
                "two chat.completions calls with identical scaffolding; "
                "usage.prompt_tokens differenced to cancel the chat template"
            ),
            "prompt_tokens_with_handbook": with_handbook,
            "prompt_tokens_empty_message": empty,
            "handbook_tokens": handbook_only,
        },
        "chars_per_token": round(len(text) / handbook_only, 3),
    }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
