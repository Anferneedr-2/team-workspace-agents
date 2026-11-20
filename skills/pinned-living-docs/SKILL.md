---
name: pinned-living-docs
description: Use when maintaining a pinned workspace living doc.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [documentation, workspace, living-doc, obsidian, canonical-entry, roster, scoping]
    related_skills: [obsidian, hermes-agent, agent-workspace-governance]
---

# Pinned Living Docs

Procedure for a paired artifact: a **pinned living document** (`README.md` at a workspace root) that owns team/project facts, and a **canonical Obsidian entry** that is only an index + snapshot of it. Use it for team workspaces whose roster, projects, and conventions change often. Vault mechanics (path resolution, CLI syntax, traps) belong to the `obsidian` skill — load it for anything beyond writing a note file.

## When to Use

- Creating or updating a pinned `README.md` at a workspace/team root, or its paired canonical Obsidian entry.
- Registering a new bot/role, project, or scoping rule in an existing living doc, or bumping its version/changelog.
- The user mentions "pinned documentation", a "living document", a "canonical entry", or roster/scoping updates for a team workspace.

Starter skeleton: `templates/pinned-readme.md`.

## Create

1. Resolve paths first: workspace root (the folder the user names); vault path via `$OBSIDIAN_VAULT_PATH` (if unset, check `${HERMES_HOME:-~/.hermes}/.env`, then fall back to `~/Documents/Obsidian Vault`); confirm the CLI with `obsidian vault`.
2. Write `README.md` at the workspace root from `templates/pinned-readme.md`: header table (setup, absolute paths, Status `vX.0`, Last updated), purpose, folder layout, roster table, one scoping subsection per dual-scope role, routing table, projects registry with explicit empty-state rows, update protocol, changelog starting at v0.1.
3. Write the canonical entry `<Team or Workspace Name>.md` at the vault root:
   - frontmatter: `tags`, `status`, `canonical: true`, `workspace_root`, `living_doc`, `version`, `created`, `updated`
   - body: one sync-rule sentence, a snapshot table, roster bullets carrying status flags, scoping notes, links.
   - **Never copy the full document into the entry** — two full copies are a guaranteed drift machine.
4. Verify both: files exist at both paths, and `obsidian search query="<note title>"` returns the note.

## Update

1. Read both files first — patch anchors must match on-disk text, and the doc may have changed since any session you remember.
2. Apply every edit in ONE `execute_code` run: build a list of `(path, old_string, new_string)` tuples and loop them through `hermes_tools.patch`, printing a per-patch pass/fail. Patches to the same file must not be separate parallel tool calls (concurrent writes race); one sequential batch gives one honest result per edit. **Exception — agent-instruction files:** `AGENTS.md` (root and per project) and any contract file sit behind an approval gate. Write those in their own standalone `patch` call after the batch: inside the batch the approval prompt blocks the cell, the run times out, and every other result in it is lost. If a write comes back `BLOCKED`, it is final — report it and ask for approval; never retry it through another path (terminal, another batch).
3. Ship in the same batch: the content change, the Status/version bump, and its changelog row. A change that lands without its bump and row has already half-rotted the doc.
4. Mirror only the changed section(s) into the Obsidian entry — README first, always.
5. Verify both files: `search_files` for the new heading/version in the workspace and in the vault.
6. Duplication audit (when the user asks whether the docs duplicate something): run `python3 scripts/dup_scan.py <workspace-root>` — it lists long prose lines shared across `.md` files. Template boilerplate instantiated per project is benign; a shared *fact* (roster row, rule, changelog entry) is a second source of truth and one copy becomes a link.

## Always-on rules

- **One source of truth.** The workspace README owns team facts; the Obsidian entry is index + snapshot. Edit facts in the README first and mirror deltas — never edit them in Obsidian first, never maintain both "to be safe".
- **Placeholders over guesses.** A role that does not exist yet gets a 🟡 "not yet generated" row with a provisional slug; flip it only after `hermes profile list` (or the role's equivalent command) shows it. Commands quoted in the doc come from `--help` output, never from memory.
- **Scoping pattern.** Every role states its scope. A role that exists at both workspace level and project level gets a numbered subsection: top-level scope statement → per-project scope → explicit isolation rule (what the scoped instance must never read, inject, or route) → escalation path back to the top-level instance → placeholder note.
- **Empty states are rows, not absences.** "No projects yet" is an explicit line; a blank section reads like an oversight.
- **Update triggers:** a bot is generated, a project is added, or a role/scoping/convention changes → same-batch edit + version bump.
- **Output style:** finish with what changed, what was verified, and exactly one next action.

## Pitfalls

- A syntax error in the batch script aborts the whole run — zero patches apply. Escape apostrophes as `\'` (or use double quotes) in embedded doc text; a "0 of N applied" report means the error was at parse time, not in a patch, so fix the script rather than the anchors.
- Generated artifacts (`governance.yaml`, an access registry keyed by skill with `granted_to`) are never edited as documents — they are rebuilt from live state via the generator, so link to them instead of restating their contents. Procedure: `agent-workspace-governance`.
- `write_file` refuses an existing file the task has no current read of — `read_file` it first when the file changed outside this session.
- Flag-style args to the official `obsidian` CLI fail with usage text; it takes `key=value` (e.g. `obsidian search query="..."`).
- Do not pre-create empty Obsidian notes for roster roles that do not exist yet — snapshot them as bullets in the canonical entry until generated; unresolved wikilinks are noise, not structure.
- A project doc that **restates** a hub rule duplicates it; one that **links** to §3.x does not. Restating invites drift the moment the hub changes — link, and keep the local copy only for facts that exist nowhere else (the project's own TBDs, its board coordinates, its changelog).