# Rules — hw6

The constraints this assignment must obey. Everything built here is written
against this list. Same role as hw5's `RULES.md`.

## Models

- **Every model call uses `gpt-6-luna`, and nothing else.** No other model id
  may appear in the code or in a run. *Points are deducted if any other model
  appears.*
- **There is one place that knows the model name:** `MODEL_NAME` in
  [`config.py`](config.py). Call sites read `config.model()` and never write a
  model string themselves. `config.model()` raises on any other name, and
  `config.client()` is the only route to the gateway, so there is no second
  place a model id can enter the program.
- Credentials resolve in this order, first one wins: the process environment,
  then `./.env`, then `~/.config/ai-keys/keys.env` — the same fallback hw4 and
  hw5 used. Both `PORTKEY_API_KEY` and `PORTKEY_BASE_URL` are already in the
  `ai-keys` file, so no `.env` is needed locally.

### Still to confirm against the handout

`gpt-6-luna` is carried over from hw5, where it was the literal string sent
through Portkey on live runs — known-good, but confirmed for *that* assignment.
Before hw6's first run, check the handout for:

- the exact model id as it goes on the wire (hw5's gateway errors named the
  deployment `gpt-6-luna-global`; that is the gateway's internal name and is
  not what you send);
- the provider / base URL, if hw6 does not use the Portkey gateway;
- which client library the course expects — hw3 used the raw `openai` client,
  hw5 used PydanticAI over it. `config.py` currently assumes only `openai`.

If any of those differ, change `config.py` and this file, and nowhere else.

## The assignment

*(Empty until the spec arrives — the problem-specific rules go here, the way
hw5 recorded the shop's constraints.)*
