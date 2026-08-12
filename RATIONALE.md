# Engineering Rationale

The written rationale the Arootah brief asks for. Everything here is checkable
against the code; where a claim depends on a measurement, the command that
produced it is named.

## a. Data & taxonomy

Four categories a model may emit — `prospect`, `existing_client`,
`vendor_partner`, `noise_other` — defined once as `MODEL_CATEGORIES` in
[`backend/src/triage_backend/schemas.py`](backend/src/triage_backend/schemas.py).
A fifth value, `needs_review`, exists only on `StoredTriageResult` and is
written **only** by the deterministic fallback. That separation is deliberate:
if a model could return `needs_review` itself, a confident guess and an
admission of failure would be the same value in the database.

Priority (`high`/`medium`/`low`) is defined **orthogonally to category**, purely
by urgency and stakes: an upset or deadline-bound existing client is high, a
cold pitch or newsletter is low, routine is medium. It is not a lookup keyed on
category.

That orthogonality is the answer to "what if the taxonomy doubled". Splitting
`vendor_partner` into `vendor_pitch` and `referral_partner` — which `inb-003`
and `inb-007` clearly want — is one tuple entry plus one line of guide text in
`classification/prompt.py`. The prompt, the Anthropic tool's enum and the
OpenAI JSON schema's enum are all *generated* from that tuple, and
`prompt.py` asserts at import time that every value has a definition. Priority
logic, the malformed pre-check and the routing policy do not branch on category
at all, so none of them change. `tests/test_prompt.py` is what keeps this from
being an aspiration: it fails the build if the prompt and the validator drift.

The taxonomy stays at four because the 13-message sample does not support finer
distinctions. Widening it when real traffic demands it beats guessing
sub-categories nobody needs.

## b. Reliable structure

Four layers, in order of how much I trust them.

1. **Provider-native schema enforcement.** The model is never asked to "output
   JSON" in prose.
   - **Anthropic:** forced `tool_choice` to a single `emit_triage` tool with a
     strict `input_schema`. There is no parse-a-string-that-might-be-JSON step.
   - **OpenAI:** `response_format` with a strict JSON schema
     (`additionalProperties: false`, `strict: true`).
2. **Server-side re-validation against the same object.** Whatever comes back
   is validated against `TriageResult` — the same Pydantic model the two
   schemas are generated from. Enum violations, missing fields, blank strings
   and runaway free text are all rejected here. The `summary` field is
   whitespace-collapsed and capped at 400 characters, because the prompt's
   "≤ 20 words" is a preference and an unbounded model string is an unbounded
   string in the UI and in the cache file.
3. **One corrective retry, then stop.** The validation error is quoted back to
   the model and the call is repeated once. A model that cannot satisfy a
   four-field schema twice will not on the third attempt, and the deterministic
   fallback is cheaper and more predictable than another round trip. The shared
   call → validate → correct → retry loop lives once in
   `classification/providers/structured.py`; the two vendor classes only
   describe how to shape a request and where the payload lives.
4. **A deterministic fallback.** Two failures produce
   `needs_review`/`medium`/"Manual review" with the flag
   `validation_failed_twice`, visibly badged in the UI. The client never sees
   invalid data and never sees a 500.

Separately, **any** exception from the API call itself — network, auth, rate
limit, or an SDK-level `TypeError` raised during header validation before a
request even goes out — becomes a `TriageError` and is returned as
`HTTP 200 {error: true}` for that row. One bad message cannot take the list
down. Failed rows are deliberately **not** cached, so Retry actually retries.

## c. Where the model was wrong

**No live model run has been performed in this environment, so I am not going
to report one.** There is no API key configured here and the test suite blocks
network access outright (`tests/conftest.py` patches `socket.connect`), which
is a deliberate property of the repository, not an accident.

What exists instead is the apparatus to answer this question reproducibly:

- [`backend/eval/golden.json`](backend/eval/golden.json) — reference labels for
  all 13 messages, hand-written by reading them, each with the reasoning
  recorded. Genuinely ambiguous items carry `accepted_categories` /
  `accepted_priorities` so a defensible answer is not scored as an error, and
  `inb-009` is marked `ambiguous` and excluded from accuracy entirely.
- [`backend/scripts/evaluate.py`](backend/scripts/evaluate.py) — runs the real
  pipeline over the corpus and prints per-message actual-vs-expected plus
  category/priority/both accuracy. `uv run python scripts/evaluate.py` with a
  key set is a 13-call run; `LLM_PROVIDER=stub` is free.

The only numbers published anywhere in this repository are from the offline
rule baseline (`docs/eval-stub-baseline.txt`): **12/12 category, 11/12
priority** on the 12 scored messages. Those numbers are **overfitted by
construction** — the rules were written while looking at these exact 13
messages — and they are published as a floor and a smoke test, not as evidence
about a model. A model that cannot beat a page of regexes on the set the
regexes were written for is not the headline; a model that cannot beat it on
*new* messages would be.

Two places I expect a real model to disagree with the labels, written down
before any run so the prediction is falsifiable:

- **`inb-009`** ("just following up on our conversation", org `(unknown)`)
  carries no signal separating `prospect` from `existing_client`. The taxonomy
  cannot resolve it and neither can I; that is why it is labelled ambiguous
  rather than scored.
- **`inb-006`** ("no rush at all… what's your minimum, how do fees work")
  is a real prospect who explicitly disclaims urgency. I label it `low`; a model
  reading "asks about fees and minimums" as a buying signal will say `medium`.
  Both are defensible, so `medium` is in `accepted_priorities` — but if a model
  says `high`, that is a genuine miss worth writing up.

## d. Edge cases

Handled in
[`backend/src/triage_backend/classification/heuristics.py`](backend/src/triage_backend/classification/heuristics.py),
**before** any model call, and covered by 24 tests.

- **Near-empty body** (`inb-010`, body `"."`): stripped of whitespace and pure
  punctuation, fewer than 3 meaningful characters remain → `empty_or_near_empty_body`.
- **Garbled content** (`inb-011`: raw control bytes and U+FFFD replacement
  characters) → `garbled_encoding`.
- **Garbled sender** (`inb-011`'s `from_name` is an undecoded RFC 2047
  encoded-word, `=?utf-8?B?…`) → `garbled_sender`. The original pattern was
  anchored to position 0, so any leading whitespace or display-name fragment
  slipped through unflagged; it now searches.
- **Sentinel org values** `(individual)` and `(unknown)` are explicitly *not*
  malformed. The brief calls them out as expected, and treating them as
  corruption would dump real messages into `noise_other`.

Flagged items resolve deterministically to `noise_other`/`low` and are served
with `source: "heuristic"` and their flags, which the UI shows. Skipping the
model rather than sending it garbage is (a) strictly cheaper and (b) more
predictable: a heuristic either matches or it does not, whereas asking a model
to grade its own input's parseability adds another place for structured output
to fail on exactly the inputs where reliability matters most. The cost is that
the heuristic is pattern-matching, not comprehension — a well-formed but
meaningless message passes straight through. For this corpus that is the right
trade.

## e. Scale & risk

**What breaks at 10,000 messages/day.**

The first thing that *did* break was not the model — it was the read path.
`get_inbound_by_id` re-read, re-parsed and re-validated the entire corpus on
every call, and the UI calls it once per row. Measured with
`scripts/bench_lookup.py`: **26.2 ms per lookup at a 10,000-message corpus,
versus 2.91 µs after indexing** (200 lookups per cell; full output in
`docs/bench-lookup.txt`). That is now flat in corpus size.

What breaks next, in order:

1. **The data layer.** A single `results.json` rewritten wholesale on every
   save is not a query surface — "today's unhandled high-priority items" means
   loading everything into memory — and it does not survive multiple processes.
   Writes are at least atomic and content-keyed now, so concurrent readers
   never see a torn file and an edited message is not served a stale triage,
   but that is making a stopgap safe, not making it a database.
2. **Cost and latency.** 10k calls a day with no batching, no queue and no
   backpressure. The browser's three-way concurrency cap is tuned for "13 rows
   on page load", not throughput. This needs a worker and batched calls.
3. **Silent accumulation.** Fallback and error rows are individually visible
   but nothing counts them. At 13 rows a human notices; at 10k, a rising pile
   of `needs_review` is invisible without a metric and an alert on it. The
   `source` and `flags` fields are the hooks for that; nothing consumes them yet.

**The biggest risk in shipping this to a real advisory firm** is a confident
misclassification of an urgent existing-client message. A malformed item is
visibly flagged; an API error is visibly flagged; a *confidently wrong* triage
looks exactly like a correct one. For a firm handling client money, "I'm not
happy about this fee, call me today" (`inb-005`) sitting at `medium` is worse
than the tool being unavailable, because unavailability is noticed.

Mitigations, in the order I would build them:

1. **Keep a human in the loop.** This is a triage aid, not an auto-router.
   Nothing here should suppress a message or close a loop by itself.
2. **Deterministic safety-net rules under the model, not instead of it.** An
   existing client whose message matches "fee", "complaint", "not happy" is
   forced to `high` regardless of the model's answer. The rule engine for this
   already exists as the `stub` provider and is already tested; wiring it as a
   floor under the model is a small change.
3. **An audit trail.** Every triage decision recorded, not overwritten on
   retriage, so misclassifications are reviewable after the fact — and so the
   golden set can grow from real disagreements instead of my guesses.
4. **Measure before trusting.** `scripts/evaluate.py` against a growing labelled
   set, run on every prompt or model change. A prompt change with no evaluation
   is a deployment with no test.
