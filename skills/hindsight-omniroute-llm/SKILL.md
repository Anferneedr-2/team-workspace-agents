---
name: hindsight-omniroute-llm
description: "Use when wiring the hindsight memory plugin to a custom LLM."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, memory, hindsight, llm, gateway, configuration]
    related_skills: [hermes-agent]
---

# Hindsight plugin → custom LLM gateway (e.g. OmniRoute/YanoOpenweights)

## When to Use

- Configuring or debugging the Hindsight memory provider against a custom/OpenAI-compatible
  LLM endpoint (OmniRoute, LiteLLM, local server), or the embedded daemon won't start.
- Not needed for Hindsight cloud mode or built-in MEMORY.md/USER.md.

## Config

Write `$HERMES_HOME/hindsight/config.json` (owner-only, mode 0600):

```json
{
  "mode": "local_embedded",
  "llm_provider": "openai_compatible",
  "llm_model": "<model-id>",
  "llm_base_url": "http://<host>:<port>/v1",
  "llm_api_key": "",
  "budget": "mid",
  "timeout": 120,
  "idle_timeout": 300,
  "banks": { "hermes": { "bankId": "hermes", "budget": "mid", "enabled": true } }
}
```

Keep `llm_api_key` EMPTY ("") and let it resolve through the secret scope — see
"Single source of truth for the key" below. A literal there is a second copy to rotate.

Keys are read by `_load_config()` in `plugins/hindsight/__init__.py`; `openai_compatible` maps to
`HINDSIGHT_API_LLM_PROVIDER=openai` (OpenAI wire) for the daemon. Config → daemon env is built by
`_build_embedded_profile_env()` in `plugins/hindsight/embedded.py`, written to
`~/.hindsight/profiles/<profile>.env`.

## Avoiding duplicate entries

A retain creates TWO rows when `store_document_text` and `enable_observations` are both true (the
bank default): the raw document (`type: world`, carries `document_id`) plus the observation
Hindsight extracts from it (`type: observation`, empty metadata). Same `mentioned_at`, near-tied
rerank scores — that pair is by design, not a double write.

The duplicate that grows unboundedly is a RE-RETAIN of the same content: with no `document_id`
Hindsight generates a fresh one, so the fact becomes a second document plus another observation.
Fix it in the writer, not the reader:

```python
"document_id": "jev-" + hashlib.sha256(re.sub(r"\s+", " ", text.strip().lower()).encode()).hexdigest()[:16],
"update_mode": "replace",   # replaces that document and reprocesses; never appends
```

`update_mode` accepts exactly `replace` (default) or `append` — verified on the live daemon:
three identical retains sharing one stable `document_id` leave exactly 1 entry.

Levers when the raw+observation pair itself is too much (bank config via `update_bank_config`,
NOT plugin settings — the plugin schema exposes no dedup key):

- `store_document_text: false` — drop the verbatim document, keep the distilled observations.
- `recall_include_chunks: false` — chunks also surface as near-duplicate recall rows.

## Verify (end-to-end, in this order)

1. `hermes memory status` → `Provider: hindsight` + active. If it prints `Provider: jev`, that is
   correct too — `jev` subclasses this provider and only adds an admission gate; see
   `references/jev-gate.md`. Do not revert it to `hindsight` without asking.
2. Probe: import plugin with Hermes' python (NOT system python3): path is
   `$(ls -d ~/.hermes/tools/python-*/bin/python3 | head -1)`, needs `PYTHONPATH` intact (the
   `agent` module lives there) and `sys.path.insert(0, ~/.hermes/plugins)`.
3. `_check_local_runtime().available` must be True; then `_start_daemon(_build_embedded_profile_env(cfg), "hermes")`
   → returns `http://127.0.0.1:<port>`; `GET /health` → `{"status":"healthy","database":"connected"}`.
   NOTE: `_daemon_is_running(cfg)` can return False even when healthy — trust `/health`, not the bool.
4. LLM proof: `hindsight_client.Hindsight(base_url=...)` → `await h.aretain(bank, "<fact>", tags=[...])`
   (retention runs real LLM extraction — check `usage` tokens) → `await h.arecall(bank, "<query>")`
   returns the normalized fact. Confirm daemon env with
   `ps eww $(pgrep -f bin/hindsight-api) | grep HINDSIGHT_API_LLM`.

## Pitfalls (all hit on 2026-11-03, each = a distinct failure layer)

1. **Deps missing**: plugin's `pyproject.toml` deps are NOT auto-installed on an existing install.
   Symptom: `ModuleNotFoundError: hindsight_client` / `hindsight_embed`, or
   `No module named 'rich'` (hindsight-embed imports rich) from the daemon-start child.
   Fix: `pip install hindsight-client hindsight-embed rich` into Hermes' python.
   `hermes plugins update <name>` does NOT re-apply deps when already at catalog pin.
2. **uvx not on PATH**: Hermes' PATH includes every `~/.hermes/tools/*` dir EXCEPT `uv-*`.
   The plugin's `_managed_uvx_dir` workaround only fires on the clean-child path; with
   hindsight-embed > 0.10.2 `_embed_scrubs_parent_env()` is True → in-process path → no workaround.
   Symptom: rich box `Command not found: uvx` / `uvx hindsight-api@<ver>`.
   Fix: symlink BOTH `uv` and `uvx` (uvx dispatches on argv[0] and needs `uv` beside it) into
   `~/.hermes/hermes-agent/.hermes/bin/` (on PATH).
3. **First-run 180s timeout**: provisioning (torch 132MB etc.) exceeds the manager's health window.
   Symptom: `Daemon failed to start (timeout)` at ~180s with download lines in
   `~/.hindsight/profiles/hermes.log`. Fix: pre-warm `uvx hindsight-api@<ver> --help` once
   (takes ~2-3min; run via terminal tool, execute_code caps at 300s).
4. **pg0 needs openssl@3**: embedded Postgres (pg0) links
   `/opt/homebrew/opt/openssl@3/lib/libssl.3.dylib`. Symptom: `Application startup failed`, exit 3,
   dylib-not-found in `~/.hindsight/profiles/hermes.log`. Fix: `brew install openssl@3`.
5. **Bridge/CLI subcommands take positional text**: `hindsight_jev_bridge.py classify "<text>"`,
   NOT `--kind` / `--text`. Guessing flags exits rc=2 with a usage banner that reads like the
   script is broken. Read `build_parser()` first before composing a call.

## Verifying the Jev gate

When `memory.provider: jev`, the gate sits in front of the automatic retain/recall paths and needs
its own verification — the daemon being healthy says nothing about whether admission works.
Full runbook, score-band calibration, fail-open semantics and pitfalls:
`references/jev-gate.md`. Minimum check: `hindsight_jev_bridge.py status` (wiring), then
`classify` a durable preference vs `"ok"` (expect ~0.9 vs ~0.04), then `retain` both and confirm
`stored: true` / `reason: jev_rejected`, then `recall` and confirm the top hit carries a high
`jev` score while irrelevant hits sit near 0.1.

## Single source of truth for the key (no literal copies)

The plugin has NO `${VAR}` expansion: `llm_api_key` in config.json is a literal, and
`_embedded_llm_api_key()` resolves config → secret scope `HINDSIGHT_API_LLM_API_KEY` →
profile env. The scope path (`load_env_file`) does NOT expand `${VAR}` — only `env_loader`
does — so `${VAR}` indirection breaks under a bound (multiplex) scope.

Working approach: a **`secrets.command` external secret source** re-exports the key under the
name the plugin expects. It hydrates BOTH `os.environ` and the per-profile scope with RESOLVED
values, so the plugin resolves it with no literal anywhere.

```sh
# ~/.hermes/scripts/omniroute-secret-helper.sh   (chmod 700)
ENV_FILE="${HERMES_HOME:-$HOME/.hermes}/.env"
[ -r "$ENV_FILE" ] || exit 0
value=$(grep -m1 '^OMNIROUTE_API_KEY=' "$ENV_FILE" | cut -d= -f2-)
[ -n "$value" ] || exit 0
printf 'HINDSIGHT_API_LLM_API_KEY=%s\n' "$value"
```

```bash
hermes config set secrets.command.enabled true
hermes config set secrets.command.command "/Users/robi/.hermes/scripts/omniroute-secret-helper.sh"
hermes config set secrets.command.helper_timeout_seconds 3
hermes config set secrets.command.override_existing false
```

Then blank `llm_api_key` in config.json (`""`) — the plugin falls through to the scope.
`hermes config set` is the sanctioned way to edit config.yaml; the `patch`/`write_file` tools
REFUSE to write `~/.hermes/config.yaml` (security guard).

Verify: `ps eww $(pgrep -f bin/hindsight-api) | grep HINDSIGHT_API_LLM_API_KEY` → set (1 line).

## Notes

- `_start_daemon(config, profile)`: first arg is the HINDSIGHT_* **env dict** from
  `_build_embedded_profile_env(cfg)` (plus idle-timeout key), NOT the raw config.json dict.
- Config loads at provider init → **restart Hermes** after editing config.json.
- API key precedence: config `llm_api_key` → secret scope `HINDSIGHT_API_LLM_API_KEY` → profile env.
- Daemon idle-stops after `idle_timeout` (300s); restarts on demand in ~16s once env is warm.
- The plugin's own setup wizard writes `HINDSIGHT_LLM_API_KEY` into `~/.hermes/.env` — a second
  name for the same key. Prefer the external-source pattern above over a literal.
- The helper's `HERMES_HOME` override makes rotation testable in a sandbox.
- A `jev` plugin (admission gate wrapping Hindsight) may be the ACTIVE provider instead of
  `hindsight` — `hermes memory status` then prints `Provider: jev`. It loads the Hindsight
  provider class from `plugins/hindsight/__init__.py`, so all of this config still applies to it.
  Don't "fix" that back to `hindsight` without asking.
- Rotating the key in `.env` needs a Hermes restart: the daemon's env is materialized at start.