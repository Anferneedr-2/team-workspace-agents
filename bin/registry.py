#!/usr/bin/env python3
"""Agent registry helper (used by create_agent.py and check_agent.py).

  registry.py status                       list registered agents and anything not yet following the requirements
  registry.py sync                         rewrite REGISTRY.md and every folder's "Agents in this folder" block
  registry.py clean-stale                  one-time: replace old bot tables (for deleted bots) in client READMEs/AGENTS.md
  registry.py review <slug>                record a review today
  registry.py set-status <slug> <status> --approved    testing | production | retired (needs Robi's clear yes)
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

HOME = Path.home()
WS = HOME / 'Team-Workspace'
AG = WS / 'Agents'
PROFILES = HOME / '.hermes' / 'profiles'
REG = AG / 'registry.yaml'
REG_BACKUP_DIR = AG / 'backups' / 'registry'
STATUSES = ('testing', 'production', 'retired')
START, END = '<!-- agents:start -->', '<!-- agents:end -->'

# --- Phase 2: discovery across reusable definitions (briefs) and deployed instances
# (registry rows), without a second registry/database. A small, self-contained brief
# scanner is used here instead of importing create_agent.py: create_agent.py already
# imports this module, so importing it back here would be a circular import.
FENCE = re.compile(r'```(?:yaml )?build-spec\n(.*?)\n```', re.S)
STATUS_APPROVED = re.compile(r'^Status:\s*APPROVED by Robi on \d{4}-\d{2}-\d{2}', re.M)
NONAGENT_BRIEF_NAMES = {'GENERIC-HELPERS.md', 'README.md'}
NONAGENT_BRIEF_SUFFIXES = ('-archive.md', '-test-report.md', '-how-to-use.md', '-source-file.md',
                           '-draft.md', '-spec.md', '-notes.md', '-request.md')


def is_agent_brief(name: str) -> bool:
    return name not in NONAGENT_BRIEF_NAMES and not name.endswith(NONAGENT_BRIEF_SUFFIXES)


def read_definition(path: Path):
    """Minimal read-only scan of one brief's build-spec block: just enough for discovery
    (capabilities, generic flag, approval status). Never writes, never validates fully --
    that remains create_agent.py's job at build time."""
    text = path.read_text()
    m = FENCE.search(text)
    if not m:
        return None
    out = {'capabilities': [], 'requires': [], 'approved': bool(STATUS_APPROVED.search(text))}
    cur = None
    for raw in m.group(1).split('\n'):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        km = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if km and not line.startswith((' ', '-')):
            cur, val = km.group(1), km.group(2).strip()
            out[cur] = [] if cur in ('capabilities', 'requires') else val.strip('"\'')
            continue
        if cur in ('capabilities', 'requires') and line.strip().startswith('- '):
            out[cur].append(line.strip()[2:].strip().strip('"\''))
    out.setdefault('definition_id', out.get('name') or path.stem)
    out['brief_file'] = str(path)
    return out


def scan_definitions() -> dict:
    """Every real agent brief, keyed by definition_id -- independent of whether any
    instance has ever been built from it. This IS the 'reusable definition' registry;
    no separate file is created."""
    out = {}
    briefs_dir = AG / 'briefs'
    if not briefs_dir.is_dir():
        return out
    for f in sorted(briefs_dir.glob('*.md')):
        if not is_agent_brief(f.name):
            continue
        spec = read_definition(f)
        if spec:
            out[spec['definition_id']] = spec
    return out


def scan_instances(d: dict) -> dict:
    """Registry rows, grouped by the definition they implement. Uses source_definition
    when a row has adopted it; otherwise falls back to the existing 'role' field, which
    already equals the un-prefixed brief name for every current entry -- so this is
    useful today, with zero migration of the 18 existing rows."""
    out = {}
    for a in d.get('agents', []):
        sd = a.get('source_definition')
        did = sd.split('@')[0] if sd else a.get('role', a['name'])
        out.setdefault(did, []).append(a)
    return out


def match_tier(dd: dict, instance_rows: list, query: str):
    """Capability match, in descending confidence. Returns (tier, reason) or (None, '')."""
    q = query.lower().strip()
    if not q:
        return 'all', ''
    caps = [c.lower() for c in (dd.get('capabilities') or [])]
    if q in caps:
        return 'capability-tag', f'tagged capability "{q}"'
    for row in instance_rows:
        if q in [s.lower() for s in (row.get('skills') or [])]:
            return 'skill', f'has skill "{q}" installed'
        if any(q in c.lower() for c in (row.get('connections') or [])):
            return 'connection', f'connects to "{q}"'
    text = ' '.join([str(dd.get('description', '')), str(dd.get('intent', ''))] +
                    [row.get('purpose', '') for row in instance_rows]).lower()
    if q in text:
        return 'text (low-confidence)', 'substring match on description/purpose text only -- verify manually'
    return None, ''


def discover(query: str = '', generic_only: bool = False) -> list:
    d = load()
    defs = scan_definitions()
    insts = scan_instances(d)
    rows = []
    for did in sorted(set(defs) | set(insts)):
        dd = defs.get(did)
        if generic_only and not (dd and str(dd.get('generic', '')).lower() in ('yes', 'true')):
            continue
        tier, reason = match_tier(dd or {}, insts.get(did, []), query)
        if query and tier is None:
            continue
        rows.append((did, dd, insts.get(did, []), tier, reason))
    return rows


def load() -> dict:
    d = yaml.safe_load(REG.read_text()) or {}
    d.setdefault('clients', {})
    d.setdefault('agents', [])
    return d


def backup_registry() -> Path | None:
    """Copy the current registry.yaml to a timestamped backup before any write.
    No-op (returns None) if registry.yaml does not exist yet."""
    if not REG.exists():
        return None
    REG_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    dest = REG_BACKUP_DIR / f'registry.yaml.{ts}'
    shutil.copy2(REG, dest)
    return dest


def save(d: dict):
    backup_registry()
    REG.write_text('# Agent registry. Written by Agents/bin/create_agent.py and Agents/bin/registry.py.\n'
                   '# Do not hand-edit agents[]. Readable copy: REGISTRY.md.\n'
                   + yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=120))


def find(d: dict, name: str):
    return next((a for a in d['agents'] if a['name'] == name), None)


def unmanaged(d: dict) -> list:
    reg = {a['name'] for a in d['agents']}
    live = sorted(p.name for p in PROFILES.iterdir() if p.is_dir() and not p.name.startswith(('.', '_')))
    return [p for p in live if p not in reg]


def short(t: str, n=90) -> str:
    t = ' '.join(str(t).split())
    return t if len(t) <= n else t[: n - 1] + '…'


def block_for(d: dict, home: str) -> str:
    rows = [a for a in d['agents'] if a.get('home') == home and a.get('status') != 'retired']
    L = [START, '## Agents in this folder', '']
    if not rows:
        L.append('_No agents yet._')
    else:
        L += ['| Agent | Job | Status | Model |', '|---|---|---|---|']
        L += [f"| `{a['name']}` | {short(a.get('purpose', ''))} | {a.get('status', '')} | {a.get('model', '')} |" for a in rows]
    L.append(END)
    return '\n'.join(L)


def put_block(path: Path, block: str):
    t = path.read_text() if path.exists() else ''
    if START in t and END in t:
        t = re.sub(re.escape(START) + r'.*?' + re.escape(END), lambda m: block, t, flags=re.S)
    else:
        t = t.rstrip('\n') + '\n\n' + block + '\n'
    path.write_text(t)


def render_md(d: dict) -> str:
    L = ['# Agent registry', '', f'Generated {date.today().isoformat()} by `bin/registry.py sync`. Source: `registry.yaml`. Rules: `CONVENTIONS.md`.', '',
         '## Registered agents', '']
    if d['agents']:
        L += ['| Agent | Placement | Folder | Job | Model | Reach | Status | Last review | Tests |', '|---|---|---|---|---|---|---|---|---|']
        for a in d['agents']:
            L.append(f"| `{a['name']}` | {a.get('placement', '')} | `{a.get('home', '')}/` | {short(a.get('purpose', ''), 70)} | {a.get('model', '')} | {', '.join(a.get('reach') or ['app'])} | {a.get('status', '')} | {a.get('last_review') or '—'} | {a.get('tests') or 'not run'} |")
    else:
        L.append('_None yet._')
    um = unmanaged(d)
    L += ['', '## Not yet following the requirements', '',
          'Helpers that exist on this Mac but are not in the registry. They are left alone until they are brought up to the requirements (or removed).', '']
    L += [f'- `{p}`' for p in um] or ['- none']
    L += ['', '## Client slug bases', ''] + [f'- `{k}/` → `{v}`' for k, v in sorted(d['clients'].items())]
    return '\n'.join(L) + '\n'


def sync():
    d = load()
    (AG / 'REGISTRY.md').write_text(render_md(d))
    homes = {a['home'] for a in d['agents']} | set(d['clients']) | {'Agents'}
    for h in sorted(homes):
        f = WS / h / 'README.md'
        if f.exists():
            put_block(f, block_for(d, h))
    return d


def clean_stale():
    """Replace the old per-project bot tables (for bots that no longer exist) with the managed block."""
    d = load()
    n = 0
    for h in sorted(d['clients']):
        base = d['clients'][h]
        for fname, heading in (('README.md', '## Project bots (scoped to this project only)'), ('AGENTS.md', '## Bots (project-scoped)')):
            f = WS / h / fname
            if not f.exists():
                continue
            t = f.read_text()
            if heading in t:
                t = re.sub(re.escape(heading) + r'.*?(?=\n## |\Z)', lambda m: block_for(d, h) + '\n', t, count=1, flags=re.S)
                n += 1
            if fname == 'AGENTS.md':
                t = re.sub(r'`' + re.escape(base) + r'-(?:memory-manager|document-engineer|orchestrator|jira-admin)`', 'an agent assigned to this folder', t)
            f.write_text(t)
    sync()
    print(f'replaced {n} stale bot tables; blocks synced')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['status', 'sync', 'clean-stale', 'review', 'set-status', 'find'])
    ap.add_argument('slug', nargs='?')
    ap.add_argument('value', nargs='?')
    ap.add_argument('--approved', action='store_true')
    ap.add_argument('--generic', action='store_true', help='find: list only definitions marked generic: yes')
    a = ap.parse_args()
    if a.cmd == 'sync':
        sync()
        print('synced REGISTRY.md and folder blocks')
    elif a.cmd == 'clean-stale':
        clean_stale()
    elif a.cmd == 'status':
        d = load()
        print(f"{len(d['agents'])} registered agent(s):")
        for x in d['agents']:
            print(f"  {x['name']:<34} {x.get('status', ''):<10} {x.get('home', '')}/  last review: {x.get('last_review') or '—'}  tests: {x.get('tests') or 'not run'}")
        print('not yet following the requirements:', ', '.join(unmanaged(d)) or 'none')
    elif a.cmd == 'review':
        d = load()
        x = find(d, a.slug or '')
        if not x:
            sys.exit('no such agent')
        x['last_review'] = date.today().isoformat()
        save(d)
        sync()
        print('review recorded for', a.slug)
    elif a.cmd == 'set-status':
        if a.value not in STATUSES:
            sys.exit(f'status must be one of {STATUSES}')
        if not a.approved:
            sys.exit('STOP: changing status needs Robi\'s clear yes (pass --approved only after he says it)')
        d = load()
        x = find(d, a.slug or '')
        if not x:
            sys.exit('no such agent')
        x['status'] = a.value
        x['updated'] = date.today().isoformat()
        save(d)
        sync()
        print(f'{a.slug} is now {a.value}')
    elif a.cmd == 'find':
        rows = discover(a.slug or '', generic_only=a.generic)
        if not rows:
            print('no matching definitions or instances found' if a.slug else 'no definitions or instances found at all')
            return
        for did, dd, instance_rows, tier, reason in rows:
            tier_txt = f'  [{tier}: {reason}]' if a.slug else ''
            print(f'{did}{tier_txt}')
            if dd is None:
                print('  definition: no brief found (instance-only; likely pre-dates the brief/registry split)')
            else:
                approved_txt = 'approved' if dd.get('approved') else 'NOT approved (draft or unmarked -- do not build from this file as-is)'
                caps = ', '.join(dd.get('capabilities') or []) or '(none tagged yet)'
                generic_txt = str(dd.get('generic', '')).lower() in ('yes', 'true')
                print(f'  definition: {approved_txt}; generic: {generic_txt}; capabilities: {caps}; brief: {dd["brief_file"]}')
            if instance_rows:
                for row in instance_rows:
                    pin = f" pinned={row['source_definition']}" if row.get('source_definition') else ''
                    print(f"  instance: {row['name']:<34} status={row.get('status')} folder={row.get('folder')}{pin}")
            else:
                print('  instance: none yet' + (' -- approved definition not yet instantiated' if dd and dd.get('approved') else ''))


if __name__ == '__main__':
    main()
