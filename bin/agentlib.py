"""Shared helpers for new_client.py and hire_agent.py. Stdlib + PyYAML (system python3 has it)."""
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import yaml

HOME = Path.home()
WS = HOME / 'Team-Workspace'
AG = WS / 'Agents'
PROFILES = HOME / '.hermes' / 'profiles'
EXEMPT_DIRS = {'Bundy', 'Governor', 'Agents'}
MODEL = {'default': 'claude-haiku-5-5', 'provider': 'anthropic', 'base_url': 'https://api.anthropic.com'}
FOLDERS = ['Memory', 'Work', 'Deliverables', 'Marketing', 'Research', 'Data', 'Assets', 'Sources']


def today() -> str:
    return date.today().isoformat()


def render(text: str, **kw) -> str:
    for k, v in kw.items():
        text = text.replace('{{' + k + '}}', str(v))
    return text


def hermes(*args, check=True):
    r = subprocess.run(['hermes', *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f'hermes {" ".join(args[:4])} failed:\n{r.stdout[-400:]}\n{r.stderr[-400:]}')
    return r


def profile_cwd(slug: str) -> str:
    try:
        cfg = yaml.safe_load((PROFILES / slug / 'config.yaml').read_text()) or {}
    except Exception:
        return ''
    return str((cfg.get('terminal') or {}).get('cwd') or '')


def projects() -> dict:
    """{ProjectDir: slugbase}, derived from each project orchestrator's cwd (same rule as the Governor)."""
    out = {}
    for p in sorted(PROFILES.iterdir()):
        if p.is_dir() and p.name.endswith('-orchestrator') and p.name != 'project-orchestrator':
            cwd = Path(profile_cwd(p.name) or '/nonexistent')
            if cwd.parent == WS and cwd.name not in EXEMPT_DIRS:
                out[cwd.name] = p.name[: -len('-orchestrator')]
    return out


def create_profile(slug, description, cwd, soul, memory_seed, extra_skills=()):
    """Create (if missing) and fully configure one Team-Workspace profile. extra_skills: [(src_dir, rel_path)]."""
    if not (PROFILES / slug).exists():
        hermes('profile', 'create', slug, '--description', description)
    pd = PROFILES / slug
    (pd / 'SOUL.md').write_text(soul)
    (pd / 'config.yaml').write_text(yaml.safe_dump(
        {'model': dict(MODEL), '_config_version': 52, 'terminal': {'cwd': str(cwd)}}, sort_keys=False))
    skills = [(AG / 'skills' / 'task-changelog', 'task-changelog')] + list(extra_skills)
    for src, rel in skills:
        dst = pd / 'skills' / rel
        shutil.rmtree(dst, ignore_errors=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__'))
    r = hermes('-p', slug, 'plugins', 'install', 'holographic', '--yes-deps', '--enable')
    if 'holographic set as memory.provider' not in r.stdout:
        raise SystemExit(f'memory plugin install failed for {slug}:\n{r.stdout[-300:]}')
    (pd / 'memories').mkdir(exist_ok=True)
    (pd / 'memories' / 'MEMORY.md').write_text(memory_seed + '\n')
    cfg = yaml.safe_load((pd / 'config.yaml').read_text())
    assert cfg['terminal']['cwd'] == str(cwd) and cfg['memory']['provider'] == 'holographic', slug


def load_instances() -> list:
    f = AG / 'instances.yaml'
    return (yaml.safe_load(f.read_text()) or {}).get('instances') or []


def save_instances(items: list):
    (AG / 'instances.yaml').write_text(
        '# Agents hired for a specific client/project (written by bin/hire_agent.py; read by Governor/build_governance.py).\n'
        + yaml.safe_dump({'instances': items}, sort_keys=False, width=140, allow_unicode=True))


def run_governance(write_lock=False):
    py = '/usr/bin/python3'
    b = subprocess.run([py, str(WS / 'Governor' / 'build_governance.py')], capture_output=True, text=True)
    v = subprocess.run([py, str(WS / 'Governor' / 'validate_governance.py')] + (['--write-lock'] if write_lock else []), capture_output=True, text=True)
    lines = [l for l in v.stdout.splitlines() if 'ERROR' in l or l.startswith('governance:')]
    print('\n'.join(lines) or v.stdout[-400:])
    return v.returncode == 0


def sync_counts():
    """Rewrite the bot/profile counts in the hub README from the live governance.yaml (after a build)."""
    gov = yaml.safe_load((WS / 'governance.yaml').read_text())
    n = len(gov['bots'])
    pn = n - 6
    hub = WS / 'README.md'
    t = hub.read_text()
    m = re.search(r'6 top-level \+ (\d+) project-scoped = (\d+)', t)
    if not m:
        return
    old_p, old_n = m.group(1), m.group(2)
    if old_n == str(n):
        return
    for x, y in [(f'6 top-level + {old_p} project-scoped = {old_n}', f'6 top-level + {pn} project-scoped = {n}'),
                 (f'6 top-level + {old_p} project-scoped', f'6 top-level + {pn} project-scoped'),
                 (f'{old_n} profiles', f'{n} profiles'), (f'all {old_n} ', f'all {n} '), (f'{old_n} bots', f'{n} bots'),
                 (f'{old_n} records', f'{n} records'), (f'on the {old_n} profiles', f'on the {n} profiles')]:
        t = t.replace(x, y)
    hub.write_text(t)
    print(f'README counts synced: {old_n} -> {n}')


def strip_jira_text(t: str) -> str:
    """Remove the default-Jira wording from a project README.md / AGENTS.md (name-agnostic)."""
    out = []
    for ln in t.split('\n'):
        if re.match(r'^\| Jira Admin \|', ln) or re.match(r'^\| `Jira/` \|', ln) or re.match(r'^\| Specialist.*jira', ln):
            continue
        ln = ln.replace("another project's docs, Jira, memory, or context", "another project's docs, memory, or context")
        ln = ln.replace('`Jira/ Memory/', '`Memory/')
        ln = ln.replace(', and §3.5 (Jira).', ' and §3.3 (documents).').replace('§3.3 (documents), and §3.5 (Jira).', '§3.3 (documents).')
        ln = re.sub(r'^- Jira activity → `Jira/activity-log.md`; time/schedules', '- Time/schedules', ln)
        ln = ln.replace(' / `Jira/README.md`', '')
        out.append(ln)
    return '\n'.join(out)
