# Registry metadata schema (Phase 1 fields documented; Phase 2 fields now implemented)

This documents **optional** fields that `Agents/registry.yaml` entries and
`Agents/briefs/*.md` build-spec blocks *may* carry, to separate reusable
**agent definitions** (briefs) from deployed **project instances** (registry
rows / Hermes profiles). As of Phase 2, the fields below under "now live" are
actually read and acted on by `create_agent.py` / `registry.py` /
`validate_registry.py`; everything under "documented, not yet built" remains
exactly that.

- No existing `registry.yaml` entry or brief has been given these fields —
  every current agent's definition mapping is genuinely uncertain and is
  **not** being guessed at or back-filled. A brief or registry row that
  never mentions a key below behaves byte-for-byte as it did before Phase 2
  — confirmed by `Agents/bin/tests/test_phase2.py`.
- `Agents/bin/validate_registry.py` treats missing Phase-1-era fields
  (`instance_scope`, `project`, etc.) as "unmigrated" (informational), never
  as an error. Phase-2-era fields (`source_definition`, `definition_hash`)
  are validated for real when present (see "Source-definition integrity"
  below) but are entirely optional — absence is never flagged.

## Brief build-spec keys — now live

These go in the fenced ` ```build-spec ` block of a brief, the same place
`name`/`intent`/`skills`/etc. already live. `create_agent.py`'s parser
accepts any key without a code change (confirmed by direct test before this
phase started); only `capabilities` and `requires` needed adding to its
`LIST_KEYS` set to parse as real lists instead of a mangled string.

```yaml
capabilities:
- documents
- changelog-maintenance
requires:
- client folder with Memory/
generic: yes
definition_id: document-engineer    # stable id; defaults to the brief's own `name` if omitted
definition_version: 2               # integer; bump only on an approved content change
```

A **copy instance's** brief additionally carries (only the copy, never the generic definition itself):
```yaml
source_definition: document-engineer@1   # <definition_id>@<version>
```
`create_agent.py` resolves this at build time (`resolve_definition()` /
`check_source_definition()`): it must match either the current (non-archived)
brief's own `definition_version`, or an existing `<id>-vN-archive.md`. A
reference that resolves to nothing **fails the build immediately** — this is
checked during `--dry-run` too, not only on a real build. On success,
`create_agent.py` computes and pins `definition_hash: sha256:...` into the
registry row itself — this is always computed by the script, never typed by
hand.

## Brief frontmatter — documented, not yet built (Phase 1 draft, unchanged)

```yaml
---
statefulness: stateful              # stateful | stateless
shared_instance_allowed: false       # true only if statefulness: stateless
                                     # AND all 6 isolation factors are demonstrated
                                     # (memory, credentials, cwd, session history,
                                     # tool permissions, filesystem access)
---
```

Immutability rule: once `definition_version: N` is written for a brief, its
content is never edited again. A further change is `N+1`, with `N`'s full
text preserved verbatim (the existing `-vN-archive.md` convention already
does this for several briefs; this just makes the version number explicit
in frontmatter instead of inferred from filenames).

## `registry.yaml` per-agent fields (optional, new)

```yaml
- name: clinicconnects-memory-manager
  ...                        # all existing fields unchanged
  definition_id: memory-manager       # NEW — which brief this instance was built from
  definition_version: 1               # NEW — pinned at build time; never auto-bumped
  definition_hash: sha256:...         # NEW — hash of the brief body at build time
  instance_scope: project             # NEW — project | shared | team
  project: CliniConnects              # NEW — null for shared/team instances
```

No existing row needs any of these fields to remain valid. A future phase
may add a dedicated `upgrade_agent.py` to move one named instance from one
pinned `definition_version` to a newer one, one instance at a time, each
requiring its own explicit approval — bumping a definition's version must
never silently change any already-deployed instance. That script is **not**
part of Phase 1.

## Isolation checklist (for any future `instance_scope: shared` claim)

A shared instance is only valid when **all six** are true for the role:

1. No per-project memory dependency.
2. No per-project credentials.
3. Working directory can be safely overridden per call (`--in`) with no
   cross-project leakage.
4. **Session history**: the instance's own `state.db`/`sessions/` would not
   mix sensitive content from two different projects across calls.
5. Tool/toolset permissions are identical across every project that would
   call it.
6. Filesystem access risk is acceptable given Hermes provides no OS-level
   sandbox on this Mac (Docker not installed) — isolation here is always
   behavioral, never enforced, for shared *and* project-isolated instances
   alike.

If any one factor fails, the role defaults to a project-isolated instance.

## Discovery — now live (`registry.py find`)

```
registry.py find <query>        # tag / skill / connection / low-confidence text match
registry.py find --generic      # list only definitions marked generic: yes
```
No new registry or database: discovery is a **union** of two things that
already exist — `Agents/briefs/*.md` (definitions, scanned read-only, status
checked via the exact same `Status: APPROVED by Robi on <date>` regex
`create_agent.py`/`check_agent.py` already use for builds) and
`Agents/registry.yaml` (instances, matched by `source_definition` when set,
else by the existing `role` field — which already equals the un-prefixed
brief name for every current entry, so this works today with zero
migration). **A brief existing is never treated as approved**; `find`
reports a definition's real `Status:` line, so a role with an approved,
deployed instance but a currently-drafted brief revision (this exists today:
`accounting-assistant.md` and `hr-assistant.md` are both `Status: DRAFT` v3
while their live instances were built from an earlier approved version) is
reported accurately as both at once, not collapsed into one misleading flag.

Match confidence, highest first: exact `capabilities:` tag match → an
instance's installed `skills:` → an instance's `connections:` → substring
match on `description`/`intent`/`purpose` text, always labeled
`(low-confidence — verify manually)`.

## Source-definition integrity — four distinct states, not one flag

For any registry row with `source_definition: <id>@<version>` set,
`validate_registry.py` reports exactly one of:

| State | Meaning | Level |
|---|---|---|
| Valid pinned-older version | Resolves to the current brief or an archive; recorded `definition_hash` matches its real content | `INFO` — normal, no action |
| Actual drift | Resolves, but the recorded hash no longer matches — the archive or current file changed after pinning | `ERROR` |
| Missing/invalid reference | id/version resolves to no file at all | `ERROR` |
| Newer version available | Resolves and matches cleanly, but the current brief's `definition_version` is higher | `INFO` — upgrade opportunity, never automatic |

An older pinned version is **never, by itself,** reported as a problem.

## Team manifest — `Agents/teams/<project>.yaml` (schema v2, implemented 2026-11-13)

A member now separates five distinct concepts that a bare `instance:` string
used to conflate (the real `Agents/teams/Lighthouse.yaml`, written by
Multi-Agent Engineer before this fix, hit exactly this ambiguity: it had
nothing to stop a generic repository instance from silently satisfying a
project-specific member reference):

```yaml
project: CliniConnects
architecture: multi-agent          # deterministic | single-agent | multi-agent
lifecycle: provisioned             # proposed | approved | provisioned | validated | active
approval: "Robi, 2026-11-13, in chat"     # required from 'approved' onward
activated: "Robi, 2026-11-13, in chat"    # required only at 'active'; distinct from 'approval'
reasoning: "<mandatory, non-empty>" # necessary, not sufficient -- see note below
members:
  - definition_id: document-engineer          # which reusable definition (repository brief)
    definition_version: 1                      # optional pin (not yet enforced beyond resolve)
    planned_instance: clinicconnects-document-engineer   # intended future Hermes profile slug
    instance: clinicconnects-document-engineer           # ACTUAL deployed slug -- null until built
    depends_on: []                              # references other members by their definition_id
    responsibilities: "..."
    handoff: { type: file, path: Deliverables/ }
```

**Lifecycle is cumulative** — each stage also re-checks every requirement of
the stages before it, so advancing the `lifecycle:` label alone never skips
an earlier, unmet prerequisite:

| Stage | Adds (on top of every earlier stage's requirements) |
|---|---|
| `proposed` | `reasoning` non-empty; valid `architecture`/member-count; every member resolves to a known definition or real instance; no invalid/circular `depends_on`. |
| `approved` | Manifest carries a non-empty `approval` note. Each member's `definition_id` must be explicit and resolve to a brief that is `Status: APPROVED` (not draft). `planned_instance` recommended (`WARN` if absent, not yet an error, for the first real manifests). |
| `provisioned` | Each member's `instance` must be **explicitly set** and resolve to a real `registry.yaml` row. That row's own `folder` must be inside **this project's folder** (`<Team-Workspace>/<project>/...`) — a generic reference instance (whose folder is the repository's own home, e.g. `Generic-Helpers/`) can never satisfy this, closing the exact gap above. If `planned_instance` is set, `instance` must equal it. |
| `validated` | The resolved instance's registry `tests` field shows a clean run (`0 fail`). |
| `active` | Manifest carries a non-empty `activated` note, distinct from `approval` (records explicit activation, not just plan sign-off). |

**Backward compatibility, not silent ambiguity.** A member with no explicit
`definition_id` (the old shorthand — a bare `instance: memory-manager` doing
double duty as either a definition reference or a real instance name) is
still accepted at `proposed`/`approved`, with a `WARN` (`E-team-legacy-
shorthand`) nudging it to split the fields. From `provisioned` onward it is
an **ERROR** (`E-team-lifecycle-mismatch`, "old shorthand ... not accepted
from 'provisioned' onward") — a bare name is never trusted as a real,
project-scoped instance, by design.

Other checks, unchanged in kind: `architecture` value and member-count
consistency; every `depends_on` resolves to another member (by
`definition_id`) in the same file; a full cycle check over the dependency
graph. **A non-empty `reasoning` field is necessary documentation, not proof
the chosen architecture is right** — that remains a human judgment call
these structural checks don't and can't make.
