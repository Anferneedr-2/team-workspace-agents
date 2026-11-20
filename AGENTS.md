# AGENTS.md — Agents repository

Team directory (like `Governor/` and `Bundy/`), not a project: no slug base, no project bots, not in the hub projects registry.

1. Definitions only. Never put client data, credentials or API keys here.
2. Changes to `roles/`, `skills/` or `templates/` are workspace changes: log them in the root `CHANGELOG.md` and let `governor` review before they are used for new clients.
3. `instances.yaml` is written by `bin/hire_agent.py`. Do not hand-edit it.
4. A new skill goes through the governance path: review, hash, add to the approved list, rebuild governance.
