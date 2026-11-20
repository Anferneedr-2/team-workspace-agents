# TypeSafe Jev as a memory decision layer

Jev System One is a batch question-answering endpoint: send one piece of state and a map of named questions, get a map of named answers. Use it to decide memory admission, classification, tagging, contradiction, and recall relevance — not as a vector store.

## Endpoint and auth

- `POST https://api.typesafe.ai/v1/systemone`
- `Authorization: Bearer $TYPESAFE_API_KEY` (OpenAPI security scheme is `HTTPBearer`)
- `GET https://api.typesafe.ai/v1/models` to confirm the model name; `jev-latest` is the alias used here.
- Contract: `curl -sS https://api.typesafe.ai/openapi.json`

## Request shape

```json
{
  "model": "jev-latest",
  "state": {"text": "Jake prefers concise answers.", "existing": []},
  "questions": {
    "remember": {"type": "noul", "instructions": "Is this worth remembering long-term?"},
    "kind": {
      "type": "choice",
      "instructions": "Classify the memory kind.",
      "criteria": {"preference": "A like, dislike, style, or way of working.", "fact": "A stable factual statement."}
    },
    "importance": {
      "type": "score",
      "instructions": "How important is this memory?",
      "criteria": [
        {"label": "trivial", "description": "Small talk or noise."},
        {"label": "useful", "description": "Worth recalling later."},
        {"label": "important", "description": "Changes how work is done."},
        {"label": "critical", "description": "A rule, constraint, or irreversible decision."}
      ]
    },
    "domain": {"type": "choice", "instructions": "Pick a domain.", "criteria": {"personal": "...", "technical": "..."}},
    "sensitivity": {"type": "choice", "instructions": "Pick sensitivity.", "criteria": {"normal": "...", "private": "...", "secret": "..."}},
    "tag_preference": {"type": "noul", "instructions": "Does this express a preference?"},
    "supersede_0": {"type": "noul", "instructions": "Does the new text contradict or replace the existing memory?"},
    "rel_0": {"type": "noul", "instructions": "Is this memory relevant to the query?"}
  }
}
```

`state` may be a string, object, or array; an object with named fields is easiest to reason about and to cache. `questions` is required and must be non-empty. `assets` is optional and only needed for media.

## Question types

| Type | Request | Answer | Use |
|---|---|---|---|
| `noul` | `{type, instructions, criteria?}` | `{type:"noul", noul: 0..1, confidence}` | admission, per-tag yes/no, supersede, relevance |
| `choice` | `{type, instructions, criteria: {label: description}}` | `{type:"choice", choice: label, confidence, probabilities}` | kind, domain, sensitivity |
| `score` | `{type, instructions, criteria: [{label, description}, ...]}` | `{type:"score", score: number, confidence}` | importance; normalize against the highest criterion |

`noul` is a probability in `[0,1]`; compare it to an explicit threshold (e.g. admit `>= 0.55`, supersede `>= 0.72`). Do not treat it as a boolean. For `score`, divide by the maximum criterion value so importance is always `0..1`, independent of how many levels the prompt defines.

## Response parsing

```json
{
  "model": "jev-...",
  "answers": {
    "remember": {"type": "noul", "noul": 0.93, "confidence": 0.9},
    "kind": {"type": "choice", "choice": "preference", "confidence": 0.86, "probabilities": {"preference": 0.86, "fact": 0.02}},
    "importance": {"type": "score", "score": 3, "confidence": 0.8},
    "rel_0": {"type": "noul", "noul": 0.91, "confidence": 0.9}
  },
  "usage": {"input_tokens": 420, "output_tokens": 40}
}
```

Read `answers[name]`, not a positional list. Keep `usage.input_tokens` for cost telemetry; the answer itself does not carry cost. Treat a missing answer as a degraded result, not as a default `true`.

## Cost control

- One request per retain and one per recall; batch every question into that request.
- Cap candidate text (`max_candidate_chars` around 480) before sending; send summaries for long memories.
- Cache the full request payload hash for 30 days. Identical text reuses the decision at zero token cost.
- Jev pricing observed at research time: about **$0.042 per million input tokens**, output free. Treat pricing as volatile and re-check the console before quoting it to the user.
- Rerank at most 16 of 24 FTS candidates; return 8 by default.

## Failure handling

- `401` — key missing/wrong. Disable the Jev path and report `jev_configured=false`; do not retry with the same key.
- `429` / `5xx` — one retry with backoff, then open the circuit.
- Timeout — abort the request at the deadline and fall back to deterministic scoring; never wait for the model to finish.
- Circuit breaker — after repeated failures, skip the HTTP call entirely for a cool-down period; expose `circuit: open|closed` in health/stats.
- Log decision summaries and token counts, never memory text or the key.

## Minimal live probe

```bash
curl -sS https://api.typesafe.ai/v1/systemone \
  -H "Authorization: Bearer $TYPESAFE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"jev-latest","state":{"text":"Jake prefers concise answers."},"questions":{"remember":{"type":"noul","instructions":"Is this worth remembering?"}}}'
```

A valid response contains `answers.remember.noul`. If it does not, fix the contract before touching the Hermes provider.
