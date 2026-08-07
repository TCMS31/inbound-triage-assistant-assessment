# Triage prompt

The live prompt is **generated** in
[`backend/src/triage_backend/classification/prompt.py`](../backend/src/triage_backend/classification/prompt.py)
from the taxonomy tuples in `schemas.py` — the same tuples `TriageResult`
validates against. The block below is the exact rendered output of
`SYSTEM_PROMPT`, reproduced here for review; the code is the source of truth.

To print it yourself:

```bash
cd backend
uv run python -c "from triage_backend.classification.prompt import SYSTEM_PROMPT; print(SYSTEM_PROMPT)"
```

## System prompt

Identical for both providers.

```text
You are the inbound-triage assistant for Northwind Advisors, an alternative-investment and family-office advisory firm. You read one inbound message at a time (email, web-form, LinkedIn, or voicemail transcript) and classify it so a human can route it quickly.

Categories (choose exactly one):
- prospect: a new business inquiry from someone who is not yet a client.
- existing_client: a request, question, or issue from someone who is already a client (they say so, or reference an account/portfolio/advisor relationship).
- vendor_partner: a vendor pitch, sales outreach, or referral/partnership proposal aimed at the firm.
- noise_other: recruiting outreach, newsletters, automated mail, or anything that is not a real business message for the firm.

Priority (choose exactly one), based on urgency and stakes, independent of category:
- high: an existing client who is upset, blocked, or has a hard deadline; or a clearly high-value warm prospect.
- medium: a normal request or inquiry with no urgent deadline.
- low: cold outreach, recruiting, newsletters, or anything low-stakes/low-signal.

Notes on the data: from_org may contain the sentinel values "(individual)" or "(unknown)" — these are not real organization names, treat the sender as an individual with an unknown/no firm. Some fields may be empty; use whatever signal is present in subject/body.

Ground every field in the message text you are given. Do not invent account numbers, names, amounts, or history that is not present in the message; if the message does not say, do not assert it.

Return your result as a JSON object with exactly four fields:
  summary     — a single line, at most ~20 words (hard limit 400 characters), not just restating the subject.
  category    — one of: prospect, existing_client, vendor_partner, noise_other.
  priority    — one of: high, medium, low.
  next_action — a short, concrete instruction (e.g. "Route to advisor on Dana Whitfield's account", "Send standard fee schedule + minimum", "No action — archive as newsletter").

If you are given a tool to call, call it exactly once with your result.```

## User turn

One message as plain key/value lines — not the raw JSON record. Cheaper, and it
stops the model reading stray JSON syntax inside a garbled body as structure.

```text
channel: {channel}
from_name: {from_name or "(empty)"}
from_org: {from_org or "(empty)"}
subject: {subject or "(empty)"}
body: {body or "(empty)"}
```

## Approach — structure, parameters, validation

### Anthropic (Claude)

- **Structure:** one tool, `emit_triage`, with a strict `input_schema`
  (required `summary`, `category` enum, `priority` enum, `next_action`), called
  with `tool_choice={"type": "tool", "name": "emit_triage"}`. That forces the
  call, so the output is reliably structured rather than hopefully structured —
  there is no parse-a-string step at all.
- **Parameters:** `max_tokens=500` (the output is four short fields; this caps
  the blast radius of a model that decides to narrate), default temperature
  (nothing here benefits from creativity, and classification is not hurt by the
  small default variance), a 30 s request timeout and one transport-level retry.

### OpenAI (GPT)

- **Structure:** `response_format` with a strict JSON schema
  (`strict: true`, `additionalProperties: false`) — the same four fields and the
  same enums, generated from the same tuples.
- **Parameters:** default temperature, same timeout and transport-retry policy.
  No `max_tokens` override.

### Validation — both providers

The payload (tool-call input for Anthropic, parsed JSON for OpenAI) is validated
server-side against `TriageResult`, the Pydantic model the schemas are generated
from. The schema the model is forced to emit and the schema we trust are the
same object, so they cannot drift. Validation also rejects blank strings and
caps `summary`/`next_action` at 400 characters, because "≤ 20 words" in a prompt
is a preference and not a guarantee.

On failure, one corrective turn quotes the validation error back and asks for a
retry. On a second failure, the routing layer returns a deterministic
`needs_review`/`medium` result flagged `validation_failed_twice`. Bad data never
reaches the client, and the client never sees a 500.

### The offline baseline

`LLM_PROVIDER=stub` runs a transparent keyword classifier instead of a model —
no key, no network, no spend. It exists so the UI, the test suite and the
screenshots work without an API key, and so `backend/scripts/evaluate.py` has a
floor to compare a model against. It is never selected by `auto`, and its
results are served as `source: "baseline"` so they cannot be mistaken for model
output.
