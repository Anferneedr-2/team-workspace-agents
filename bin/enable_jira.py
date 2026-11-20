#!/usr/bin/env python3
"""Jira is an optional tool, not a client default.

  enable_jira.py <ProjectDir>              add Jira/ + the <base>-jira-admin bot to one client
  enable_jira.py <ProjectDir> --remove     take them away (refuses if Jira/ has real entries, unless --force)
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from agentlib import *  # noqa: F401,F403

OPT = AG / 'optional' / 'jira'


def folder_is_pristine(d: Path, kw: dict) -> bool:
    for f in (OPT / 'Jira').rglob('*'):
        if f.is_file():
            g = d / 'Jira' / f.relative_to(OPT / 'Jira')
            if not g.exists() or g.read_text() != render(f.read_text(), **kw):
                return False
    return not any(p for p in (d / 'Jira').rglob('*') if p.is_file() and not (OPT / 'Jira' / p.relative_to(d / 'Jira')).exists())


def hub_rows(project: str, base: str, add: bool):
    hub = WS / 'README.md'
    t = hub.read_text()
    slug = f'{base}-jira-admin'
    if add:
        row = f'| {project} | `{slug}` | This project\'s Jira board only | ✅ {today()} |'
        if row not in t:
            t = re.sub(r'(\| Project \| Profile slug \| Board scope \| Status \|\n\|[-| ]+\|\n)((?:\|[^\n]*\n)*)', lambda m: m.group(1) + m.group(2) + row + '\n', t, count=1)
    else:
        t = '\n'.join(l for l in t.split('\n') if not l.startswith(f'| {project} | `{slug}` |'))
        t = t.replace(f', `{slug}`', '')
    hub.write_text(t)


ap = argparse.ArgumentParser()
ap.add_argument('project')
ap.add_argument('--remove', action='store_true')
ap.add_argument('--force', action='store_true')
a = ap.parse_args()
pm = projects()
assert a.project in pm, f'unknown project {a.project}; known: {sorted(pm)}'
proj, base = a.project, pm[a.project]
D, slug = WS / proj, f'{pm[a.project]}-jira-admin'
siblings = ', '.join(f'`../{p}/`' for p in sorted(pm) if p != proj)
kw = dict(Project=proj, base=base, date=today(), WS=WS, siblings=siblings)

if a.remove:
    if (D / 'Jira').exists() and not (a.force or folder_is_pristine(D, kw)):
        sys.exit(f'{proj}/Jira has real entries; re-run with --force to delete it anyway')
    if (PROFILES / slug).exists():
        hermes('profile', 'delete', slug, '--yes', check=False)
        shutil.rmtree(PROFILES / slug, ignore_errors=True)
    shutil.rmtree(D / 'Jira', ignore_errors=True)
    for name in ('AGENTS.md', 'README.md'):
        f = D / name
        f.write_text(strip_jira_text(f.read_text()))
    hub_rows(proj, base, add=False)
    cl = D / 'CHANGELOG.md'
    cl.write_text(cl.read_text().rstrip('\n') + f'\n- [{today()}] [claude-code] Jira disabled — removed Jira/ and `{slug}` (Jira is an optional tool: Agents/bin/enable_jira.py)\n')
    print('Jira removed from', proj)
else:
    assert not (PROFILES / slug).exists(), f'{slug} already exists'
    for src in sorted((OPT / 'Jira').rglob('*')):
        dst = D / 'Jira' / src.relative_to(OPT / 'Jira')
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(render(src.read_text(), **kw))
    role = yaml.safe_load((OPT / 'role.yaml').read_text())
    soul = (PROFILES / 'governor' / 'SOUL.md').read_text()
    create_profile(render(role['slug'], **kw), ' '.join(render(role['description'], **kw).split()), render(role['cwd'], **kw), soul, render(role['memory_seed'], **kw))
    ag = (D / 'AGENTS.md').read_text().split('\n')
    bots_hdr = next(i for i, l in enumerate(ag) if l.startswith('## Bots'))
    last = max(i for i, l in enumerate(ag) if l.startswith('| ') and i > bots_hdr and i < next(j for j, x in enumerate(ag) if j > bots_hdr and x.startswith('## ') and not x.startswith('## Bots')))
    ag.insert(last + 1, f'| Jira Admin | `{slug}` | this board only; `Jira/activity-log.md`; warn `bundy` on conflicts |')
    fm = next((i for i, l in enumerate(ag) if l.startswith('| `README.md`, `AGENTS.md`')), None)
    if fm is not None:
        ag.insert(fm + 2, f'| `Jira/` | board living doc + activity log (Jira is enabled for this project) | `{slug}` |')
    (D / 'AGENTS.md').write_text('\n'.join(ag))
    rd = (D / 'README.md').read_text().split('\n')
    rb = next(i for i, l in enumerate(rd) if l.startswith('## Project bots'))
    rl = max(i for i, l in enumerate(rd) if l.startswith('| ') and i > rb)
    rd.insert(rl + 1, f"| Jira Admin | `{slug}` | This project only — its Jira board + `Jira/activity-log.md`; warns `bundy` of conflicts, overlaps, impossible entries |")
    (D / 'README.md').write_text('\n'.join(rd))
    hub_rows(proj, base, add=True)
    cl = D / 'CHANGELOG.md'
    cl.write_text(cl.read_text().rstrip('\n') + f'\n- [{today()}] [claude-code] Jira enabled — added Jira/ and `{slug}` via Agents/bin/enable_jira.py\n')
    print('Jira enabled for', proj)

print('governance:')
run_governance()
sync_counts()
