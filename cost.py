"""Token and cost accounting for every model call.

`data/prices.json` ships `gpt-6-luna`'s prices, so the run is probably scored
partly on cost. Metering is therefore wired in from the first call rather than
reconstructed afterwards from logs.

Usage — record every response, print the bill at the end:

    from config import client, model
    from cost import METER

    resp = await client().chat.completions.create(model=model(), messages=[...])
    METER.record(resp)
    ...
    print(METER.report())
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import MODEL_NAME, PROJECT_ROOT

PRICES_PATH = PROJECT_ROOT / "data" / "prices.json"


@dataclass(frozen=True)
class Prices:
    """Dollars per 1M tokens, as given by the course."""

    input_per_1m: float
    cached_input_per_1m: float
    cache_write_per_1m: float
    output_per_1m: float

    @classmethod
    def load(cls, model_name: str = MODEL_NAME) -> "Prices":
        if not PRICES_PATH.exists():
            raise FileNotFoundError(f"missing price table: {PRICES_PATH}")
        table = json.loads(PRICES_PATH.read_text(encoding="utf-8"))
        if model_name not in table:
            raise KeyError(
                f"{model_name!r} is not priced in {PRICES_PATH.name} "
                f"(has: {sorted(k for k in table if k != 'source')})"
            )
        row = table[model_name]
        return cls(
            input_per_1m=float(row["input_per_1m"]),
            cached_input_per_1m=float(row["cached_input_per_1m"]),
            cache_write_per_1m=float(row["cache_write_per_1m"]),
            output_per_1m=float(row["output_per_1m"]),
        )


def _usage_fields(usage: Any) -> tuple[int, int, int]:
    """(uncached_input, cached_input, output) from an OpenAI usage object.

    `prompt_tokens` is the *total* prompt, cached included, so the cached part
    is subtracted out rather than counted twice at the full rate.
    """
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    output = int(getattr(usage, "completion_tokens", 0) or 0)

    details = getattr(usage, "prompt_tokens_details", None)
    cached = 0
    if details is not None:
        cached = int(getattr(details, "cached_tokens", 0) or 0)
    elif isinstance(usage, dict):  # some gateways hand back plain dicts
        cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)

    return max(prompt - cached, 0), cached, output


@dataclass
class Meter:
    """A running tally across every call in a run. Thread- and task-safe."""

    prices: Prices = field(default_factory=Prices.load)
    calls: int = 0
    uncached_input: int = 0
    cached_input: int = 0
    output: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, response: Any) -> None:
        """Add one API response's usage to the tally. Silent if usage is absent."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        uncached, cached, out = _usage_fields(usage)
        with self._lock:
            self.calls += 1
            self.uncached_input += uncached
            self.cached_input += cached
            self.output += out

    @property
    def input_tokens(self) -> int:
        return self.uncached_input + self.cached_input

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output

    @property
    def dollars(self) -> float:
        p = self.prices
        return (
            self.uncached_input * p.input_per_1m
            + self.cached_input * p.cached_input_per_1m
            + self.output * p.output_per_1m
        ) / 1_000_000

    def as_dict(self) -> dict[str, Any]:
        """For writing next to a run's artefacts in `output/`."""
        return {
            "model": MODEL_NAME,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input,
            "output_tokens": self.output,
            "total_tokens": self.total_tokens,
            "usd": round(self.dollars, 6),
        }

    def report(self) -> str:
        d = self.as_dict()
        hit = (self.cached_input / self.input_tokens * 100) if self.input_tokens else 0.0
        return (
            f"{d['calls']} calls to {d['model']} — "
            f"{d['input_tokens']:,} in ({hit:.0f}% cached), "
            f"{d['output_tokens']:,} out, "
            f"{d['total_tokens']:,} total — ${d['usd']:.4f}"
        )


#: The run-wide tally. Import this rather than making your own.
METER = Meter()
