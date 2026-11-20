#!/usr/bin/env python3
"""Hire (instantiate) an existing specialist for ONE client/project.

  hire_agent.py <specialist-profile> <ProjectDir>        e.g. hire_agent.py seo-audit-bot SimplySource

Creates profile <base>-<specialist> that: starts in the client folder, has its own memory, copies the
specialist's persona (SOUL.md) and extra skills (never .env/credentials), and is registered in
Agents/instances.yaml + governance. Undo with:  hire_agent.py --fire <base>-<specialist>
"""
import argparse
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from agentlib import *  # noqa: F401,F403

ap = argparse.ArgumentParser()
ap.add_argument('agent', nargs='?')
ap.add_argument('project', nargs='?')
ap.add_argument('--fire', metavar='INSTANCE')
ap.add_argument('--relock', action='store_true', help='write the governance lock after validation (only after you approve)')
a = ap.parse_args()

if a.fire:
    items = load_instances()
    hit = [i for i in items if i['profile'] == a.fire]
    assert hit, f'{a.fire} is not a hired instance'
    hermes('profile', 'delete', a.fire, '--yes', check=False)
    shutil.rmtree(PROFILES / a.fire, ignore_errors=True)
    save_instances([i for i in items if i['profile'] != a.fire])
    D = WS / hit[0]['project']
    ag = D / 'AGENTS.md'
    ag.write_text('\n'.join(l for l in ag.read_text().split('\n') if f'`{a.fire}`' not in l))
    cl = D / 'CHANGELOG.md'
    cl.write_text(cl.read_text().rstrip('\n') + f'\n- [{today()}] [claude-code] Specialist removed — `{a.fire}` (instance deleted, Agents/instances.yaml updated)\n')
    print('removed', a.fire)
    run_governance(a.relock)
    sync_counts()
    sys.exit(0)

assert a.agent and a.project, 'usage: hire_agent.py <specialist> <ProjectDir>'
proj, agent = a.project, a.agent
pm = projects()
assert proj in pm, f'unknown project {proj}; known: {sorted(pm)}'
base = pm[proj]
src = PROFILES / agent
assert src.is_dir() and not agent.startswith(('_', '.')), f'no such specialist profile: {agent}'
team = {p for b in pm.values() for p in [f'{b}-{s}' for s in ('orchestrator', 'memory-manager', 'document-engineer', 'jira-admin')]}
assert agent not in team | {'governor', 'memory-manager', 'project-orchestrator', 'document-engineer', 'assistant', 'bundy'}, 'hire specialists, not team bots'
slug = f'{base}-{agent}'
assert not (PROFILES / slug).exists(), f'{slug} already exists'
D = WS / proj

# persona + description
spec_desc = ' '.join(((yaml.safe_load((src / 'profile.yaml').read_text()) or {}).get('description') or agent).split()) if (src / 'profile.yaml').exists() else agent
desc = f'{spec_desc} Instance of {agent} hired for {proj} only.'
soul = (src / 'SOUL.md').read_text() if (src / 'SOUL.md').exists() else (PROFILES / 'governor' / 'SOUL.md').read_text()
soul = soul.rstrip('\n') + f'''

# Instance scope ({slug})
- You are the {proj} instance of the specialist `{agent}`. Work only inside `{D}`; never read or write another client's folder.
- Put drafts in `Work/`; approved outputs go to `Deliverables/` only after Robi approves. Client card and marketing data: `Marketing/` (CLIENT.md).
- Ignore any output path, client path or reporting line in your original persona that points outside `{D}`: you report to `{base}-orchestrator`.
- Follow `{D}/AGENTS.md`. Log every finished task with the task-changelog skill into `{D}/CHANGELOG.md`.
'''
seed = (f"Scope: {proj} only ({D}). Role: hired specialist, instance of {agent}. Never read or inject another project's docs, Jira, memory or context. "
        f"Logging duty: after every finished task append exactly one entry to {D / 'CHANGELOG.md'} via the task-changelog skill, format '- [YYYY-MM-DD] [{slug}] what changed — detail'. "
        f'Handoff to another bot: hermes -p <slug> --in <scope-dir> -z "<task>" (--in is mandatory). Read AGENTS.md in your scope at session start.')

# create, then carry over the specialist's extra skills (those a fresh profile does not already have)
create_profile(slug, desc, D, soul, seed)
have = {p.parent.relative_to(PROFILES / slug / 'skills') for p in (PROFILES / slug / 'skills').rglob('SKILL.md')}
extra = [p.parent for p in (src / 'skills').rglob('SKILL.md') if p.parent.relative_to(src / 'skills') not in have]
for sdir in extra:
    rel = sdir.relative_to(src / 'skills')
    dst = PROFILES / slug / 'skills' / rel
    shutil.rmtree(dst, ignore_errors=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(sdir, dst, ignore=shutil.ignore_patterns('__pycache__'))
print(f'ready {slug} (+{len(extra)} specialist skills copied)')

# register
items = load_instances()
items.append({'profile': slug, 'agent': agent, 'project': proj, 'hired': today()})
save_instances(items)
ag = (D / 'AGENTS.md').read_text().split('\n')
idx = max(i for i, l in enumerate(ag) if l.startswith('| ') and i < next((j for j, x in enumerate(ag) if x.startswith('## Handoff')), len(ag)) and i > next(j for j, x in enumerate(ag) if x.startswith('## Bots')))
ag.insert(idx + 1, f'| Specialist (hired) | `{slug}` | instance of `{agent}`; this project only; outputs to `Work/` then `Deliverables/` |')
(D / 'AGENTS.md').write_text('\n'.join(ag))
cl = D / 'CHANGELOG.md'
cl.write_text(cl.read_text().rstrip('\n') + f'\n- [{today()}] [claude-code] Specialist hired — `{slug}` (instance of `{agent}`), registered in Agents/instances.yaml\n')
print('governance:')
run_governance(a.relock)
sync_counts()
