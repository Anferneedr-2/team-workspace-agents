# Registry schema and validator checks

Shapes a generated governance layer settles into: `governance.yaml` ×1 root + ×1 per project,
`skills.yaml` ×1 root (the access registry), a lock file, a memo dir.

## Root `governance.yaml`

```yaml
apiVersion: <workspace>/v1
kind: Governance
metadata: {workspace: /abs/root, generated: <iso>, version: '1.1', canonical_ref: null}
standards: {…}
hierarchy: {owner: user, auditor: governor, operational_root: project-orchestrator, chart: |
  user
  └── governor (audit only)}
bots:
- profile: governor
  role: Governor
  description: <mirrors `hermes profile describe`>
  scope: workspace            # workspace | project
  path: /abs/profile/dir      # or the project dir for project-scoped bots
  reports_to: user            # slug | user
  functional_line: null
  cron_enabled: true
  write_scope: /abs
  read_scope: /abs
  cross_project_read: true
registries: {access: skills.yaml, rule: '…'}
secrets: {provider: macos-keychain, service: <service>, entries: []}
schedules: {jobs: [], policy: {…}}
policies: {…}
security: {…OWASP ASI matrix…}
```

No `skills:` key and no per-bot tool list, ever. A bot record answers *who/where/scope/cadence*;
what it may load is answered only by the access registry.

## Project `governance.yaml`

Same schema, narrower: only that project's project-scoped bots, an `isolation` block naming the
sibling projects it must never read, an `escalation` path, and
`registries: {access: ../../skills.yaml}` plus `metadata.canonical_ref: ../../governance.yaml`.

## `skills.yaml` (kind `AccessRegistry`)

```yaml
skills:
  <skill-name>:
    hash: sha256:<digest of SKILL.md>
    description: <frontmatter description>
    granted_to: [slug, slug, …]      # sorted, explicit
    conflicts: [sha256:…]            # only when profiles disagree
policy: {mode: allowlist + sha256 integrity, dynamic_install: forbidden, review_required: true}
tools:
  cron: {kind: scheduling, description: …, granted_to: [governor]}
```

Grant rules: sorted slugs, never an empty list, no unknown slug, and `cron` granted exactly to the
`cron_enabled` bots.

## Validator checks

| # | Check | Failure means |
|---|---|---|
| 1 | required keys on root + project files | generator regressed |
| 2 | registry bots ↔ live profiles | unregistered profile, or stale record |
| 3 | `reports_to` chain, no cycles | broken chain of command |
| 4 | `path`/scope ↔ profile `terminal.cwd` | scope drift: a project bot pointed at the root (leak risk) |
| 5 | memory provider matches policy | isolation silently disabled |
| 6 | project file is a faithful subset + refs canonical registry | hand-edited project copy |
| 7 | skill/tool grants: unknown bot, granted-not-installed, installed-not-granted, hash drift, cron grant set | access registry out of sync with the install |
| 8 | keychain references resolve; no plaintext secret patterns | invented credential reference or leaked value |
| 9 | skill content scan (pipe-to-shell, eval/exec, base64 pipe, credential paths) | unreviewed skill behaviour; doc-level hits are expected noise |
| 10 | sha256 lock over registries + AGENTS.md + READMEs | change landed without approval/re-lock |

Exit code is 0 only when no ERROR-severity finding exists; WARNs never fail the run.

## Schedule policy block

```yaml
schedules:
  jobs: []
  policy:
    max_model_backed_concurrent: 1
    min_gap_minutes: 10
    jitter_minutes: 5
    quiet_hours: '00:00-06:00'
    timezone: Asia/Manila
    deterministic_scan: no_agent
    collision: 'auto-stagger the later job, log every move'
    cascade_order: [bundy, document-engineer, memory-manager, project-orchestrator, governor]
```

The scan enforces timing only — it never changes what a job does, only when it fires.
