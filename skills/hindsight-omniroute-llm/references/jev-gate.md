# Jev admission gate (`memory.provider: jev`) — verification runbook

`jev` is not a replacement memory backend. It subclasses the Hindsight provider and adds an
admission check on four automatic paths. Hindsight stays the store; tools, config, session
handling and shutdown are inherited untouched. So every Hindsight setting (gateway, model, key
resolution) applies unchanged — when `hermes memory status` prints `Provider: jev`, that is the
expected end state, not a misconfiguration to revert.

## What is gated vs. not

| Path | Gated action | Notes |
|---|---|---|
| `sync_turn` | per-turn retain | skip when the turn scores below `retain_min` |
| `queue_prefetch` | per-turn recall | skip when the query scores below `recall_min` |
| `on_memory_write` | MEMORY.md mirror | same gate as retain |
| `prefetch` | recall | only in Hindsight's opt-in `recall_sync` mode |

NOT gated, by design: explicit `hindsight_retain` / `hindsight_recall` tool calls, and the
bridge's own `retain` / `recall` subcommands. Those are deliberate writes and fully classified
already — do not "verify the gate" by calling them and expecting a skip.

Env knobs, read from the profile `.env` at provider init:
`JEV_GATE=0` disables the gate entirely; `JEV_GATE_TIMEOUT=<seconds>` bounds the wait (default 2.0).
`TYPESAFE_API_KEY` must be present or every path fails open.

## Thresholds and defaults

- `retain_min` = 0.55 (module constant `RETAIN_MIN_DEFAULT`)
- `recall_min` = 0.50 (`RECALL_MIN_DEFAULT`)
- `JEV_GATE_TIMEOUT` = 2.0 s
- Endpoint `https://api.typesafe.ai/v1/systemone`, model `jev-latest`

## Verification order

All subcommands take the text **positionally**. Read `build_parser()` in the bridge before
composing a call — passing `--kind` / `--text` exits rc=2 with a usage banner, which is easy to
misread as a broken bridge.

```sh
B=~/.hermes/scripts/hindsight_jev_bridge.py

# 1. Liveness + wiring (spends no Jev tokens)
python3 $B status            # url, bank, health, memories, endpoint, model, key set, circuit

# 2. Retain gate discrimination
python3 $B classify "<a durable preference>"   # expect admit >= 0.55
python3 $B classify "ok"                       # expect admit ~0.04

# 3. Store actually honours the verdict
python3 $B retain "<a durable preference>"     # expect "stored": true
python3 $B retain "ok"                         # expect "stored": false, "reason": "jev_rejected"

# 4. Recall rerank
python3 $B recall "<query about the fact>" --limit 3
#    top hit carries the exact token + a high jev score; irrelevant hits score ~0.1

# 5. Automatic-path counters (in-agent tool, not the bridge)
#    jev_gate_stats  -> retains/recalls seen, admitted, gated, jev_errors
```

## Reading a score

Calibration observed against this endpoint — use it to judge whether a gate decision is a fault
or correct behaviour:

| Band | Meaning |
|---|---|
| 0.74–0.90 | substantive query or durable preference → admit |
| 0.42–0.55 | concrete but low-value fact → correctly rejected |
| 0.08–0.40 | filler (`ok`, `thanks`, `yes`, `continue`) → correctly gated |

A recall that gets gated is therefore usually correct, not a bug. Before declaring the gate
over-suppressing, score the actual query with `query_gate()` and compare against the band table.
Long substantive questions land 0.74–0.81; conversational filler lands 0.08–0.40.

## Fail-open semantics

`_score()` returns `None` — never 0.0 — when the gate is disabled, the bridge will not import,
the key is absent, or the call raises. Every caller treats `None` as keep/admit:
`keep = score is None or score >= min`. An unreachable Jev degrades to plain Hindsight
behaviour; it never silently drops memory. So `gate: "off"` or a `jev_errors` bump means
"degraded", not "data loss".

## Pitfalls

1. **`jev_gate_stats` `gate: "enabled"` only means configured** — key present, bridge loaded, no
disable flag. It does not mean anything was admitted. Read the per-path counters for that.
2. **The store count from `status` lags one call.** A `retain` can return `stored: true` while
   `memories:` is unchanged from a moment earlier. Confirm persistence with a `recall` for the
   distinctive token, not with the counter.
3. **Counters reset per Hermes session** — they are in-process, not persisted. Zero recalls seen
   simply means no turn-prefetch has run yet in this process.
4. **The same text can be stored twice** — once carrying `jev_kind` metadata from a classified
   write and once untagged from another path. Recall then returns both variants. Not a gate
   failure; look for duplicates if the bank grows unexpectedly fast.
5. **Each gate call costs ~330–440 ms** (real Jev inference, ~900 input / ~226 output tokens).
   It runs on the serialized background worker, so it adds to write-queue time, not reply latency.
   Do not set `JEV_GATE_TIMEOUT` below the observed p95 or the gate starts failing open under load.
