# Agents — the agent repository

Reusable agent definitions and the tools that turn them into per-client agents. **No client data lives here.** Client work lives in the client folders next to this one (`../<Client>/`).

| Path | What it is |
|---|---|
| `roles/workspace/` | the 6 workspace-wide roles (governor, memory-manager, project-orchestrator, document-engineer, assistant, bundy) |
| `roles/project/` | the 3 roles every client gets: orchestrator, memory-manager, document-engineer |
| `skills/` | canonical copies of the custom skills (socratic-discovery, workflow-and-journey-mapping, agent-requirements, agent-lifecycle, hermes-reference, task-changelog, pinned-living-docs, agent-workspace-governance, agent-memory-layer, hindsight-omniroute-llm) |
| `templates/project/` | the client folder skeleton: README, AGENTS, CHANGELOG, `Memory/`, `Work/`, `Deliverables/`, `Marketing/`, `Research/`, `Data/`, `Assets/`, `Sources/` |
| `CATALOG.md` | the specialists you can hire for a client (generated from `../departments.yaml`) |
| `instances.yaml` | which agents are hired for which client (governance reads it) |
| `optional/jira/` | **Jira, an optional tool** (not a default): `Jira/` skeleton + `jira-admin` role, switched on per client with `bin/enable_jira.py` |
| `optional/` (rest) | inert reference copies from the remote Mini: Hindsight + `jev` scripts and its Obsidian note (see `optional/README.md`) |
| `AGENT-REQUIREMENTS.md` | the requirements for creating an agent (Hermes platform + decisions + registration + verification), from the remote Mac Mini |
| `CONVENTIONS.md` | how agents are organized: placement, names, records, status lifecycle, change control |
| `registry.yaml` / `REGISTRY.md` | the register of every agent (and what does not yet follow the requirements) |
| `briefs/` | Agent Briefs and test reports written by `agent-creator` |
| `bin/` | `new_client.py` (create or complete a client folder + its 3 bots; `--with-jira` adds Jira), `enable_jira.py` (add or remove Jira for one client), `create_agent.py` (build, `--update` or `--retire` a helper from an approved brief), `check_agent.py` (checks and scenario tests), `registry.py` (the register), `hire_agent.py` (reuse a specialist for one client) |

## How reuse works

A specialist (for example `seo-audit-bot`) is a **definition**. Hiring it for a client creates an **instance**, a separate profile `<base>-<specialist>` that:

- starts in that client's folder (`terminal.cwd`) and is told to work only there;
- has its own memory, so what it learns about one client never reaches another;
- copies the specialist's persona and extra skills, but **not** its `.env` or credentials;
- is registered in `instances.yaml` and in governance.

```bash
python3 ~/Team-Workspace/Agents/bin/hire_agent.py seo-audit-bot SimplySource
python3 ~/Team-Workspace/Agents/bin/new_client.py "Client Name" clientslug
```

Then run governance: `python3 ~/Team-Workspace/Governor/build_governance.py && python3 ~/Team-Workspace/Governor/validate_governance.py` (add `--write-lock` after you approve).

<!-- agents:start -->
## Agents in this folder

| Agent | Job | Status | Model |
|---|---|---|---|
| `agent-creator` | Take every new helper from the first question to a working, connected, tested, documented… | testing | claude-sonnet-5-5 |
<!-- agents:end -->
