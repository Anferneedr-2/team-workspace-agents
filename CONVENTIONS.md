# How agents are organized (backend conventions)

Taken from how the remote Mac Mini is organized (hub README sections 2, 3 and 3.6, AGENTS.md, governance), adapted for the fresh start on this Mac. `agent-creator` follows this on every build, and `bin/check_agent.py` checks it.

## 1. Two kinds of placement

| Placement | Works in | Slug | Example |
|---|---|---|---|
| **Client agent** | that client's folder, `Team-Workspace/<Client>/` | `<slugbase>-<role>` | `simplysource-onboarding-chaser` |
| **Team agent** | its own team folder at the workspace root, like `Governor/`, `Bundy/`, `Agents/` | `<role>` | `agent-creator` (folder `Agents/`) |

- The **slug base** of each client is recorded in `registry.yaml` under `clients:` and never recomputed (`CliniConnects` is `clinicconnects`).
- Names are lowercase letters, numbers and hyphens. **One job per agent.** Never give one agent two jobs.
- A client agent never reads or writes another client's folder. Work that crosses clients goes to a team agent.

## 2. Everything an agent has (no exceptions)

| Piece | Where | Made by |
|---|---|---|
| Hermes profile | `~/.hermes/profiles/<slug>/` (+ alias in `~/.local/bin/`) | `create_agent.py` |
| Agent Brief (approved) | `Agents/briefs/<slug-or-name>.md` | `agent-creator` |
| Registry entry | `Agents/registry.yaml` (readable copy: `Agents/REGISTRY.md`) | `create_agent.py` |
| Home folder with `README.md`, `AGENTS.md`, `CHANGELOG.md` | the placement folder | `create_agent.py` |
| Listed in its folder's README | managed block `<!-- agents:start -->` | `registry.py sync` |
| Change log entries | the folder's `CHANGELOG.md` **and** `Team-Workspace/CHANGELOG.md` | `create_agent.py` |
| Test report | `Agents/briefs/<slug>-test-report.md` | `check_agent.py` |

## 3. Client folder layout

`Memory/ Work/ Deliverables/ Marketing/ Research/ Data/ Assets/ Sources/` plus `README.md`, `AGENTS.md`, `CHANGELOG.md`. Agents put drafts in `Work/`. Approved, client-ready files go to `Deliverables/` only after Robi approves. `Sources/` holds symlinks to existing repos; the repo stays where it is.

## 4. Instruction files (from the Hermes docs)

- `SOUL.md` (in the profile): who the agent is, tone, how it handles doubt, its job and limits. Kept short.
- `AGENTS.md` (in the home folder): rules for the work in that folder. Loaded when the agent runs from that folder, so one-shot runs must pass `--in <folder>`.
- Keep both concise: they are read on every message.

## 5. Status lifecycle

`testing` → `production` → `retired`.

- Every agent **starts as `testing`**. It moves to `production` only after Robi approves a correct real result.
- `retired` agents keep their registry row and brief (history) but the profile is deleted.
- Anything on the Mac that is not in the registry is listed as **not yet following the requirements** until it is brought in or removed.

## 6. Change control

- Every creation, update, review result and retirement writes one line to the folder `CHANGELOG.md` and to `Team-Workspace/CHANGELOG.md`: `- [YYYY-MM-DD] [actor] what changed — detail`.
- Before an update, `SOUL.md`, `config.yaml` and `MEMORY.md` are copied to `<profile>/backups/<timestamp>/`.
- Instructions change only through an approved brief and `create_agent.py --update`.

## 7. Safety and secrets

- Secrets live only in the agent's own `.env` (permissions 600) or the Mac Keychain. Never in briefs, registry, docs, SOUL or chat. Never copied between agents.
- `approvals.mode` stays `smart` or `manual`. One-shot runs, timers and API sessions cannot ask anyone, so risky commands are denied there by default.
- On this Mac a folder limit is a rule the agent follows, not a wall. Say so plainly. A real wall needs a sandbox (Docker), which is not installed.
- Timers, passwords, outside connections and messages to other people always need a separate, explicit OK.

## 7a. Connections (tools)

Built-in toolsets are limited per agent with `agent.disabled_toolsets` (least privilege). Outside tools connect through MCP in the agent's own `config.yaml`, with an include list of only the tools the job needs, read-only first, secrets as `${VAR}` from its `.env`. Each connection is verified with `hermes mcp test` and one harmless read before the agent is called working.

## 8. Reviews

First review after the first three real tasks or seven days, whichever comes first. Then monthly. Each review records `last_review` in the registry.

## 9. What "working" means

An agent is **working** when `check_agent.py` shows no FAIL, its scenario tests passed or were reviewed by Robi, and Robi has used it for one real task and said the result was right. Only then does it become `production`.
