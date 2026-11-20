#!/usr/bin/env python3
"""Read-only, local-only registry validator (Phase 1).

Never writes anything. Checks Agents/registry.yaml against the live local
Hermes install. Does NOT replicate Governor/validate_governance.py (that
script describes the remote's roster — see ../../REMOTE-REFERENCE-INDEX.md).

  validate_registry.py              run all checks against the real registry
  validate_registry.py --registry <path> --profiles-dir <path>
                                     run against fixtures (for tests)

Exit code: 0 if no ERROR-level findings, 1 otherwise. WARN-level findings
(including "unmigrated metadata") never fail the run.
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

DEFAULT_WS = Path.home() / 'Team-Workspace'
DEFAULT_AG = DEFAULT_WS / 'Agents'
DEFAULT_PROFILES = Path.home() / '.hermes' / 'profiles'
DEFAULT_TEAMS = DEFAULT_AG / 'teams'


def load_registry(path: Path) -> dict:
    d = yaml.safe_load(path.read_text()) or {}
    d.setdefault('clients', {})
    d.setdefault('agents', [])
    return d


def live_profiles(profiles_dir: Path) -> set:
    if not profiles_dir.exists():
        return set()
    return {p.name for p in profiles_dir.iterdir()
            if p.is_dir() and not p.name.startswith(('.', '_'))}


def profile_cwd(profiles_dir: Path, slug: str) -> str:
    cfg_path = profiles_dir / slug / 'config.yaml'
    if not cfg_path.exists():
        return ''
    try:
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        return ''
    return str((cfg.get('terminal') or {}).get('cwd') or '')


NEW_FIELDS = ('definition_id', 'definition_version', 'definition_hash', 'instance_scope', 'project')


def resolve_definition_file(ag_dir: Path, definition_id: str, version: str):
    """Mirrors create_agent.py's resolve_definition() exactly (duplicated on purpose --
    this validator must stay self-contained and read-only, independent of the writer
    script). Returns (path, kind) where kind is 'current' or 'archive', or (None, None)."""
    cur = ag_dir / 'briefs' / f'{definition_id}.md'
    if cur.is_file():
        try:
            text = cur.read_text()
            m = re.search(r'```(?:yaml )?build-spec\n(.*?)\n```', text, re.S)
            cur_version = None
            if m:
                vm = re.search(r'^definition_version:\s*(.+)$', m.group(1), re.M)
                cur_version = vm.group(1).strip() if vm else None
            if cur_version is not None and cur_version == str(version):
                return cur, 'current'
        except Exception:
            pass
    arc = ag_dir / 'briefs' / f'{definition_id}-v{version}-archive.md'
    return (arc, 'archive') if arc.is_file() else (None, None)


def current_definition_version(ag_dir: Path, definition_id: str):
    cur = ag_dir / 'briefs' / f'{definition_id}.md'
    if not cur.is_file():
        return None
    m = re.search(r'```(?:yaml )?build-spec\n(.*?)\n```', cur.read_text(), re.S)
    if not m:
        return None
    vm = re.search(r'^definition_version:\s*(.+)$', m.group(1), re.M)
    return vm.group(1).strip() if vm else None


def scan_definition_ids(ag_dir: Path) -> set:
    """Just the set of definition ids with a parseable build-spec, for the team-manifest
    'missing agent' check -- a member may name an approved-but-not-yet-instantiated
    definition, which is valid and must not be flagged as missing."""
    briefs_dir = ag_dir / 'briefs'
    skip_suffixes = ('-archive.md', '-test-report.md', '-how-to-use.md', '-source-file.md',
                      '-draft.md', '-spec.md', '-notes.md', '-request.md')
    skip_names = {'GENERIC-HELPERS.md', 'README.md'}
    out = set()
    if not briefs_dir.is_dir():
        return out
    for f in briefs_dir.glob('*.md'):
        if f.name in skip_names or f.name.endswith(skip_suffixes):
            continue
        m = re.search(r'```(?:yaml )?build-spec\n(.*?)\n```', f.read_text(), re.S)
        if not m:
            continue
        idm = re.search(r'^definition_id:\s*(.+)$', m.group(1), re.M)
        nm = re.search(r'^name:\s*(.+)$', m.group(1), re.M)
        out.add((idm.group(1).strip() if idm else (nm.group(1).strip() if nm else f.stem)))
    return out


def definition_brief_path(ag_dir: Path, definition_id: str):
    """Just the brief file for a definition id, or None -- used for the approval-status
    check, kept separate from scan_definition_ids so that check stays a plain set lookup."""
    f = ag_dir / 'briefs' / f'{definition_id}.md'
    return f if f.is_file() else None


def definition_is_approved(ag_dir: Path, definition_id: str) -> bool:
    f = definition_brief_path(ag_dir, definition_id)
    if not f:
        return False
    return bool(re.search(r'^Status:\s*APPROVED\b', f.read_text(), re.M))


def check_source_definitions(agents: list, ag_dir: Path) -> list:
    """Four distinct states for a pinned source_definition, never collapsed into one
    flat 'drift' flag:
      - valid pinned-older version  -> INFO  (normal, approved, no action needed)
      - actual drift                -> ERROR (recorded hash != the resolved file's real hash)
      - missing/invalid reference   -> ERROR (id/version resolves to nothing on disk)
      - newer version available     -> INFO  (surfaced only; never auto-applied)
    Agents with no source_definition are skipped entirely -- this feature is opt-in."""
    import hashlib
    findings = []
    for a in agents:
        sd = a.get('source_definition')
        if not sd:
            continue
        did, _, version = str(sd).partition('@')
        resolved, kind = resolve_definition_file(ag_dir, did, version)
        if not resolved:
            findings.append(('ERROR', 'F-definition-reference',
                              f"{a['name']}: source_definition \"{sd}\" does not resolve to any "
                              f"current or archived definition file"))
            continue
        recorded_hash = a.get('definition_hash')
        actual_hash = 'sha256:' + hashlib.sha256(resolved.read_text().encode()).hexdigest()
        if recorded_hash and recorded_hash != actual_hash:
            findings.append(('ERROR', 'F-definition-drift',
                              f"{a['name']}: pinned definition {sd} ({kind}) content no longer matches "
                              f"its recorded hash -- the {kind} file changed after this instance pinned it"))
        else:
            findings.append(('INFO', 'F-definition-reference',
                              f"{a['name']}: source_definition {sd} resolves cleanly ({kind}) -- valid pinned version"))
        cur_version = current_definition_version(ag_dir, did)
        if cur_version and cur_version != version:
            findings.append(('INFO', 'F-newer-version-available',
                              f"{a['name']}: pinned at {did}@{version}; a newer definition_version "
                              f"{cur_version} exists -- upgrade is available but not automatic"))
    return findings


def load_team_manifests(teams_dir: Path) -> list:
    out = []
    if not teams_dir.is_dir():
        return out
    for f in sorted(teams_dir.glob('*.yaml')):
        try:
            data = yaml.safe_load(f.read_text()) or {}
            out.append((f, data))
        except Exception as e:  # noqa: BLE001
            out.append((f, {'_parse_error': str(e)}))
    return out


LIFECYCLES = ('proposed', 'approved', 'provisioned', 'validated', 'active')


def normalize_member(m: dict):
    """Separates the 5 distinct concepts the schema now tracks explicitly:
      definition_id       -- which reusable definition (repository brief)
      definition_version  -- pinned version of it (optional)
      planned_instance    -- the intended future project-specific Hermes profile slug
      instance            -- the ACTUAL deployed slug, once built (None until then)
      legacy               -- True when this member predates the split and only gave
                              'instance', which under the OLD schema did double duty as
                              either a definition reference or a real instance name --
                              that ambiguity is exactly what this schema version removes.
    Legacy members are only ever valid at proposed/approved (see check below); from
    provisioned onward a member MUST carry an explicit definition_id so a generic
    repository instance can never silently stand in for a missing project instance."""
    definition_id = m.get('definition_id')
    planned_instance = m.get('planned_instance')
    instance = m.get('instance')
    legacy = False
    if not definition_id:
        legacy = True
        definition_id = instance  # old shorthand: 'instance' held the definition id
        instance = None           # under legacy shorthand we cannot tell it apart from a
                                   # real deployed slug -- never trust it as one
    return definition_id, planned_instance, instance, legacy


def check_team_manifests(teams_dir: Path, agents: list, defs_ids: set, ag_dir: Path, ws_dir: Path) -> list:
    """Lifecycle-cumulative validation: each stage's requirements also re-checks every
    requirement of the stages before it, so the validator rejects lifecycle advancement
    when an earlier prerequisite is missing, not just the newest one.

      proposed     -- structurally coherent plan: reasoning, valid architecture/member-count,
                       every member resolves to a known definition or real instance, no
                       invalid/circular dependencies.
      approved     -- (+ proposed) every member's definition_id is explicit and resolves to
                       an APPROVED (not draft) brief; the manifest itself records an
                       'approval' note. A legacy member (no explicit definition_id) is
                       tolerated here only, with a WARN, for backward compatibility.
      provisioned  -- (+ approved) every member carries an explicit 'instance' that resolves
                       to a REAL registry row, AND that row's own folder is inside THIS
                       project's folder -- a generic reference profile (whose folder is the
                       repository's own Generic-Helpers/ home, not the project's) can never
                       satisfy this. A legacy member cannot satisfy this at all.
      validated    -- (+ provisioned) the resolved instance's registry 'tests' record is
                       clean (shows '0 fail').
      active       -- (+ validated) the manifest records a non-empty 'activated' note,
                       distinct from 'approval'.
    """
    reg_by_name = {a['name']: a for a in agents}
    reg_names = set(reg_by_name)
    findings = []
    for f, data in load_team_manifests(teams_dir):
        if '_parse_error' in data:
            findings.append(('ERROR', 'E-team-manifest', f"{f.name}: cannot parse YAML ({data['_parse_error']})"))
            continue
        project = data.get('project', f.stem)
        members = data.get('members') or []

        lifecycle = data.get('lifecycle')
        if lifecycle is None:
            findings.append(('WARN', 'E-team-lifecycle', f"{project}: no 'lifecycle' field -- treated as 'proposed'"))
            lifecycle = 'proposed'
        elif lifecycle not in LIFECYCLES:
            findings.append(('ERROR', 'E-team-lifecycle', f"{project}: lifecycle must be one of {LIFECYCLES}, got {lifecycle!r}"))
            lifecycle = 'proposed'  # fall back to the most permissive stage for the remaining checks
        stage = LIFECYCLES.index(lifecycle)

        if not str(data.get('reasoning') or '').strip():
            findings.append(('ERROR', 'E-team-reasoning', f"{project}: 'reasoning' field is missing or empty"))

        arch = data.get('architecture')
        if arch not in ('deterministic', 'single-agent', 'multi-agent'):
            findings.append(('ERROR', 'E-team-architecture', f"{project}: architecture must be one of "
                              f"deterministic|single-agent|multi-agent, got {arch!r}"))
        elif arch == 'single-agent' and len(members) != 1:
            findings.append(('ERROR', 'E-team-architecture',
                              f"{project}: architecture is single-agent but has {len(members)} member(s)"))
        elif arch == 'deterministic' and members:
            findings.append(('ERROR', 'E-team-architecture',
                              f"{project}: architecture is deterministic but lists {len(members)} agent member(s)"))

        # approved+ requires a recorded approval note; active additionally requires activation.
        if stage >= LIFECYCLES.index('approved') and not str(data.get('approval') or '').strip():
            findings.append(('ERROR', 'E-team-lifecycle-mismatch',
                              f"{project}: lifecycle is '{lifecycle}' but no 'approval' note is recorded"))
        if lifecycle == 'active' and not str(data.get('activated') or '').strip():
            findings.append(('ERROR', 'E-team-lifecycle-mismatch',
                              f"{project}: lifecycle is 'active' but no 'activated' note is recorded "
                              f"(distinct from 'approval' -- records explicit activation, not just the plan)"))

        norm = {}  # definition_id -> True (membership key is recorded here) for depends_on/cycle checks
        for m in members:
            raw_instance = m.get('instance')
            definition_id, planned_instance, instance, legacy = normalize_member(m)
            label = definition_id or raw_instance or '(unnamed)'
            key = definition_id or raw_instance
            if key:
                norm[key] = True

            if not key:
                findings.append(('ERROR', 'E-team-missing-agent', f"{project}: a member has neither "
                                  f"'definition_id' nor 'instance' set"))
                continue
            # Floor check: known at all, by EITHER route -- a legacy member naming an
            # already-real instance must not be flagged missing just because the richer
            # checks below (which require an explicit split) don't trust it as one.
            is_known_definition = bool(definition_id) and definition_id in defs_ids
            is_real_instance = bool(instance) and instance in reg_names
            known = is_known_definition or is_real_instance or (bool(raw_instance) and raw_instance in reg_names)
            if not known:
                findings.append(('ERROR', 'E-team-missing-agent',
                                  f"{project}: member '{label}' is not a known registry instance or definition"))
                continue

            if legacy:
                if stage >= LIFECYCLES.index('provisioned'):
                    findings.append(('ERROR', 'E-team-lifecycle-mismatch',
                                      f"{project}: member '{label}' uses the old shorthand (no explicit "
                                      f"'definition_id'/'instance' split) -- not accepted from 'provisioned' "
                                      f"onward because a bare name cannot be told apart from a generic "
                                      f"repository instance; split it into definition_id + instance first"))
                else:
                    findings.append(('WARN', 'E-team-legacy-shorthand',
                                      f"{project}: member '{label}' uses the old shorthand ('instance' doubling "
                                      f"as a definition reference) -- fine at '{lifecycle}', but split into "
                                      f"separate 'definition_id'/'planned_instance'/'instance' fields before "
                                      f"advancing past 'approved'"))
            else:
                if stage >= LIFECYCLES.index('approved'):
                    if not definition_is_approved(ag_dir, definition_id):
                        findings.append(('ERROR', 'E-team-lifecycle-mismatch',
                                          f"{project}: member '{label}' lifecycle is '{lifecycle}' but its "
                                          f"definition's brief is not Status: APPROVED"))
                    if not planned_instance:
                        findings.append(('WARN', 'E-team-schema',
                                          f"{project}: member '{label}' has no 'planned_instance' (intended "
                                          f"future instance name) -- recommended from 'approved' onward for a "
                                          f"clear plan"))

                if stage >= LIFECYCLES.index('provisioned'):
                    if not instance:
                        findings.append(('ERROR', 'E-team-lifecycle-mismatch',
                                          f"{project}: member '{label}' lifecycle is '{lifecycle}' but 'instance' "
                                          f"is not set -- no real profile has been built yet"))
                    elif not is_real_instance:
                        findings.append(('ERROR', 'E-team-missing-agent',
                                          f"{project}: member '{label}' declares instance '{instance}' but no "
                                          f"such registry row exists"))
                    else:
                        row = reg_by_name[instance]
                        row_folder = str(row.get('folder') or '')
                        project_folder = str(ws_dir / project)
                        if not row_folder or not (row_folder == project_folder or row_folder.startswith(project_folder + '/')):
                            findings.append(('ERROR', 'E-team-scope-mismatch',
                                              f"{project}: member '{label}' instance '{instance}' resolves to a "
                                              f"real profile, but its registry folder ({row_folder or '(none)'}) "
                                              f"is not this project's folder ({project_folder}) -- a generic or "
                                              f"other-project profile cannot substitute for this project's own "
                                              f"instance"))
                        if planned_instance and instance != planned_instance:
                            findings.append(('ERROR', 'E-team-schema',
                                              f"{project}: member '{label}' instance '{instance}' does not match "
                                              f"its own planned_instance '{planned_instance}'"))
                        row_sd = str(row.get('source_definition') or '')
                        if row_sd and row_sd.split('@')[0] != definition_id:
                            findings.append(('WARN', 'E-team-schema',
                                              f"{project}: member '{label}' instance '{instance}' has "
                                              f"source_definition {row_sd!r}, which does not match this "
                                              f"member's definition_id '{definition_id}'"))
                        if stage >= LIFECYCLES.index('validated'):
                            tests = row.get('tests') or ''
                            clean = bool(re.search(r'0 fail', tests)) if tests else False
                            if not clean:
                                findings.append(('ERROR', 'E-team-lifecycle-mismatch',
                                                  f"{project}: member '{label}' lifecycle is '{lifecycle}' but "
                                                  f"its registry tests record is {tests!r} -- not confirmed "
                                                  f"clean (expect '0 fail')"))

            for dep in (m.get('depends_on') or []):
                if dep not in norm and dep != key:
                    findings.append(('ERROR', 'E-team-invalid-dependency',
                                      f"{project}: member '{label}' depends_on unknown member '{dep}'"))

        # Circular-dependency check: simple DFS over depends_on, keyed the same way as
        # the per-member loop above (definition_id, or legacy raw 'instance' string).
        graph = {(m.get('definition_id') or m.get('instance')): list(m.get('depends_on') or [])
                 for m in members if m.get('definition_id') or m.get('instance')}
        visiting, visited = set(), set()

        def has_cycle(node, path):
            if node in visiting:
                findings.append(('ERROR', 'E-team-circular-dependency',
                                  f"{project}: circular dependency: {' -> '.join(path + [node])}"))
                return True
            if node in visited:
                return False
            visiting.add(node)
            for nxt in graph.get(node, []):
                if has_cycle(nxt, path + [node]):
                    return True
            visiting.discard(node)
            visited.add(node)
            return False

        for n in list(graph):
            if n not in visited:
                has_cycle(n, [])
    return findings


def run_checks(registry_path: Path, profiles_dir: Path, ag_dir: Path = None, teams_dir: Path = None, ws_dir: Path = None):
    findings = []  # (level, check, message)
    d = load_registry(registry_path)
    agents = d['agents']
    live = live_profiles(profiles_dir)
    reg_names = {a['name'] for a in agents}
    ag_dir = ag_dir or registry_path.parent  # registry.yaml lives at <Agents>/registry.yaml
    teams_dir = teams_dir or (ag_dir / 'teams')
    ws_dir = ws_dir or ag_dir.parent  # Agents/ is always one level under Team-Workspace/

    # Check A: every non-retired registered agent has a live profile.
    for a in agents:
        if a.get('status') != 'retired' and a['name'] not in live:
            findings.append(('ERROR', 'A-live-profile',
                              f"{a['name']}: registered as {a.get('status')} but no live profile at "
                              f"{profiles_dir / a['name']}"))

    # Check B: live profiles not in the registry (informational — mirrors registry.py's
    # existing 'unmanaged' concept; never an error on its own).
    unmanaged = sorted(live - reg_names)
    for name in unmanaged:
        findings.append(('WARN', 'B-unmanaged', f"{name}: live profile not in registry.yaml"))

    # Check C: declared folder (if set) matches the profile's own config.yaml terminal.cwd.
    for a in agents:
        folder = a.get('folder')
        if not folder or a.get('status') == 'retired' or a['name'] not in live:
            continue
        cwd = profile_cwd(profiles_dir, a['name'])
        if cwd and cwd != str(folder):
            findings.append(('ERROR', 'C-scope-cwd',
                              f"{a['name']}: registry folder={folder!r} but profile config.yaml terminal.cwd={cwd!r}"))
        elif not cwd:
            findings.append(('WARN', 'C-scope-cwd', f"{a['name']}: no terminal.cwd set in its config.yaml to compare"))

    # Check D: new-schema migration status — informational only, per Phase 1 scope
    # (existing agents are intentionally left unmigrated; this never fails the run).
    migrated = [a['name'] for a in agents if any(a.get(f) is not None for f in NEW_FIELDS)]
    findings.append(('WARN', 'D-migration-status',
                      f"{len(migrated)}/{len(agents)} registry entries carry new definition/instance metadata "
                      f"(expected 0 in Phase 1 — see SCHEMA.md)"))

    # Check F (Phase 2): source_definition integrity -- 4-state model (see check_source_definitions).
    findings += check_source_definitions(agents, ag_dir)

    # Check E (Phase 2): team manifests -- missing agents, invalid/circular dependencies,
    # architecture/member-count consistency, and the mandatory (but not sufficient on its
    # own) reasoning field.
    defs_ids = set(scan_definition_ids(ag_dir))
    findings += check_team_manifests(teams_dir, agents, defs_ids, ag_dir, ws_dir)

    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--registry', type=Path, default=DEFAULT_AG / 'registry.yaml')
    ap.add_argument('--profiles-dir', type=Path, default=DEFAULT_PROFILES)
    ap.add_argument('--ag-dir', type=Path, default=None, help='Agents/ root for briefs+teams (default: registry.yaml\'s own folder)')
    ap.add_argument('--teams-dir', type=Path, default=None)
    ap.add_argument('--ws-dir', type=Path, default=None, help='Team-Workspace root, for team-manifest project-scope checks (default: --ag-dir\'s parent)')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    findings = run_checks(a.registry, a.profiles_dir, ag_dir=a.ag_dir, teams_dir=a.teams_dir, ws_dir=a.ws_dir)
    errors = [f for f in findings if f[0] == 'ERROR']

    if a.json:
        import json
        print(json.dumps({'ok': not errors, 'findings': [
            {'level': l, 'check': c, 'message': m} for l, c, m in findings]}, indent=2))
    else:
        for level, check, message in findings:
            print(f'[{level}] {check}: {message}')
        print(f"\n{len(errors)} error(s), {len(findings) - len(errors)} warning(s)/info "
              f"out of {len(findings)} finding(s). Registry: {a.registry}")

    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
