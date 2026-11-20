---
name: agent-memory-layer
description: "Build a shared memory layer for agents."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [memory, memory-provider, sqlite, fts5, mcp, sidecar, jev, typesafe]
    related_skills: [hermes-agent, hindsight-omniroute-llm]
---

# Agent Memory Layer

**On this machine the store is Hindsight. Do not add a second database or a daemon.** Put the decision model in one maintainable bridge script that calls Hindsight's public HTTP API (retain/recall) and Jev's System One API. Never patch or import private internals of `~/.hermes/plugins/hindsight` — plugin updates overwrite them. A SQLite sidecar is the fallback design below, justified only when Hindsight cannot meet a hard requirement and the user explicitly asks for it. See `references/hindsight-bridge.md` for this machine's exact bridge commands.

## Compiled layer: knowledge-base pages, not a second wiki

Hindsight already ships the compiled tier. `/v1/default/banks/{bank}/knowledge-base/{tree,folders,pages,search,export}`
gives folders, pages, hybrid BM25+vector search and a markdown export of the whole KB. A page is a
*saved query*, not a document: `name` + `source_query` + `tags` that SCOPE which memories feed it,
rendered by the server's own LLM. Mental models are the same idea with explicit refresh triggers.

Consequence: Karpathy-style wiki output (`llm-wiki` skill) is a **projection**. Compile pages from the
memory store, then `GET .../knowledge-base/export` into the vault for git, humans and agents that have
no MCP client. Never hand-write a parallel wiki directory and call it the knowledge base.

Routing rule: Jev's `kind` and `domain` are the facet tags pages scope on. `kind:constraint`,
`kind:procedure`, `kind:entity` compile to pages; `transient` never does; `sensitivity:secret` never
leaves the store and never exports. API detail, scoping rules and the probe recipe:
`references/hindsight-kb-pages.md`.

- **Page `tags` scope with `all_strict`.** Every tag must be present on the memory and untagged
  memories are excluded, so a topic tag no memory carries renders an empty page that looks like a
  rendering bug.
- **The automatic gate path drops the facets.** `plugins/jev` calls `super().sync_turn(...)` with no
  tags, so per-turn memories carry only `session:<hash>`; the bridge's explicit `retain` is the only
  writer of `kind:`/`domain:`. Annotate before delegating if pages must scope on them.
- **Tag backfill is unproven.** Provider `update_memory` cannot add tags; verify HTTP
  `PATCH /memories/{id}` accepts them before promising a backfill job.
- **Page rendering costs a server LLM call.** Refresh on a memory-count delta, never per write.

## This machine's layout (2026-11)

- **Explicit commands** → `python3 ~/.hermes/scripts/hindsight_jev_bridge.py {status,classify,retain,recall}` (stdlib, one-shot).
- **Automatic retain/recall** → `~/.hermes/plugins/jev/` — a provider that SUBCLASSES `HindsightMemoryProvider` and overrides only `sync_turn`, `queue_prefetch`, `prefetch` (Hindsight's opt-in recall_sync mode only) and `on_memory_write`. Tools, config schema, prompt block, session hooks and shutdown are inherited, so a Hindsight update only matters if one of those four signatures changes. The base class is resolved by reusing the module the loader already imported — never import a second copy when the first is in `sys.modules`.
- The gate fails OPEN: missing key, slow Jev or an unreadable bridge degrades to plain Hindsight. `JEV_GATE=0` disables it, `JEV_GATE_TIMEOUT=2` bounds it, `JEV_GATE_DEBUG=1` appends one line per decision to `~/.hermes/cache/scratch/jev_gate_debug.log` — CLI-side only: agent turns do not inherit that variable, so read per-turn counters from the `jev_gate_stats` tool (or grep `Jev gate:` in `~/.hermes/logs/agent.log` with `HERMES_LOG_LEVEL=DEBUG`).
- Probe a gate change outside a chat session first: load with `plugins.memory.load_memory_provider("jev")`, call `initialize(session_id, hermes_home=...)`, exercise `sync_turn`/`queue_prefetch`/`on_memory_write`, then read the `jev_gate_stats` tool. Import `hermes_bootstrap` before anything under `hermes-agent`, or the plugin's packages are not on `sys.path`.

Build a local-first memory service that Hermes and every other agent on the machine can share. A remote decision model (TypeSafe Jev or equivalent) decides what to keep and how to rank it; the agent never blocks on memory.

## When to use

- Replacing or augmenting a memory provider without destroying the old one.
- Several agents (Hermes, Claude Code, Codex, OpenCode, scripts) need one shared store.
- Memory needs admission, schema/kind classification, tagging, contradiction handling, and recall reranking — not just embeddings.
- Recall or retain latency, database growth, or background-process hygiene is part of the acceptance criteria.

## Architecture

| Layer | Responsibility | Default |
|---|---|---|
| Decision model | admit, kind, importance, domain, sensitivity, tags, supersede, rerank | TypeSafe Jev System One |
| Store | durable rows + keyword candidates | SQLite WAL + FTS5 |
| Transport | local HTTP for any client | loopback `127.0.0.1` |
| Agent protocol | tools for MCP clients | stdio JSON-RPC 2.0 |
| Hermes adapter | lifecycle hooks + tools | native `MemoryProvider` plugin |
| Process | on-demand, single instance, idle exit | short-lived spawn helper |

Do not put the model in the request path as a hard dependency. It is an advisor with a deadline; the store and a deterministic fallback must answer when it is slow or down.

## Procedure

### 1. Inventory and preserve the current provider

```bash
hermes memory status
hermes config get memory.provider
```

Record the active provider and leave its plugin, config, and bank untouched. Activation is one config line; rollback must stay one config line. Do not migrate or delete old memories unless the user explicitly asks.

### 2. Define the decision contract before writing code

One request per write and one per recall, never one per question. Batch all questions into a single `questions` map:

- `remember` — `noul`, admission threshold.
- `kind` — `choice`, closed set from `schema.json`.
- `importance` — `score`, normalized to 0–1.
- `domain` / `sensitivity` — `choice`.
- `tag_<name>` — `noul` only for tags matched locally.
- `supersede_<n>` — `noul` against the nearest existing memories.
- `rel_<n>` — `noul` for recall candidates.

Send the state once (`{text, existing}`), cache the whole payload, and keep thresholds in config so they can be tuned without code changes.

### 3. Build the store

Minimum tables: `memories`, `memories_fts`, `decisions`, `decision_cache`, `meta`.

- `status`: `active` | `superseded` | `deleted`; exclude non-active from recall.
- `uid` stable and short; `content_hash` unique per namespace for exact dedupe.
- FTS5 with porter/unicode61; rank with `bm25(memories_fts, 1.0, 0.5, 2.0, 1.5)`.
- A controlled `schema.json` for kinds, domains, and tags. Validate writes against it; return rejected tags instead of silently dropping them.
- Namespaces: owner namespace plus `shared`; lowercase, `[a-z0-9:_-]`, max 64 characters.

### 4. Build the daemon

Expose at least `/health`, `/v1/retain`, `/v1/retain_async`, `/v1/recall`, `/v1/classify`, `/v1/forget`, `/v1/feedback`, `/v1/stats`, `/v1/reload`, `/v1/prune`, `/v1/shutdown`.

- Bind loopback; optional bearer token for non-loopback use.
- One `fcntl.flock` instance lock; a second instance exits 0.
- One writer queue and one writer thread; explicit `remember` is synchronous, turn capture is async.
- Hard deadlines on every model call, a circuit breaker, a content-hash cache, and deterministic local scoring as fallback.
- Idle exit only when the queue is empty and no request has arrived for the timeout.
- Startup prune of tombstones and old decisions.

Use `references/sidecar-daemon.md` for the lock, spawn, idle-exit, WAL, and timeout recipes.

### 5. Build the clients

- **MCP stdio** for other agents: newline-delimited JSON-RPC 2.0, protocol `2024-11-05`, no SDK dependency, exits on stdin EOF. Tools: `memory_retain`, `memory_recall`, `memory_classify`, `memory_forget`, `memory_feedback`, `memory_stats`.
- **Hermes provider**: `~/.hermes/plugins/<name>/` with `plugin.yaml`, `__init__.py`, optional `config_schema.py`. See `hermes-agent` → `references/memory-provider-plugins.md`.
- **CLI**: `start`, `stop`, `status`, `reload`, `prune`, `logs`, `doctor` so operations do not require hand-written HTTP.

### 6. Test before activation

```bash
python3 -m py_compile *.py
python3 test_jev_contract.py     # mock of the real API shape, no key
python3 test_layer.py            # isolated lifecycle, MCP, latency, idle exit
python3 test_layer.py --live     # real key from ~/.hermes/.env
```

Use `references/testing-memory-layer.md` for the mock contract server, isolated harness, stress methodology, and Python-version pitfalls. Do not switch providers until the live classify/retain/recall path passes.

### 7. Activate with a rollback

```bash
hermes config set memory.provider <name>
# restart Hermes or start a new session
hermes memory status

# rollback
hermes config set memory.provider <old-name>
```

Keep the old provider installed. If the new layer is empty, say so before switching; switching silently changes what the user's agent remembers. Do not delete the old bank or database as part of the trial.

### 8. Document the key and operations

- Decision API key: `~/.hermes/.env`, `TYPESAFE_API_KEY=...`; the daemon reads the file, the agent process never sees the value.
- No key: the layer must still work in heuristic mode; report `jev_configured=false`, not a crash.
- Directory `700`, DB/config/log `600`; reapply permissions after recreating the DB.
- No launchd/systemd job by default: start on demand from the client and let idle exit clean up.

## Pitfalls

- **Never switch `memory.provider` before the live decision call passes.** A green offline suite only proves the fallback; switching first silently downgrades recall and hides a bad API contract. Keep the old provider one command away.
- **A wrapper provider must declare the wrapped plugin's packages in its own `pyproject.toml`.** The package manager installs members for enabled plugins plus the active `memory.provider` and evicts the rest, so switching the provider to a wrapper that declares nothing removes the original plugin's runtime; the inherited `is_available()` then returns False and `agent_init` drops the provider, with only `hermes memory status` noticing. Symptom: `Status: not available ✗` plus "run 'hermes pm repair'". Fix: mirror the wrapped plugin's `dependencies` (same version bounds) in the wrapper's `pyproject.toml`, then `hermes pm lock` and `hermes pm install`.
- **`hermes plugins info <name>` may answer from the curated catalog, not your local dir.** The catalog ships its own plugin named `jev` (`ourines/hermes-jev`, tool `jev_evaluate`), so a hand-made `~/.hermes/plugins/jev/` can be confused with it or clobbered by `hermes plugins install jev`. Adopt the dir (`hermes plugins adopt <name>`) or use a name the catalog does not claim.
- **The key goes in `~/.hermes/.env`, never in `config.json` or code.** A plain `python3 test.py` does not inherit Hermes's environment; load `.env` explicitly in live tests or the key is silently skipped.
- **One model request per operation, not one per question.** Per-question calls multiply cost and latency and make the circuit breaker trip sooner.
- **Every model call needs a hard deadline and a fallback.** A memory lookup must never turn an agent turn into a timeout.
- **One writer thread and one SQLite connection per request.** Concurrent writers plus an unbounded queue cause lock contention and WAL growth; `wal_autocheckpoint=256` keeps the WAL bounded.
- **Spawn through a short-lived launcher, not as a direct child of the agent.** `start_new_session=True`, `close_fds=True`, then the launcher exits; the daemon is reparented to init/launchd, so a long-lived agent never accumulates a `<defunct>` child.
- **The single-instance lock is non-negotiable.** A second daemon must exit 0 instead of double-binding the port or opening a second writer.
- **Idle exit requires an empty queue.** Check both the last request time and queue depth, or a queued retain is lost.
- **Supersede, don't delete.** Mark contradicted rows `superseded`, exclude them from recall, and prune tombstones after a retention window.
- **Validate tags against `schema.json`.** Free-form tags drift; return `tags_rejected` rather than storing whatever the model produced.
- **Sanitize namespaces and always read `shared`.** A typo otherwise creates a silent memory island that no other agent can see.
- **`prefetch` swallows every error and returns `""`; `handle_tool_call` returns `tool_error`.** The agent loop must never see a traceback because memory is down.
- **Use the Hermes Python for provider imports.** The system `python3` may be 3.9 while Hermes runs 3.14; a runtime `str | object` expression raises `TypeError` on 3.9 even with `from __future__ import annotations`. `from __future__` postpones annotations only, not evaluated expressions.
- **`with sqlite3.connect(...)` commits but does not close.** Use `try/finally` or `contextlib.closing`, especially on the startup path.
- **Stress with distinct vocabulary.** Near-duplicate Jaccard correctly collapses “same sentence with a different number” into one row; that is dedupe, not a database-growth test. Use random distinct words and count active rows.
- **Never point a test at the production DB.** Use a temp home, a free port, and `finally` cleanup; stop the daemon before deleting WAL files.

## Verification checklist

- [ ] `curl -s http://127.0.0.1:<port>/health` returns `ok` and the expected model.
- [ ] `python3 jevmemctl.py doctor` reports the key as set when configured.
- [ ] Mock contract tests pass: auth header, model, state, question types, answer parsing, cache hit.
- [ ] Lifecycle tests pass: second instance exits, no zombie, no zombie children, idle exit, no orphan, degraded path under 1s.
- [ ] 300 distinct writes stay under ~1 MB and p95 retain/recall stay in single-digit milliseconds on the heuristic path.
- [ ] Provider `prefetch` returns a bullet list; `handle_tool_call` returns a tool error when the daemon is down.
- [ ] `hermes memory status` shows the old provider active until the explicit switch.

## References

- `references/hindsight-kb-pages.md` — knowledge-base page/folder/export/search API, `all_strict` page scoping, observed bank tags/entities, probe recipe.
- `references/jev-system-one.md` — TypeSafe Jev endpoint, request/response shape, question types, pricing, failure handling.
- `references/sidecar-daemon.md` — single-instance lock, reparenting spawn, idle exit, WAL/FTS5, queue, timeouts, circuit breaker.
- `references/testing-memory-layer.md` — mock contract test, isolated lifecycle harness, stress methodology, Python-version and `.env` pitfalls.
- Hermes plugin wiring: `hermes-agent` → `references/memory-provider-plugins.md`.
