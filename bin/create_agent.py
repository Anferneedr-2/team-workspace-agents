#!/usr/bin/env python3
"""Build, update or retire a Hermes agent from an approved Agent Brief, organized like the remote Mac Mini.

  create_agent.py <brief.md> --dry-run                    check the brief, show exactly what would be created
  create_agent.py <brief.md> --approved [--smoke]         build (brief must say "Status: APPROVED by Robi on <date>")
  create_agent.py <brief.md> --update --approved          apply an approved brief to an existing helper (backs up first)
  create_agent.py --retire <slug> --approved              retire: delete the profile, keep the registry row and brief

The brief holds a ```build-spec block: `key: text` lines and `- item` lines (see Agents/skills/agent-requirements).
Rules: Agents/CONVENTIONS.md. After a build run:  check_agent.py <slug> --scenarios
Never creates timers, stores passwords, connects outside tools or messages anyone.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import registry as R  # noqa: E402

HOME, HERMES = R.HOME, R.HOME / '.hermes'
PROFILES, WS, AG = R.PROFILES, R.WS, R.AG
NAME_RE = re.compile(r'^[a-z][a-z0-9-]{1,40}$')
TEAM_RE = re.compile(r'^[A-Z][A-Za-z0-9]*(-[A-Za-z0-9]+)*$')
FENCE = re.compile(r'```(?:yaml )?build-spec\n(.*?)\n```', re.S)
LIST_KEYS = {'skills', 'instructions', 'never', 'ask_first', 'context', 'examples', 'toolsets_off', 'block_commands', 'connections', 'tests', 'reach',
             'capabilities', 'requires'}
ACTOR = os.environ.get('AGENT_ACTOR', 'agent-creator')


def fail(msg):
    sys.exit(f'STOP: {msg}')


def hermes(*args):
    return subprocess.run(['hermes', *args], capture_output=True, text=True)


def unwrap(v: str) -> str:
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in '"\'' else v


def parse_spec(block: str) -> dict:
    spec, cur = {}, None
    for raw in block.split('\n'):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        m = re.match(r'^([a-z_]+):\s*(.*)$', line)
        if m and not line.startswith((' ', '-')):
            cur, val = m.group(1), m.group(2).strip()
            if cur in LIST_KEYS:
                spec[cur] = []
                if val and val not in ('[]', '-'):
                    spec[cur].extend(v.strip() for v in val.split(',') if v.strip())
            else:
                spec[cur] = unwrap(val) if val else ''
            continue
        if cur is None:
            fail(f'build spec line has no key above it: {line.strip()[:60]}')
        s = line.strip()
        if cur in LIST_KEYS:
            if s.startswith('- '):
                spec[cur].append(unwrap(s[2:]))
            elif spec[cur]:
                spec[cur][-1] += ' ' + s
            else:
                fail(f'"{cur}" items must start with "- "')
        else:
            spec[cur] = (spec[cur] + ' ' + s).strip()
    return spec


def load_spec(brief: Path) -> dict:
    if not brief.is_file():
        fail(f'brief not found: {brief}')
    m = FENCE.search(brief.read_text())
    if not m:
        fail('no "```build-spec" block found in the brief')
    return parse_spec(m.group(1))


def check_spec(spec: dict, reg: dict) -> dict:
    s = {'model': 'claude-haiku-5-5', 'skills': [], 'skills_mode': 'lean', 'memory': 'builtin', 'never': [], 'ask_first': [], 'context': [],
         'examples': [], 'toolsets_off': [], 'block_commands': [], 'connections': [], 'tests': [], 'reach': ['app'],
         'capabilities': [], 'requires': []}
    s.update(spec)
    for k in ('name', 'placement', 'description', 'intent', 'role', 'instructions'):
        if not s.get(k):
            fail(f'build spec is missing "{k}"')
    if not NAME_RE.match(str(s['name'])):
        fail('name must be lowercase letters, numbers and hyphens (start with a letter)')
    for k in LIST_KEYS:
        if not isinstance(s[k], list):
            fail(f'"{k}" must be a list')
    if s['memory'] not in ('builtin', 'holographic'):
        fail('memory must be "builtin" or "holographic"')
    for rch in s['reach']:
        if rch not in ('app', 'telegram', 'terminal', 'agents'):
            fail('reach items must be from: app, telegram, terminal, agents')
    if s['skills_mode'] not in ('lean', 'standard'):
        fail('skills_mode must be "lean" or "standard"')
    for sk in s['skills']:
        if not (AG / 'skills' / sk / 'SKILL.md').is_file():
            fail(f'skill "{sk}" not found in {AG / "skills"}')
    kind, _, target = str(s['placement']).partition(':')
    if kind == 'client':
        if target not in reg['clients']:
            fail(f'unknown client "{target}". Known: {", ".join(sorted(reg["clients"]))}. A new client is added with bin/new_client.py and a slug base in registry.yaml')
        base = reg['clients'][target]
        if str(s['name']).startswith(base + '-'):
            fail(f'do not put the client name in "name"; it is added automatically (slug will be {base}-<name>)')
        folder, home, slug = WS / target, target, f'{base}-{s["name"]}'
        if not folder.is_dir():
            fail(f'client folder not found: {folder}')
    elif kind == 'team':
        if not TEAM_RE.match(target) or target in reg['clients']:
            fail('team folder must look like "Agents" or "Support-Desk" (capital first letter) and not be a client folder')
        folder, home, slug = WS / target, target, str(s['name'])
    else:
        fail('placement must be "client:<ClientFolder>" or "team:<TeamFolder>"')
    if len(slug) > 48:
        fail('the full agent name is too long (max 48 characters)')
    s.update(kind=kind, home=home, slug=slug, folder=folder)
    return s


def render_soul(s: dict) -> str:
    L = ['# Intent', str(s['intent']).strip(), '', '# Role', str(s['role']).strip(), '', '# Instructions']
    L += [f'- {i}' for i in s['instructions']]
    L += [f'- Never: {i}' for i in s['never']]
    L += [f'- Ask Robi first before: {i}' for i in s['ask_first']]
    L += [f'- Work only inside {s["folder"]}.',
          '- Get explicit approval from Robi before sending anything to other people, publishing, spending money, deleting files or writing to a shared system.',
          '- Never invent results. If work fails or something is missing, say so plainly and say what you need.',
          '- Keep answers short and in plain language unless Robi asks for detail.', '', '# Context']
    L += [f'- {i}' for i in s['context']] or ['- (none yet)']
    L += ['', '# Examples']
    L += [f'- {i}' for i in s['examples']] or ['- (none yet)']
    return '\n'.join(L) + '\n'


def memory_seed(s: dict, brief: Path) -> str:
    t = (f'I am {s["slug"]}. My job: {str(s["intent"]).strip()} I work only inside {s["folder"]}. '
         f'Never: {"; ".join(map(str, s["never"])) or "nothing extra listed"}. '
         f'Ask Robi first before: {"; ".join(map(str, s["ask_first"])) or "sending, publishing, spending or deleting"}. Brief: {brief}')
    if len(t) > 2000:
        fail(f'the memory note would be {len(t)} characters; Hermes keeps only 2,200. Shorten "intent", "never" or "ask_first".')
    return t + '\n'


def config_version() -> int:
    try:
        return int((yaml.safe_load((HERMES / 'config.yaml').read_text()) or {}).get('_config_version'))
    except Exception:
        return 52


FALLBACK_POLICY_FILE = AG / 'fallback-policy.yaml'


def validate_fallback_chain(chain, label: str):
    """Structural validation only -- provider/model presence and order, never a hard-coded
    list of 'valid' providers (that would bake provider names into this script, which is
    exactly what the centralized policy file exists to avoid)."""
    if not isinstance(chain, list) or not chain:
        fail(f'{label}: must be a non-empty list of provider/model entries')
    for i, entry in enumerate(chain):
        if (not isinstance(entry, dict) or not str(entry.get('provider') or '').strip()
                or not str(entry.get('model') or '').strip()):
            fail(f'{label}: entry #{i + 1} is missing "provider" or "model"')


def load_fallback_policy() -> dict:
    """Loads and validates Agents/fallback-policy.yaml. Fails clearly (never a silent
    no-op) on a missing file, invalid YAML, a missing/empty "chains" map, or any chain
    whose entries don't each carry a non-empty provider and model -- Decision 3."""
    if not FALLBACK_POLICY_FILE.is_file():
        fail(f'fallback policy file not found: {FALLBACK_POLICY_FILE} (required for the '
             f'default fallback policy -- create it, or set fallback_providers: none in this brief)')
    try:
        data = yaml.safe_load(FALLBACK_POLICY_FILE.read_text()) or {}
    except Exception as e:  # noqa: BLE001
        fail(f'fallback policy file is not valid YAML: {FALLBACK_POLICY_FILE} ({e})')
    chains = data.get('chains') if isinstance(data, dict) else None
    if not isinstance(chains, dict) or not chains:
        fail(f'fallback policy file has no non-empty "chains" map: {FALLBACK_POLICY_FILE}')
    for name, chain in chains.items():
        validate_fallback_chain(chain, f'{FALLBACK_POLICY_FILE} chain "{name}"')
    return data


def resolve_fallback_chain(name: str, policy: dict) -> list:
    chains = policy['chains']
    chain = chains.get(name)
    if chain is None:
        fail(f'fallback_providers: "{name}" is not a named chain in {FALLBACK_POLICY_FILE} '
             f'(known: {", ".join(sorted(chains))})')
    return chain


def fallback_plan_line(fb_requested, is_update: bool, exists: bool, existing_cfg: dict) -> str:
    """One line for the --dry-run plan describing exactly what will happen to
    fallback_providers -- shown even when nothing changes, so a silent update is never
    actually silent in the plan Robi reviews before approving (Decision 2)."""
    old_chain = (existing_cfg or {}).get('fallback_providers') if exists else None
    if is_update and fb_requested is None:
        return f'fallback_providers: unchanged, preserved as-is ({old_chain or "none configured"})'
    if fb_requested == 'none':
        new_chain = None
    else:
        policy = load_fallback_policy()
        new_chain = resolve_fallback_chain(fb_requested or 'default', policy)
    if is_update:
        return f'fallback_providers: CHANGE requested -- {old_chain!r} -> {new_chain!r}'
    return f'fallback_providers: {new_chain!r}' if new_chain else 'fallback_providers: none (explicit opt-out)'


def write_config(pdir: Path, s: dict, fresh: bool):
    cfgf = pdir / 'config.yaml'
    cfg = {} if fresh else (yaml.safe_load(cfgf.read_text()) or {})
    cfg['model'] = {'default': s['model'], 'provider': 'anthropic', 'base_url': 'https://api.anthropic.com'}
    cfg['_config_version'] = config_version()
    cfg.setdefault('terminal', {})['cwd'] = str(s['folder'])
    if s['toolsets_off']:
        cfg.setdefault('agent', {})['disabled_toolsets'] = list(s['toolsets_off'])
    elif 'agent' in cfg:
        cfg['agent'].pop('disabled_toolsets', None)
    if s['block_commands']:
        cfg.setdefault('approvals', {})['deny'] = list(s['block_commands'])

    fb_requested = s.get('fallback_providers')  # None when the brief says nothing about it
    if fresh:
        # Decision 1 + 2: every NEW profile gets the default policy unless explicitly opted
        # out. Decision 3: a missing/malformed policy file fails the build, never a silent omit.
        if fb_requested == 'none':
            cfg.pop('fallback_providers', None)
        else:
            policy = load_fallback_policy()
            cfg['fallback_providers'] = resolve_fallback_chain(fb_requested or 'default', policy)
    else:
        # Decision 2: an --update NEVER silently changes fallback behavior. Nothing here is
        # touched -- and the policy file is never even opened -- unless the brief explicitly
        # names a chain or "none". An unrelated instructions/skills update is unaffected.
        if fb_requested == 'none':
            cfg.pop('fallback_providers', None)
        elif fb_requested is not None:
            policy = load_fallback_policy()
            cfg['fallback_providers'] = resolve_fallback_chain(fb_requested, policy)
    cfgf.write_text(yaml.safe_dump(cfg, sort_keys=False))


def home_skeleton(s: dict, brief: Path):
    """Home folder for a team agent; for a client folder only Work/ and CHANGELOG.md are ensured."""
    f = s['folder']
    f.mkdir(parents=True, exist_ok=True)
    (f / 'Work').mkdir(exist_ok=True)
    if s['kind'] == 'team':
        if not (f / 'README.md').exists():
            (f / 'README.md').write_text(f'# {s["home"]}\n\nTeam folder (not a client). Home of the agents listed below.\n\nPurpose: {s["description"]}\n\nBrief: `{brief}`\nCreated: {date.today().isoformat()}\n')
        if not (f / 'AGENTS.md').exists():
            (f / 'AGENTS.md').write_text(
                f'# AGENTS.md — {s["home"]}\n\nTeam folder. Working directory for the agents listed in README.md.\n\n## Rules\n\n'
                '1. Work only inside this folder. Never read another client\'s folder.\n2. Drafts go in `Work/`. Approved outputs only after Robi approves.\n'
                '3. Every finished task: one entry in `CHANGELOG.md`, format `- [YYYY-MM-DD] [actor] what changed — detail`.\n'
                '4. Hand work to another agent with `hermes -p <slug> --in <folder> -z "<task>"` (`--in` is mandatory).\n5. Secrets never go in files.\n')
    if not (f / 'CHANGELOG.md').exists():
        (f / 'CHANGELOG.md').write_text(f'# {s["home"]} CHANGELOG\n\nAppend-only. Format: `- [YYYY-MM-DD] [actor] what changed — detail`\n\n## Entries\n\n')


def log(s: dict, line: str):
    for f in (s['folder'] / 'CHANGELOG.md', WS / 'CHANGELOG.md'):
        if f.exists():
            f.write_text(f.read_text().rstrip('\n') + f'\n- [{date.today().isoformat()}] [{ACTOR}] {line}\n')


def registry_entry(s: dict, brief: Path, old=None) -> dict:
    today = date.today().isoformat()
    e = {'name': s['slug'], 'role': s['name'], 'placement': s['kind'], 'home': s['home'], 'folder': str(s['folder']),
         'purpose': ' '.join(str(s['intent']).split()), 'owner': 'Robi', 'model': s['model'], 'skills': list(s['skills']),
         'skills_mode': s['skills_mode'], 'toolsets_off': list(s['toolsets_off']), 'memory': s['memory'],
         'connections': list(s['connections']), 'reach': list(s['reach']), 'brief': str(brief), 'status': (old or {}).get('status', 'testing'),
         'created': (old or {}).get('created', today), 'updated': today, 'last_review': (old or {}).get('last_review'),
         'tests': (old or {}).get('tests')}
    # Phase 2: optional reusable-definition metadata. Only added when the brief (or the
    # source_definition resolution below) actually supplies it, so an agent built from a
    # brief that doesn't use this feature gets a registry row byte-identical to before.
    for k in ('capabilities', 'generic', 'definition_id', 'definition_version', 'source_definition', 'requires', 'definition_hash'):
        if k in s and s[k] not in (None, '', [], {}):
            e[k] = s[k]
    return e


def resolve_definition(ag: Path, definition_id: str, version: str):
    """Find the file that holds a definition at a pinned version: the current (non-archived)
    brief if its own definition_version matches, else the matching -vN-archive.md. Returns
    None if neither exists -- a genuinely broken reference, caught before any build."""
    cur = ag / 'briefs' / f'{definition_id}.md'
    if cur.is_file():
        try:
            spec = load_spec(cur)
            if str(spec.get('definition_version', '')).strip() == str(version).strip():
                return cur
        except SystemExit:
            pass
    arc = ag / 'briefs' / f'{definition_id}-v{version}-archive.md'
    return arc if arc.is_file() else None


def check_source_definition(s: dict, ag: Path):
    """If this brief declares source_definition: <id>@<version>, resolve it and pin a
    content hash into s['definition_hash'] -- computed here, never authored by hand, so
    later drift checks compare against what was actually built from, not a guess."""
    sd = s.get('source_definition')
    if not sd:
        return
    did, _, version = str(sd).partition('@')
    if not did or not version:
        fail(f'source_definition "{sd}" must look like "<definition-id>@<version>"')
    resolved = resolve_definition(ag, did, version)
    if not resolved:
        fail(f'source_definition "{sd}" does not resolve to any known definition '
             f'(looked for {ag / "briefs" / (did + ".md")} with definition_version={version}, '
             f'or {ag / "briefs" / (did + "-v" + version + "-archive.md")})')
    import hashlib
    s['definition_hash'] = 'sha256:' + hashlib.sha256(resolved.read_text().encode()).hexdigest()


def gateway_serves(slug: str) -> str:
    try:
        return 'yes' if slug in json.loads((HERMES / 'gateway_state.json').read_text()).get('served_profiles', []) else 'not yet (the app may need a refresh)'
    except Exception:
        return 'unknown'


def do_retire(slug: str, approved: bool):
    if not approved:
        fail('retiring deletes the helper. Get Robi\'s clear yes, then pass --approved')
    reg = R.load()
    e = R.find(reg, slug)
    if not e:
        fail(f'"{slug}" is not in the registry, so I will not delete it')
    if (PROFILES / slug).exists():
        r = hermes('profile', 'delete', slug, '--yes')
        if r.returncode != 0:
            fail(f'could not delete the profile: {r.stdout[-200:]}{r.stderr[-200:]}')
        shutil.rmtree(PROFILES / slug, ignore_errors=True)
    e['status'], e['updated'] = 'retired', date.today().isoformat()
    R.save(reg)
    f = Path(e['folder'])
    for cl in (f / 'CHANGELOG.md', WS / 'CHANGELOG.md'):
        if cl.exists():
            cl.write_text(cl.read_text().rstrip('\n') + f'\n- [{date.today().isoformat()}] [{ACTOR}] Agent retired — `{slug}` (profile deleted; registry row and brief kept)\n')
    R.sync()
    print(f'RETIRED "{slug}". Registry row and brief are kept as history.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('brief', nargs='?')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--approved', action='store_true')
    ap.add_argument('--update', action='store_true')
    ap.add_argument('--smoke', action='store_true')
    ap.add_argument('--retire')
    a = ap.parse_args()
    if a.retire:
        return do_retire(a.retire, a.approved)
    if not a.brief:
        fail('give a brief file, or use --retire <slug>')
    if a.dry_run and a.approved:
        fail('use --dry-run alone, or --approved to build')
    if not a.dry_run and not a.approved:
        fail('use --dry-run to check, or --approved to build (add --update for an existing helper)')
    brief = Path(a.brief).expanduser()
    reg = R.load()
    s = check_spec(load_spec(brief), reg)
    check_source_definition(s, AG)  # Phase 2: resolve + pin source_definition before any further step
    slug, folder = s['slug'], s['folder']
    old = R.find(reg, slug)
    exists = (PROFILES / slug).exists()
    if not a.update:
        if exists:
            fail(f'a helper called "{slug}" already exists (see: hermes profile list). To change it, use --update with a re-approved brief')
        if old:
            fail(f'"{slug}" is already in the registry')
    else:
        if not exists:
            fail(f'--update needs an existing helper, but "{slug}" does not exist')
        if old and (old.get('home') != s['home'] or old.get('placement') != s['kind']):
            fail('placement cannot change on update. Retire and rebuild if it must move')
    if a.approved and not re.search(r'^Status:\s*APPROVED by Robi on \d{4}-\d{2}-\d{2}', brief.read_text(), re.M):
        fail('the brief does not say "Status: APPROVED by Robi on <date>". Get his clear yes first.')
    if shutil.which('hermes') is None:
        fail('the hermes command was not found')
    soul = render_soul(s)
    seed = memory_seed(s, brief)
    try:
        gw = json.loads((HERMES / 'gateway_state.json').read_text()).get('gateway_state')
        if gw != 'running':
            print(f'note: gateway state is "{gw}"; the helper will not answer in the app until it runs')
    except Exception:
        print('note: could not read the gateway state')

    plan = [f'{"update" if a.update else "create"} agent "{slug}" ({s["kind"]} agent in {s["home"]}/)', f'model {s["model"]}, memory {s["memory"]}, skills {s["skills_mode"]} + {", ".join(s["skills"]) or "none"}',
            f'works in: {folder}', f'toolsets turned off: {", ".join(s["toolsets_off"]) or "none"}; blocked commands: {len(s["block_commands"])}',
            'files: SOUL.md, config.yaml, memory note, home folder README/AGENTS/CHANGELOG, registry row, change-log entries',
            'not done here: timers, passwords, outside connections, messages']
    existing_cfg = {}
    if exists:
        try:
            existing_cfg = yaml.safe_load((PROFILES / slug / 'config.yaml').read_text()) or {}
        except Exception:
            existing_cfg = {}
    plan.append(fallback_plan_line(s.get('fallback_providers'), a.update, exists, existing_cfg))
    if a.dry_run:
        print('DRY RUN OK. Plan:\n- ' + '\n- '.join(plan) + '\n\n--- SOUL.md preview ---\n' + soul)
        return

    pdir = PROFILES / slug
    if not a.update:
        args = ['profile', 'create', slug, '--description', ' '.join(str(s['description']).split())]
        if s['skills_mode'] == 'lean':
            args.append('--no-skills')
        r = hermes(*args)
        if r.returncode != 0:
            fail(f'could not create the profile:\n{r.stdout[-300:]}{r.stderr[-300:]}')
    else:
        stamp = time.strftime('%Y%m%d-%H%M%S')
        bk = pdir / 'backups' / stamp
        bk.mkdir(parents=True, exist_ok=True)
        for rel in ('SOUL.md', 'config.yaml', 'memories/MEMORY.md'):
            if (pdir / rel).exists():
                shutil.copy2(pdir / rel, bk / Path(rel).name)
        print(f'backup saved: {bk}')
    try:
        (pdir / 'SOUL.md').write_text(soul)
        write_config(pdir, s, fresh=not a.update)
        if s['memory'] == 'holographic' and not a.update:
            r = hermes('-p', slug, 'plugins', 'install', 'holographic', '--yes-deps', '--enable')
            if 'holographic set as memory.provider' not in r.stdout:
                raise RuntimeError('memory plugin install failed:\n' + r.stdout[-300:])
        for sk in s['skills']:
            dst = pdir / 'skills' / sk
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(AG / 'skills' / sk, dst, ignore=shutil.ignore_patterns('__pycache__'))
        home_skeleton(s, brief)
        (pdir / 'memories').mkdir(exist_ok=True)
        if not a.update or not (pdir / 'memories' / 'MEMORY.md').exists():
            (pdir / 'memories' / 'MEMORY.md').write_text(seed)
        cfg = yaml.safe_load((pdir / 'config.yaml').read_text())
        assert cfg['terminal']['cwd'] == str(folder) and cfg['model']['default'] == s['model'], 'config check failed'
        if s['memory'] == 'holographic':
            assert cfg['memory']['provider'] == 'holographic', 'memory provider not set'
        if s['toolsets_off']:
            assert cfg['agent']['disabled_toolsets'] == s['toolsets_off'], 'toolsets not saved'
    except Exception as e:  # noqa: BLE001
        fail(f'build stopped half-way ({e}). "{slug}" exists but is incomplete. Remove it with: hermes profile delete {slug} --yes')

    adopt = a.update and not old
    entry = registry_entry(s, brief, old)
    reg['agents'] = [x for x in reg['agents'] if x['name'] != slug] + [entry]
    R.save(reg)
    log(s, f'Agent {"adopted into the registry and updated" if adopt else "updated" if a.update else "created"} — `{slug}` ({s["kind"]} agent, model {s["model"]}, brief {brief.name})')
    R.sync()
    smoke = ''
    if a.smoke:
        t = hermes('-p', slug, '--in', str(folder), '-z', 'In two short lines: what is your job, and which folder do you work in?')
        smoke = f'exit {t.returncode}: ' + (t.stdout or t.stderr).strip()[-500:]
    print(f'{"UPDATED" if a.update else "BUILT"} "{slug}"\n- {s["kind"]} agent, home folder: {folder}\n- model: {s["model"]} | memory: {s["memory"]} | status: {entry["status"]}\n'
          f'- registered in Agents/registry.yaml and listed in {s["home"]}/README.md\n- served by the gateway: {gateway_serves(slug)}\n'
          f'- talk to it: hermes -p {slug} --in {folder} -z "<your request>"  (or open it in the Hermes app)\n'
          f'- next: python3 {AG}/bin/check_agent.py {slug} --scenarios')
    if smoke:
        print('- smoke test answer:\n  ' + smoke.replace('\n', '\n  '))


if __name__ == '__main__':
    main()
