#!/usr/bin/env python3
"""Create a client/project folder (or complete an existing one) with its 4 bots.

  new_client.py <ProjectDir> <slugbase> [--source <path> ...]

Idempotent: existing files are never overwritten (AGENTS.md and README.md only gain the missing
Folder map / Working folders sections). --source adds a symlink under Sources/ to an existing repo.
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from agentlib import *  # noqa: F401,F403

ap = argparse.ArgumentParser()
ap.add_argument('project')
ap.add_argument('base')
ap.add_argument('--source', action='append', default=[])
ap.add_argument('--with-jira', action='store_true', help='also enable the optional Jira tool (Jira/ + <base>-jira-admin)')
a = ap.parse_args()
name, base = a.project, a.base
assert re.fullmatch(r'[a-z0-9]+', base), 'slug base must be lowercase alphanumeric'
T = AG / 'templates' / 'project'
D = WS / name
existing = projects()
is_new = name not in existing
siblings = ', '.join(f'`../{p}/`' for p in sorted(set(existing) | {name}) if p != name)
kw = dict(Project=name, base=base, date=today(), WS=WS, siblings=siblings or 'any other project folder')

# 1. folder from template (never overwrite)
for src in sorted(T.rglob('*')):
    rel = src.relative_to(T)
    dst = D / rel
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
    elif not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(render(src.read_text(), **kw))
# existing AGENTS.md / README.md: add the new sections if missing
t_ag, t_rd = render((T / 'AGENTS.md').read_text(), **kw), render((T / 'README.md').read_text(), **kw)
ag, rd = (D / 'AGENTS.md').read_text(), (D / 'README.md').read_text()
if '## Folder map' not in ag:
    sec = t_ag[t_ag.index('## Folder map'):t_ag.index('## Handoff')]
    ag = ag.replace('## Handoff', sec + '## Handoff', 1)
    ag = re.sub(r'Writes are confined to this directory: `README.md`[^\n]*?`Jira/`\.', 'Writes are confined to this directory, following the Folder map below.', ag)
if '## Working folders' not in rd:
    sec = t_rd[t_rd.index('## Working folders'):t_rd.index('## Project bots')]
    rd = rd.replace('## Project bots (scoped to this project only)', sec + '## Project bots (scoped to this project only)', 1)
    rd = rd.replace('- Workspace hub (living doc):', f'- Agent repository (reusable roles, template, hire script): `{WS}/Agents/`\n- Workspace hub (living doc):', 1)
(D / 'AGENTS.md').write_text(ag)
(D / 'README.md').write_text(rd)

# 2. sibling lists in every project's AGENTS.md
allp = sorted(set(existing) | {name})
for p in allp:
    f = WS / p / 'AGENTS.md'
    others = ', '.join(f'`../{o}/`' for o in allp if o != p)
    f.write_text(re.sub(r'including (`\.\./[^`]+`(?:, `\.\./[^`]+`)*)', 'including ' + others, f.read_text()))

# 3. sources
for s in a.source:
    sp = Path(s).expanduser()
    assert sp.exists(), f'source not found: {sp}'
    link = D / 'Sources' / sp.name
    if not link.exists() and not link.is_symlink():
        link.symlink_to(sp)

# 4. the 4 project bots from roles/project
soul = (PROFILES / 'governor' / 'SOUL.md').read_text()
for rf in sorted((AG / 'roles' / 'project').glob('*.yaml')):
    role = yaml.safe_load(rf.read_text())
    slug = render(role['slug'], **kw)
    if (PROFILES / slug).exists():
        print('exists, left untouched', slug)
        continue
    create_profile(slug, ' '.join(render(role['description'], **kw).split()), render(role['cwd'], **kw), soul, render(role['memory_seed'], **kw))
    print('ready', slug)

# 5. hub README rows + counts (only when the project is new to the hub)
hub = WS / 'README.md'
t = hub.read_text()
if is_new:
    ref = sorted(existing)[0]
    ref_base = existing[ref]
    out = []
    for ln in t.split('\n'):
        out.append(ln)
        if re.match(rf'^\| `?{ref}`? \|', ln):
            out.append(ln.replace(ref, name).replace(ref_base, base).replace('2026-11-04', today()))
    t = '\n'.join(out)
    t = re.sub(r'(\*\*Current projects:\*\* [^\n]*?)( \(scaffolded)', rf'\1, `{name}`\2', t, count=1)
    hub.write_text(t)
    cl = WS / 'CHANGELOG.md'
    cl.write_text(cl.read_text().rstrip('\n') + f'\n- [{today()}] [claude-code] Project `{name}` added via Agents/bin/new_client.py — folder from template + 4 bots (`{base}-*`)\n')
    pc = D / 'CHANGELOG.md'
    pc.write_text(pc.read_text().rstrip('\n') + f'\n- [{today()}] [claude-code] Project created from Agents/templates/project; bots `{base}-*` created\n')

print('governance:')
run_governance()
sync_counts()
if a.with_jira:
    import subprocess
    subprocess.run(['/usr/bin/python3', str(Path(__file__).parent / 'enable_jira.py'), name], check=True)
