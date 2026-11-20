# Requirements for creating an agent (bot)

How the remote Mac Mini ("Agentic Team Alpha", workspace v1.3) creates an agent, as a checklist. Source: the remote's hub README (sections 2, 3, 3.6, 3.7), its AGENTS.md, `governance.yaml`, `Governor/validate_governance.py`, and the real profile files copied from it.

> **Fresh start (2026-11-10).** The old team bots and the governance generator are gone. On this Mac an agent is now organized by `CONVENTIONS.md` and the scripts in `bin/`: `create_agent.py` (build, `--update`, `--retire`), `check_agent.py` (checks and scenario tests) and `registry.py` (the register `registry.yaml`). Section 3 below describes how the remote did registration; here the register replaces it. `agent-creator` runs the whole process.

An agent is a **Hermes profile**. It is not finished when the profile exists. It is finished when it is registered, scoped, logged and verified.

---

## 0. Hermes requirements (the platform must be ready before any agent)

Checked on both Macs unless marked otherwise.

**Install and runtime**
- [ ] Hermes Agent installed from git at `~/.hermes/hermes-agent` (remote v0.22.7, this Mac v0.22.6), with its own managed Python 3.14 under `~/.hermes/tools/`, and the `hermes` command on the PATH (`~/.local/bin/hermes`).
- [ ] Config schema current (`_config_version: 52`) and `hermes doctor` shows no failures. Warnings about npm audit, optional Docker, Discord and other sign-in providers are fine.
- [ ] Tool chain present: `git` and `ripgrep`, plus Node + npm, ffmpeg, Chromium (browser tool), Playwright, agent-browser and the computer-use driver in `~/.hermes/tools/`. Docker is optional.
- [ ] macOS permissions: Full Disk Access for Hermes (`hermes doctor` checks it, so there are no per-folder prompts) and the Screen Recording permission if the bot uses computer use.

**Model access**
- [ ] A model provider with working credentials. Remote: a custom OpenAI-compatible endpoint (`provider: custom`, `base_url`, and the **name** of the key variable, `OMNIROUTE_API_KEY`, set in `.env`). This Mac: an Anthropic login stored in `auth.json`. The doctor line "API key or custom endpoint configured" must be ✓.
- [ ] A network path to the model host (remote: Tailscale to `yano:20128`).
- [ ] Credentials live only in `.env`, `auth.json` or the Keychain. Never in `config.yaml` or docs, and never copied from one profile to another.

**Gateway and messaging**
- [ ] The gateway is running (launchd-managed `hermes gateway run`) and serves all profiles. A new profile must appear in `served_profiles` in `~/.hermes/gateway_state.json`.
- [ ] Messaging only for bots that talk to you. Telegram needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS` in that profile's `.env`. The API server needs `API_SERVER_ENABLED` and `API_SERVER_KEY`.

**Toolsets** (the same config on both Macs): web, browser, terminal, file, code_execution, vision, image_gen, tts, skills, todo, connections, clarify, session_search, delegation, cronjob, computer_use. Web search needs a search provider key (remote: Perplexity).

**Plugins and memory**
- [ ] The memory plugin is installed with its dependencies for that profile: `hermes -p <slug> plugins install <name> --yes-deps --enable`. Holographic needs `numpy` and `snowballstemmer` and no key. Hindsight needs `uv`/`uvx`, an embedded Postgres and a model key (not installed on this Mac).
- [ ] `hermes -p <slug> memory status` shows the provider.

**Scheduling** (only if the bot has cron): the script must be a real file inside that profile's `scripts/` folder (symlinks are rejected). Create with `hermes -p <slug> cron create "<cron>" --name <name> --no-agent --script <file> --interpreter <python> --timezone Asia/Manila --deliver local`.

**Learned the hard way**
- `hermes plugins install` without `-p <slug>` installs into the **active** profile (here `executive-assistant`). Always pass `-p`.
- Don't use `--clone` or `--clone-all` for a new bot: they copy `.env`.
- `hermes profile create` needs `--description`. A plugin install rewrites `config.yaml`, so re-check that `terminal.cwd` survived.
- One-shot `hermes -p <slug> -z` ignores `terminal.cwd`: always pass `--in`.
- A non-interactive plugin install needs `--yes-deps`.

---

## 1. Decide first (write these down before creating anything)

- [ ] **Role.** One job only. Never give one bot two jobs.
- [ ] **Level.** Top-level (workspace-wide) or project-scoped (one client only).
- [ ] **Slug.** Lowercase, hyphens allowed. Top-level bots use a fixed role slug (`memory-manager`). Project bots use `<slugbase>-<role>` (`clinicconnects-document-engineer`). The slug base is recorded explicitly, taken from the project orchestrator's folder, and never recomputed by lowercasing the folder name.
- [ ] **Reports to.** Which bot it answers to. Project bots report to `<slugbase>-orchestrator`, and orchestrators report to `project-orchestrator`.
- [ ] **Scope folder.** The one folder it works in. Top-level bots: the workspace root. Project bots: their project folder.
- [ ] **Write scope.** What it may write. A project bot writes only inside its own project.
- [ ] **Skills.** Which approved skills it needs. At minimum `task-changelog`.
- [ ] **Tools and schedule.** Whether it needs cron. Only `governor` has cron on the remote.
- [ ] **Secrets.** Whether it needs a credential, and under what Keychain name.
- [ ] **Memory scope.** Its own memory only. Cross-project facts belong to the top-level `memory-manager`.

## 2. Create the profile

- [ ] `hermes profile list` (confirm the name is free).
- [ ] `hermes profile create <slug> --description "<one-paragraph role description>"`. The description goes in `profile.yaml`. It is how routing finds the bot, because the profile description is what decides which bot gets a task.
- [ ] **`config.yaml` is thin** (about 10 lines):
  - `model`: `default`, `provider`, `base_url`, `key_env` (the env var name only, never the key)
  - `_config_version: 52`
  - `terminal.cwd`: the scope folder
  - `memory.provider`: the memory plugin
- [ ] **`SOUL.md`** is the shared generic persona text. The role lives in `profile.yaml`, the scope folder and the governance files, not in a long SOUL.
- [ ] **No `.env` copied** from another bot. No credentials in the profile.
- [ ] **Alias.** A wrapper script in `~/.local/bin` (created by `hermes profile create`), so `<slug>` runs the bot.
- [ ] **Skills installed** into the profile, including `task-changelog`.
- [ ] **Memory plugin installed** and enabled. The remote uses `hindsight` + `jev` with `memory.provider: jev`.
- [ ] **Seeded `memories/MEMORY.md`** stating its scope and its logging duty.
- [ ] **Served by the gateway.** The bot must be served by the running Hermes gateway before it is used.

## 3. Register it (an unregistered profile is a governance violation)

- [ ] **`governance.yaml`** lists it: role, scope, `reports_to`, write scope, read scope, cron eligibility. This file is **generated** by `Governor/build_governance.py` from the live profiles. Never hand-edit it.
- [ ] **`skills.yaml`** lists every skill it uses, once, with a sha256 hash and the bot in `granted_to`. A new skill is reviewed, hashed, added to the approved list, then governance is rebuilt. No dynamic installs.
- [ ] **Project projection.** A project bot also appears in `<Project>/governance.yaml` (generated).
- [ ] **`AGENTS.md`** (workspace and project) lists the bot in its bot table.
- [ ] **Hub README** roster row filled in (real slug, model, gateway status, date). Update `Status` and `Last updated`, and mirror the change in the Obsidian entry.
- [ ] **CHANGELOG entry** before its first task: `- [YYYY-MM-DD] [actor] what changed — detail`.
- [ ] **Lock.** `validate_governance.py --write-lock`, only after a human approves. Governor memos ask for that approval.

## 4. Rules the agent works under

- [ ] **Handoff only by** `hermes -p <slug> --in <scope-dir> -z "<task>"`. Always pass `--in`, because one-shot commands ignore `terminal.cwd`.
- [ ] **Isolation.** A project bot never reads another project's folder, docs, Jira log or memory. Cross-project work goes up to the top-level bot for that role.
- [ ] **Every finished task** appends one entry to the right `CHANGELOG.md` (workspace or project) using the `task-changelog` skill.
- [ ] **Secrets** are macOS Keychain references only, in the form `keychain:agentic-team-alpha/<profile>/<name>`. No value is ever stored in a file.
- [ ] **Schedule policy** if it has cron: at most one model-backed job at a time, a 10-minute gap, quiet hours 00:00-06:00 PHT, and deterministic scans run `--no-agent`.
- [ ] **Time** is recorded through `bundy` (no overlapping entries across projects).

## 5. Verify before calling it done

- [ ] `validate_governance.py` reports **PASS** (no unregistered profile, `reports_to` chain resolves, folder scope matches `terminal.cwd`, memory provider set, skill hashes match, no plaintext credentials).
- [ ] `hermes doctor` has no failures, and `hermes -p <slug> memory status` shows the memory provider.
- [ ] **Smoke test:** run it once with a handoff using `--in <scope-dir>`. It should state its role and stay in its folder.
- [ ] Its `config.yaml` shows the correct `terminal.cwd`, and its folder contains no credential values.
- [ ] The CHANGELOG entry exists, and the roster row is updated.

---

## What was different on this Mac

| Remote Mac Mini | This Mac |
|---|---|
| Model `yano-openweights` through the yano gateway | Claude (`claude-haiku-5-5`, provider `anthropic`) |
| Memory: Hindsight + `jev` | Memory: local `holographic` (no model key needed) |
| Every project had a Jira admin bot | Jira is optional: `Agents/bin/enable_jira.py <Project>` |

Scripts here that do steps 2 and 3 for you: `Agents/bin/new_client.py` (a client's three bots) and `Agents/bin/hire_agent.py` (a specialist for one client).

---

## 6. After the build: connect, verify, hand over, review (end to end)

A helper is not finished when it exists. The full journey is the 10 stages in `skills/agent-lifecycle`:

1. Discover, 2. Shape, 3. Brief and approval, 4. Pre-build check, 5. Build, **6. Connect tools**, **7. Verify**, **8. Hand over**, **9. First real use**, **10. Review**.

- [ ] **Connect tools** (only with a separate OK): built-in toolsets limited with `toolsets_off`; outside tools through MCP in the agent's own `config.yaml`, read-only first, an include list, secrets as `${VAR}` from its `.env` (Robi stores the key himself, never in chat); checked with `hermes -p <slug> mcp test <server>` and one harmless read.
- [ ] **Verify:** `check_agent.py <slug> --scenarios` shows no FAIL. It checks the folder and records, naming, config, memory limits, skills, cost, tools really off, connections, gateway, and secrets, then runs read-only scenario tests (intro, normal, edge, boundary, scope, tool).
- [ ] **Hand over:** the "How to use your helper" card (what it is for, where to find it, how to ask, what it asks first, where its work lands, how to correct it, how to check on it, review date).
- [ ] **First real use:** one real task with Robi. Only a clear yes allows `registry.py set-status <slug> production --approved`.
- [ ] **Review:** after three real tasks or seven days, then monthly. Changes go through an updated brief and `create_agent.py --update` (backs up first). Retire with `--retire`.

## 7. What the official Hermes docs add

From https://hermes-agent.nousresearch.com/docs (checked against this install; details in `skills/hermes-reference`):

- **Instructions:** `SOUL.md` is the agent's identity and tone and loads from its profile; `AGENTS.md` carries rules for a folder and loads from the working folder, so one-shot runs need `--in`. Both are read on every message, so keep them short.
- **Memory:** `MEMORY.md` is limited to 2,200 characters and `USER.md` to 1,375. Memory is per profile.
- **Skills:** `SKILL.md` with frontmatter (`name`, `description` saying when to use it), body under about 24,000 characters, loaded on demand. Lean agents use `--no-skills`.
- **Tools:** least privilege through `agent.disabled_toolsets`. MCP servers add `mcp_<server>_<tool>` tools; filter with include/exclude lists.
- **Security:** `approvals.mode` stays `smart` or `manual`; one-shot runs, timers and API sessions cannot ask anyone, so risky commands are denied there; `approvals.deny` blocks patterns; on this Mac a folder limit is a rule, not a wall.
- **Reaching it:** Hermes app Bots list, terminal, another agent with `--in`, or Telegram (needs a token and an allowlist, locked by default).
- **Verifying:** `hermes doctor`, `status`, `config check`, `prompt-size`, `tools list`, `mcp test`, `logs`, `sessions list`, `memory status`, and `hermes -z` exit codes (0 ok, 2 failed or partial, 130 interrupted, 1 no text).
