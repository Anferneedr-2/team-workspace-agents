---
name: task-changelog
description: "Use when a task finishes: auto-log changelog, docs, memory."
version: 0.1.0
author: Jake, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [changelog, memory, living-doc, documentation, indexable]
    related_skills: [pinned-living-docs, obsidian]
---

# Task Changelog

Record what a finished task changed — in the changelog, the living documentation, and memory — using a fixed grep-able format so future sessions and recall can find it.

## Automatic trigger (no user prompt needed)

Fire this yourself at the end of EVERY task that changed anything — the user must never have to say "log it". Two mechanisms make it automatic:

- This skill's description is index-matched on task completion, so it loads without being named.
- A standing rule lives in persistent memory (injected into every session): finished task ⇒ run this procedure before the final reply.

Check before replying: did this turn write files, change facts, or alter structure? If yes and no entry exists for it yet, append it now. Skip only pure Q&A / read-only turns.

## When to Use

- Any task that changed files, facts, structure, profiles, or conventions is finished (also when the user says "log this" or "document what you did").
- NOT for: pre-work plans (README §8 open items), Jira board activity (`<Project>/Jira/activity-log.md`), or Bundy time entries (`Bundy/time-ins.md`) — those have their own files.

## Which changelog

| Changed… | Entry goes in |
|---|---|
| Workspace root, hub README, Obsidian entry, profiles, Bundy, conventions | `/Users/robi/Team-Workspace/CHANGELOG.md` |
| Inside one project directory (README, Jira/, AGENTS.md, project bots) | `<Project>/CHANGELOG.md` |
| Both | one entry in each file |

Owners (hub README §6): top-level `document-engineer` owns the workspace file, each project's DE owns its project's file — but **any agent appends the entry immediately**; never defer logging to the owner.

## Procedure

1. Determine scope from the table; read the target file so you append under its `## Entries` heading (append-only, newest at the bottom).
2. Append exactly ONE line: `- [YYYY-MM-DD] [actor] what changed — detail`
   - `actor` = your profile slug (e.g. `document-engineer`, `clinicconnects-jira-admin`) or `default`
   - `detail` = version bump if any + key file paths; facts, not narration
3. If structure, roster, conventions, or status changed → follow `pinned-living-docs`: bump README `Status` + `Last updated`, apply the delta, mirror the changed sections to the Obsidian entry (`Agentic Team Alpha.md`), bump its frontmatter `version:`.
4. Retain memory in the same turn: `hindsight_retain(content="Changelog [YYYY-MM-DD] [scope]: <what changed> → <files>", tags=["changelog", "agentic-team-alpha"])`
5. Verify both indexes, then report the file path:
   - `search_files(target="content", pattern="^- \\[20", file_glob="CHANGELOG.md")` finds your line
   - living doc / Obsidian bumped only if step 3 applied

## Entry format (the index contract)

```
- [2026-11-04] [document-engineer] v1.2 — created CHANGELOG.md files, wired DE ownership → CHANGELOG.md, README §6
```

- Fixed prefix `- [YYYY-MM-DD] ` — one pattern finds every entry across every changelog: `search_files(target="content", pattern="^- \\[20", file_glob="CHANGELOG.md", path="/Users/robi/Team-Workspace")`
- Project files are scoped by their location; workspace entries name the scope in the summary when relevant
- Memory side: the `changelog` tag makes `hindsight_recall("changelog entries")` return the run history
- Cross-links keep it one graph: project changelogs link `../CHANGELOG.md`; the Obsidian entry's `## Related` points at the workspace file; README §7 is a pointer, never a duplicate

## Pitfalls

- Append-only — never rewrite old entries; correct mistakes with a new correction entry.
- Never copy history back into README §7 (pointer by design since v0.9).
- One entry per finished task: multi-file work collapses into one line with a `→ file list`.
- Use the local date (`date +%F`), not UTC, to avoid off-by-one-day entries.
- Changelog entry + living-doc delta + memory retain happen in the SAME turn — all three, or the task isn't logged.
- Do not automate this with a Hermes shell/gateway hook: `agent:end` payloads carry only truncated message/response, so a hook cannot write a factual entry and would pollute an append-only log. The automatic trigger is the description + standing memory rule (see "Automatic trigger").
- Logging is itself a change — a task that edits this skill, the entry format, or the changelog files still appends an entry.
- A profile only sees this skill if it exists in that profile's own `skills/` dir; copying it into `~/.hermes/profiles/<slug>/skills/` is part of wiring a bot.

## Verification

- `search_files(target="files", pattern="CHANGELOG.md", path="/Users/robi/Team-Workspace")` returns 3 files (root, CliniConnects, Guardare)
- Content search for `^- \[20` returns every entry ever written
- `hindsight_recall("changelog entries")` returns recent retains tagged `changelog`