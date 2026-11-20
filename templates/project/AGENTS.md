# AGENTS.md — {{Project}}

Project-scoped rules. Working directory = this folder (`{{WS}}/{{Project}}`).

## Scope — hard rules

1. This project only. Never read or write another project's docs, memory, or context.
2. Cross-project work is not this project's job — raise it to Robi.
3. Writes are confined to this directory, following the Folder map below.

## Agents

Agents for this project are built one at a time with `Agents/bin/create_agent.py` from an approved
brief (`placement: client:{{Project}}`), after a plan and Robi's clear yes. There is no fixed roster
for every project — the Multi-Agent Engineer decides the smallest effective team (deterministic
automation, one agent, or several) for this project's actual stated need, and records it as an
approved plan before anything is built. See `../Agents/REGISTRY.md` for what currently exists here.

## Folder map

| Folder | Holds | Writes |
|---|---|---|
| `README.md`, `AGENTS.md`, `CHANGELOG.md` | entry point, rules, change history | the project's document-keeping agent, once built |
| `Memory/` | human-readable project memory: `context.md`, `decisions.md`, `glossary.md` | the project's memory agent, once built |
| `Work/` | drafts and in-progress files | any project agent |
| `Deliverables/` | approved, client-ready outputs | only after Robi's approval |
| `Marketing/` | client card `CLIENT.md` + marketing data | marketing-related agents, if any |
| `Research/` | research and analysis notes | any project agent |
| `Data/` | raw data and exports (never credentials) | any project agent |
| `Assets/` | brand assets, logos, photos, source files | any project agent |
| `Sources/` | symlinks to this client's existing repos; the repo stays where it is | read through the link |

## Handoff

```bash
hermes -p <slug> --in {{WS}}/{{Project}} -z "<task>"
```
`--in` is mandatory — one-shot calls ignore a profile's own `terminal.cwd`.

## Logging

Every finished task → one entry in `CHANGELOG.md` and one in the workspace root `CHANGELOG.md`,
format `- [YYYY-MM-DD] [actor] what changed — detail`.

## Placeholders

Fields marked `TBD` in `README.md` are unfilled — don't invent project facts; ask the owner.
