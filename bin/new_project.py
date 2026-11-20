#!/usr/bin/env python3
"""Initialize a client project folder from Agents/templates/project and register it in
Agents/registry.yaml's clients: map. Creates ZERO agent profiles -- agent instantiation
stays exclusively create_agent.py + an approved brief + check_agent.py. No dependency on
Governor/ or any remote-governance structure (see ../../REMOTE-REFERENCE-INDEX.md).

  new_project.py "<Client>" <slugbase> --dry-run     show the plan, create nothing
  new_project.py "<Client>" <slugbase> --approved    create the folder + register the client

Safe to run twice: an existing file is never overwritten; re-running on an already
registered client reports it and makes no change.
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import registry as R  # noqa: E402  -- the established registry load/save/backup interface

TEMPLATE = R.AG / 'templates' / 'project'
BASE_RE = re.compile(r'^[a-z0-9]+$')
NAME_RE = re.compile(r'^[A-Z][A-Za-z0-9-]*$')


def fail(msg):
    sys.exit(f'STOP: {msg}')


def render(text: str, **kw) -> str:
    for k, v in kw.items():
        text = text.replace('{{' + k + '}}', str(v))
    return text


def plan_issues(name: str, base: str, reg: dict, folder: Path) -> list:
    issues = []
    if not NAME_RE.match(name):
        issues.append('project folder name must start with a capital letter (letters, numbers, hyphens)')
    if not BASE_RE.match(base):
        issues.append('slug base must be lowercase letters and numbers only')
    if name in reg['clients']:
        issues.append(f'"{name}" is already a registered client (base "{reg["clients"][name]}")')
    elif base in reg['clients'].values():
        issues.append(f'slug base "{base}" is already used by another client')
    return issues


def template_files():
    if not TEMPLATE.is_dir():
        fail(f'template folder not found: {TEMPLATE}')
    return sorted(TEMPLATE.rglob('*'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('base')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--approved', action='store_true')
    a = ap.parse_args()
    if a.dry_run and a.approved:
        fail('use --dry-run alone, or --approved to create (not both)')
    if not a.dry_run and not a.approved:
        fail('use --dry-run to check, or --approved to create')

    reg = R.load()
    folder = R.WS / a.project
    issues = plan_issues(a.project, a.base, reg, folder)

    to_write = []
    for src in template_files():
        rel = src.relative_to(TEMPLATE)
        dst = folder / rel
        if not src.is_dir() and not dst.exists():
            to_write.append(str(dst))

    plan = [
        f'{"create" if not folder.exists() else "complete (folder already exists)"} project folder: {folder}',
        f'register client: "{a.project}" -> "{a.base}" in Agents/registry.yaml clients:',
        f'files to be written (never overwriting an existing file): {len(to_write)}',
        'agent profiles created: NONE -- build agents later via create_agent.py + an approved brief',
        'no Governor/ script, governance.yaml, or remote structure is touched',
    ]
    if issues:
        plan.append('ISSUES (must resolve before --approved): ' + '; '.join(issues))

    if a.dry_run:
        print('DRY RUN OK. Plan:\n- ' + '\n- '.join(plan))
        if to_write:
            print('\nFiles that would be written:')
            for f in to_write:
                print(' ', f)
        return

    if issues:
        fail('cannot proceed: ' + '; '.join(issues))

    kw = dict(Project=a.project, base=a.base, date=date.today().isoformat(), WS=str(R.WS))
    written = []
    for src in template_files():
        rel = src.relative_to(TEMPLATE)
        dst = folder / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(render(src.read_text(), **kw))
            written.append(str(dst))

    # Register the client through the SAME load/save every other registry write uses --
    # R.save() backs up registry.yaml automatically before writing (Phase 1 mechanism).
    reg['clients'][a.project] = a.base
    R.save(reg)

    for cl in (folder / 'CHANGELOG.md', R.WS / 'CHANGELOG.md'):
        if cl.exists():
            cl.write_text(cl.read_text().rstrip('\n') +
                           f"\n- [{date.today().isoformat()}] [new_project.py] Project `{a.project}` initialized "
                           f"(slug base `{a.base}`); client registered in Agents/registry.yaml. No agents created.\n")

    R.sync()
    print(f'CREATED project "{a.project}" (base: {a.base})\n- folder: {folder}\n'
          f'- files written: {len(written)}\n- client registered in Agents/registry.yaml\n'
          f'- agent profiles created: 0\n'
          f'- next: build project agents with create_agent.py from an approved brief, '
          f'placement: client:{a.project}')


if __name__ == '__main__':
    main()
