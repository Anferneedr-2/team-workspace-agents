<!-- Pinned living document skeleton. Copy to <workspace-root>/README.md and fill every <> marker. -->

# <Team / Workspace Name> — Workspace Hub (Pinned)

> **Pinned documentation for this folder.** This is a **living document** — edit it in place as the team, projects, and conventions change, and log every change in the [Changelog](#7-changelog). Do not fork it, do not let it drift.

| | |
|---|---|
| **Setup** | <one line: what this workspace is for> |
| **Workspace root** | <absolute path> |
| **Canonical Obsidian entry** | `<Note Title>.md` → <absolute vault path> |
| **Status** | v0.1 — scaffolded; <N> bot profiles still placeholders |
| **Last updated** | <YYYY-MM-DD> |

---

## 1. Purpose

<What this workspace is, who works in it, how bots and projects relate.>

## 2. Folder layout — projects as subdirectories

Every project is one subdirectory of this root:

```
<workspace-root>/
├── README.md                  ← this pinned living document
└── <project-slug>/            ← one directory per project
    ├── README.md              ← purpose, owner, status — the project's entry point
    └── AGENTS.md              ← rules every bot must follow inside this project
```

**Conventions**

1. Directory name: `kebab-case`, stable once created — bots and links reference it.
2. Every project directory **must** contain a `README.md` before any work starts in it.
3. Add `AGENTS.md` once the project has rules worth enforcing.
4. New project checklist: `mkdir <slug>` → write its `README.md` → register it in §5 → add an Obsidian entry.

**Current projects:** _none yet — this section is updated the moment the first one lands._

## 3. The team — Hermes profiles (placeholder roster)

All bots are Hermes profiles under `~/.hermes/profiles/<slug>/`. Run one with `hermes -p <slug> <command>`; manage with `hermes profile ...`.

| Role | Provisional slug | Responsibility | Status |
|---|---|---|---|
| **<Role>** | `<slug>` | <one line: what it owns> | 🟡 Placeholder — not yet generated |

> **To activate a bot:** `hermes profile list` → `hermes profile create <slug>` → run via `hermes -p <slug> ...`.
> **When a bot is generated**, fill in its row: real slug, model, gateway status, generation date, flip 🟡 → ✅.

### 3.x <Role> scoping rules

_(one subsection per role that exists at both workspace and project level)_

1. The **top-level <Role>** at this root is the only one with workspace-wide scope: <what it owns across projects>.
2. Every project will get its **own <role>**, created inside that project's directory, scoped strictly to that one project.
3. **Isolation rule:** a project-scoped <role> must never <read/inject/propagate> context from a different project. Cross-project <knowledge/work> moves only through the top-level <Role>.
4. Project <roles> are 🟡 planned — each gets its row (nested under its project) when generated.

## 4. Routing — intent → bot

| If the request is about… | Route to |
|---|---|
| <workspace-wide intent> | **<Role> (top-level)** |
| <in-project intent> | <Project role> (planned — §3.x) |

_Routing rules are a living section — extend the table as roles sharpen._

## 5. Projects registry

| Project slug | Purpose | Status | Docs |
|---|---|---|---|
| _—_ | _No projects yet_ | — | — |

_New project row goes here the same day its directory is created._

## 6. Living-document protocol

1. **This file is the source of truth** for workspace structure, roster, and conventions.
2. The Obsidian note is the **canonical entry point** (index + snapshot), not a second copy — it links here and mirrors deltas; never edit team facts there first.
3. **Update triggers:** a bot is generated · a project is added · a convention or role changes.
4. **On every update:** bump `Status`/`Last updated` above, add a Changelog row, mirror the changed section into the Obsidian entry.
5. Anyone (human or bot) may edit this file — the document owner keeps it true.

## 7. Changelog

| Date | Version | Change | By |
|---|---|---|---|
| <YYYY-MM-DD> | v0.1 | Scaffolded pinned doc + Obsidian canonical entry; <N> bot placeholders registered | <who/which profile> |
