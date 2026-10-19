"""Model and credentials — the one place a model client is built.

The assignment allows exactly one model, so exactly one module knows its name
and exactly one function hands out a client. There is no other route to the
gateway, so no call site can quietly name a different model.

This is hw5's `backend/settings.py` pattern, trimmed to the parts that do not
assume an agent framework. If hw6 turns out to need PydanticAI (or anything
else), wrap `client()` there rather than building a second client.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from openai import AsyncOpenAI, OpenAI

#: The only model this assignment may use. Points are deducted for any other.
#:
#: Provenance: this is the literal string hw5 sent on the wire through Portkey
#: across its live runs, so it is a known-good gateway model id, not a guess.
#: Note the gateway's own error messages name the deployment `gpt-6-luna-global`
#: — that is its internal name, and is *not* what you send. Confirm against the
#: hw6 handout before the first run; if the course changed it, change it here
#: and nowhere else.
MODEL_NAME = "gpt-6-luna"

PROJECT_ROOT = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    """Set any KEY=VALUE from a dotenv-style file that isn't already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip())


def _load_credentials() -> tuple[str, str]:
    """Portkey key and base URL: process env, then ./.env, then ~/.config."""
    _load_env_file(PROJECT_ROOT / ".env")
    _load_env_file(Path.home() / ".config" / "ai-keys" / "keys.env")

    key = os.environ.get("PORTKEY_API_KEY")
    base_url = os.environ.get("PORTKEY_BASE_URL")
    if not key or not base_url:
        raise RuntimeError(
            "PORTKEY_API_KEY and PORTKEY_BASE_URL must be set — see .env.example"
        )
    return key, base_url


def _kwargs() -> dict[str, object]:
    key, base_url = _load_credentials()
    return {
        "base_url": base_url,
        "api_key": "unused",  # Portkey authenticates with its own header
        "default_headers": {"x-portkey-api-key": key},
        "timeout": 120.0,
        "max_retries": 2,
    }


@lru_cache(maxsize=1)
def client() -> AsyncOpenAI:
    """One async client for the whole assignment, pointed at Portkey."""
    return AsyncOpenAI(**_kwargs())  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def sync_client() -> OpenAI:
    """The same, for scripts that have no event loop."""
    return OpenAI(**_kwargs())  # type: ignore[arg-type]


def model(name: str = MODEL_NAME) -> str:
    """The assignment's model id. Refuses any name but `MODEL_NAME`.

    Pass the result to every call rather than writing a literal, so that a
    stray model id fails loudly here instead of silently billing elsewhere.
    """
    if name != MODEL_NAME:
        raise ValueError(
            f"this assignment allows {MODEL_NAME!r} only, not {name!r} — "
            "every call must use the same model"
        )
    return name
