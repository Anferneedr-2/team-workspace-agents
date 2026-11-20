---
name: agent-workspace-governance
description: "Govern a multi-agent workspace: registries, lock, audits."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [governance, multi-agent, registry, hash-lock, audit, isolation, cron, org-chart]
    related_skills: [pinned-living-docs, hermes-agent, task-changelog]
---

# Agent Workspace Governance

Governance layer for a multi-profile Hermes workspace: one **generated registry** of bots/hierarchy/scopes, one **access registry** holding every skill and tool exactly once with its grants, a **sha256 lock**, a **validator** that fails on drift, and a **scheduled no-model audit** that writes memos. File shapes and the full check table: `references/registry-schema.md`.

## When to Use

- Maintain or extend governance for a multi-profile workspace: roster change, new project scope, new skill or tool, isolation rule, secret reference, schedule policy, or an audit memo.
- The user says "governance", "org chart", "chain of command", "who may use which skill/tool", "audit/cascade the scheduled tasks", or asks to shorten a registry file that repeats long per-bot lists.
- A bot's granted access must change, or a validator check must be added/trusted.

## Invariants

1. **Generated, never hand-edited.** One build script reads the live install (`hermes profile list`, each profile's `terminal.cwd`, memory provider, installed skills) and writes every registry file. The live profiles are the source of truth; the YAML is the auditable snapshot. Editing YAML directly is the failure mode the whole layer exists to prevent.
2. **Define once, grant by name.** Each skill and each tool gets ONE entry with `hash`, `description`, `granted_to: [slugs]`. Bot records carry role/scope/`reports_to`/write+read scope/cron eligibility and **no lists**. Project-level files reference the canonical registry (`registries.access: ../../<registry>.yaml`); they never copy definitions. Widening access is a one-line edit to one `granted_to` list.
3. **Validate both directions.** `granted but not installed`, `installed but not granted`, and hash drift are all errors. Grants are cross-checked against live capability (a `cron` grant must equal exactly the bots with `cron_enabled`).
4. **Lock, then re-lock only on approval.** The lock is sha256 over registries + root and project `AGENTS.md` + `README.md`; any change without a re-lock reports as an unapproved change.
5. **Secrets are references, never values.** `keychain:<service>/<profile>/<name>`, verified with `security find-generic-password -s <service> -a <profile>/<name>`; absence is reported as "inherits env credentials", not fabricated.
6. **Audit-only posture.** The governor bot proposes in memos; its only autonomous write is timing-only cron staggering (max a few per run, every move logged). Roster/policy/skill changes stay human-approved.

## Procedure — change a definition or a grant

1. Edit the **generator** (`build_governance.py`), never the generated YAML.
2. Rebuild: `~/.hermes/profiles/<governor>/.venv/bin/python Governor/build_governance.py` — it must print every file it wrote with entry counts (skills, tools).
3. Validate and re-lock: `… Governor/validate_governance.py --write-lock` → expect `PASS — N bots / N live profiles`, exit 0, plus expected WARN noise.
4. **Tamper-test any check you added or changed**: mutate one hash/grant in a copy, run `--json`, confirm exit 1 and a message naming the bot and the skill, restore, re-lock. A check you have not seen fail is not known to work.
5. Keep the description honest: the governor's `description` is embedded in the YAML, so `hermes profile describe <slug> --text "…"` **before** the final rebuild.
6. Sync prose in the same pass: living-doc section + version bump, governance README (file table + how to grant/revoke), any Obsidian mirror, then one changelog entry per affected scope.
7. Re-lock last, and record the result line in the report.

## Procedure — add a project or a bot

1. Derive the slug base from the live profile's configured `terminal.cwd` (the orchestrator whose cwd is that project dir), never from the directory name.
2. Register the bot's `reports_to`/`functional_line` in the generator's role map; project-scoped bots report into their project orchestrator, top-level into the user.
3. Rebuild, validate, re-lock. A bot present in the live install but absent from the registry is an ERROR, and so is the reverse — both mean the generator's discovery missed it.
4. Update the doc roster row and changelog; do not hand-add YAML.

## Pitfalls

- **Never fold a project directory name into a profile slug** (`name.lower()`). Names and slugs differ by letters and casing; derive the base from the orchestrator profile's `terminal.cwd` and record it explicitly, or discovery silently finds zero projects.
- **PyYAML block style explodes grant lists.** `safe_dump` defaults to one scalar per line, so 60 entries × 14 grants becomes a thousand-line file. Pass `default_flow_style=None, width=120` — scalar lists stay inline and the file stays diffable and a fraction of the size.
- **`--json` has no `status` key.** The validator's result object is `{ok, bots, live_profiles, findings:[{severity, area, message}], notes}`; read `ok` (and the exit code), not `status`.
- **Hash each `SKILL.md` once.** Every profile keeps its own copy of the same skill, so scanning copies reports the same finding N times; dedupe by digest and cap printed findings with a pointer to `--json`.
- **Cron schedule fields are polymorphic** — a dict with `display`/`expr` or a plain string. Normalize before parsing, and tag naive timestamps (`.replace(tzinfo=timezone.utc)`) before comparing with `datetime.now(timezone.utc)`.
- **The audit script must live in the governor profile's `scripts/` dir** even when the source of truth sits in the workspace — cron `--script` resolves there. Run the job once and confirm `completed` before trusting the schedule.
- **Protected agent-instruction files (`AGENTS.md`, root contracts) sit behind an approval gate.** Write them in their own single tool call, never inside a batch loop with other edits: the prompt blocks the batch, the run times out, the kernel dies, and every other result in it is lost. A `BLOCKED` write is final — do not retry it via terminal or a second batch; report it and ask for approval.
- **Doc version and schema version are different numbers.** Bump the living doc (`vX.Y`) and the registry `metadata.version` independently; conflating them makes both meaningless.
- **In skill files, quote any frontmatter value containing a colon** — an unquoted `description: Foo: bar` fails the YAML parse and aborts the whole skill_manage batch, rolling back every operation in it.

## Verify

- `validate_governance.py --write-lock` → PASS, exit 0, bot count equals `hermes profile list` count.
- Generated files hold no duplicated lists: every bot record's keys are metadata only, and `grep -c granted_to <registry>` equals skills + tools.
- Project files differ from the root only by scope/isolation/`canonical_ref`, and their `registries.access` points at the root registry.
- The daily scan runs clean (`governance PASS · N cron jobs · N model-backed`) and only writes a memo when something needs a human.

## Reporting

Close with what changed, what was verified (counts, exit codes, the tamper test you ran), what is still blocked, and exactly one next action.
