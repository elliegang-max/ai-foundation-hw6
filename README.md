# hw6 — AI Foundation

Scaffold only. The assignment spec has not been written down here yet, so this
README describes the setup and nothing else; it gets rewritten for graders once
there is something to grade.

---

## Quick start

**Install.** Python 3.14 (same interpreter hw3–hw5 used).

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Credentials.** Model calls go through the Portkey gateway. Resolution order,
first one wins: the process environment, then `./.env`, then
`~/.config/ai-keys/keys.env` — the same fallback hw4 and hw5 used. Both
`PORTKEY_API_KEY` and `PORTKEY_BASE_URL` already live in the `ai-keys` file, so
no local `.env` is needed on this machine.

```bash
cp .env.example .env     # only if you want per-project overrides
```

---

## Layout

| Path             | What goes here                                           |
| ---------------- | -------------------------------------------------------- |
| `data/`          | The assignment's dataset / handout files. Committed by default, like hw3's product photos — add a `data/*` ignore block with exceptions if the pack gets big, the way hw5 did. |
| `output/`        | Everything the code produces: run artefacts, `harness.md`, figures. |
| `scripts/`       | One-off runners and helpers.                              |
| `AI_prompts.md`  | The prompt log, one section per problem.                  |
| `.env.example`   | Environment template. The real `.env` is never committed. |
