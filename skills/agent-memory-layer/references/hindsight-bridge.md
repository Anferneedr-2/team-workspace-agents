# Hindsight + Jev bridge (this machine)

Hindsight is the provider and the store. Jev is the decision layer. There is no second database and no background service.

| Piece | Value |
|---|---|
| Provider | `hindsight` (`hermes memory status` → Provider: hindsight) |
| Bank | `hermes` |
| Hindsight API | `http://127.0.0.1:9177` (local embedded; probe `/health`) |
| Bridge | `~/.hermes/scripts/hindsight_jev_bridge.py` |
| Automatic-path gate | `~/.hermes/plugins/jev/` (`memory.provider=jev`) |
| Jev key | `~/.hermes/.env` → `TYPESAFE_API_KEY` |

## Commands

```bash
python3 ~/.hermes/scripts/hindsight_jev_bridge.py status
python3 ~/.hermes/scripts/hindsight_jev_bridge.py classify "text"
python3 ~/.hermes/scripts/hindsight_jev_bridge.py retain "text" --context "why it matters"
python3 ~/.hermes/scripts/hindsight_jev_bridge.py recall "query" --limit 5
python3 ~/.hermes/scripts/hindsight_jev_bridge.py recall "query" --json
```

`retain` asks Jev for admission, kind, importance, domain, sensitivity and tags, then writes to Hindsight with those tags and metadata. `recall` fetches Hindsight candidates and reranks them with Jev (65% Jev relevance, 35% Hindsight score). `secret`-tagged results are hidden unless `--include-secret`.

## Rules

- Do not edit `~/.hermes/plugins/hindsight/__init__.py`. It is a catalog install and updates replace it.
- Do not rebuild the SQLite `jevmemd` sidecar; it was removed on 2026-11-03 because Hindsight already stores the memories.
- **Both paths are gated.** The bridge covers explicit retain/recall from any agent; `memory.provider=jev` puts the same Jev admission in front of Hermes's automatic `sync_turn`/`queue_prefetch`/`on_memory_write`. The gate provider subclasses `HindsightMemoryProvider`, so the store, tools and config are still Hindsight's.
- The gate fails OPEN (missing key, slow Jev or an unreadable bridge → plain Hindsight). Turn it off with `JEV_GATE=0`; `JEV_GATE_DEBUG=1` logs one line per decision to `~/.hermes/cache/scratch/jev_gate_debug.log`; counters are exposed by the `jev_gate_stats` tool.
- The wrapper declares `hindsight-client`/`hindsight-embed` in `~/.hermes/plugins/jev/pyproject.toml`: the package manager evicts the inactive provider's packages, and without them `is_available()` is False and the provider is dropped.
- Hindsight `update_memory` cannot add tags or metadata, so do not plan a post-hoc tagger. Tags must be supplied at retain time, which is what the bridge does.
