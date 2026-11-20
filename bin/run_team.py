#!/usr/bin/env python3
"""Deterministic coordinator for executing an Agents/teams/<project>.yaml team
against a lightweight execution plan, on top of Hermes's native Kanban.

HANDOFF PROTOCOL (current): a worker signals "I'm done, please verify" by
calling `kanban_block(kind='needs_input', reason=<HANDOFF_SENTINEL> + summary)`
-- NEVER `kanban_request_review`, NEVER `kanban_complete`. This replaced an
earlier review-lane design after live testing proved it was not reliably
preventable; see "Why not review-lane" below for the full evidence trail.

Verified native kanban semantics this design relies on (read from the
installed source -- hermes_cli/kanban_db.py, kanban_db_graph.py,
kanban_db_dispatch.py, kanban_workflow.py, tools/kanban_tools.py/schemas.py):

  - A child task is gated to 'ready' only when ALL parents are literally
    status == 'done' (kanban_db_graph.initial_task_state / recompute_ready,
    called again after every complete_task()).
  - `DEFAULT_WORKFLOW` (kanban_workflow.py) lists every task status:
    triage, todo, scheduled, ready, running, blocked, review, done, archived.
    The dispatcher's spawn loop (`_run_ready_and_review_lanes`) ONLY ever
    queries `ready` and `review` rows -- `blocked` is categorically absent
    from that query. This is a STRUCTURAL exclusion (the row is never even
    considered), not a late per-row filter that a snapshot can race past.
  - CONFIRMED LIVE (disposable board `block-handoff-test`, deleted after):
    created a task with a real resolvable assignee, called `kanban block
    <id> "..." --kind needs_input` (simulating the worker's own call), then
    ran a REAL `hermes kanban dispatch` while still assigned -> `spawned: []`
    and the task appears in NONE of the dispatcher's skip buckets -- it was
    never considered at all. No race window exists to win or lose.
  - `kanban_block` is a normal worker-callable lifecycle tool (same
    `_worker_guard` ownership pattern as `kanban_complete`,
    `_RUN_LIFECYCLE_TOOLS` in tools/kanban_tools.py) -- a worker can
    legitimately call it on its own task as a final action.
  - `block_task()`'s source: `running`/`ready` -> `blocked`, clears
    `claim_lock`/`claim_expires`/`worker_pid`, and closes the run with
    `outcome="blocked"` -- a value DISTINCT from a genuine crash/timeout/
    breaker-trip (`crashed`/`timed_out`/`spawn_failed`, set by the
    dispatcher's own `_record_task_failure`). This is the load-bearing
    discriminator `classify_blocked_task()` below relies on: `blocked`
    status is reachable by (a) a worker's intentional handoff, (b) a
    genuine execution failure the circuit breaker auto-blocked, or (c) a
    human/coordinator's own manual block -- and the run's `outcome` +
    `summary` (the block `reason`) are the ONLY way to tell them apart.
    Status alone is never trusted.
  - `kanban complete <id>` accepts `blocked` as a valid starting status with
    NO `--force` needed (confirmed live: no live claim to protect, since
    `block_task` already cleared it) -- "'ready' is accepted for manual CLI
    completion, 'review' for human approval" per the docstring, and `blocked`
    behaves the same way in practice (verified live: `complete` succeeded
    directly from `blocked`, child released `todo -> ready` immediately).
  - idempotency_key dedupes task CREATION only (an existing non-archived task
    with the same key is returned instead of a duplicate) -- it does NOT
    dedupe a retried worker's file-level side effects. Our own post-run file
    verification is the real safety net for that.
  - consecutive_failures is the circuit breaker; --max-retries N trips
    "block" on the Nth consecutive non-success (spawn_failed/timed_out/
    crashed); reset only by a real complete_task() success.
  - An ALREADY-blocked, already-typed task (block_kind already set, e.g. our
    own worker-handoff `needs_input` block) REFUSES a second `block_task()`
    call ("A typed block ... is still refused.") -- so a verification
    FAILURE on an already-blocked handoff task is recorded via `kanban
    comment`, not a second `block()` call; the task simply stays exactly
    where the worker left it, already fully dispatcher-inert.
  - On gateway/dispatcher restart, a 'running' task whose worker PID is dead
    is requeued to 'ready' on the next reconcile tick
    (reconcile_orphaned_running) -- never silently duplicated beside a still-
    alive worker. A 'blocked' task is untouched by ANY automatic
    reconciliation path at all (confirmed empirically: Robi's manual block of
    t_3525d5b6 survived a pause/resume/multi-session gap with zero native
    interference).

Why not review-lane (superseded design, kept for the record): `review` IS
scanned by the dispatcher, and `check_respawn_guard()`'s own source
deliberately disables its duplicate-work guard for the review lane ("a
recent completed run ... [is] the canonical *input* to a review handoff, not
a duplicate-work signal"). Combined with the dispatcher's row-scan being a
plain SELECT taken once per tick and acted on without re-validation, this
created a genuine, empirically-reproduced race: a live `hermes kanban
dispatch` was proven to claim and spawn a SECOND real worker against a
review-lane task that still carried its implementer assignee, before this
coordinator's own unassign call could land. Unassigning only closed the
window for FUTURE ticks, never a tick already in flight -- not a reliable
guarantee. The blocked-state handoff above has no such window because
`blocked` is never in the dispatcher's candidate set to begin with.

Design consequence: every task's instruction MUST end with the worker
calling `kanban_block(kind='needs_input', reason=HANDOFF_SENTINEL + ...)`,
never `kanban_request_review` or `kanban_complete`. This coordinator is the
ONLY caller of `kanban complete`, and only after BOTH (a) `classify_blocked_
task()` positively identifies the block as this exact kind of worker handoff
(never trusting status=='blocked' alone) and (b) its own deterministic file
check passes.

If a task is found 'done' without ever having been blocked first (i.e. the
worker self-completed, bypassing the handoff protocol entirely), this
coordinator still runs its safety-net check and reports an explicit ANOMALY,
hard-stopping the whole workflow, rather than treating it as silently fine --
it cannot un-complete an already-done kanban task.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# The worker's task instruction MUST tell it to include this exact phrase in
# its kanban_block `reason`. It is how classify_blocked_task() positively
# identifies "worker says it's done, please verify" apart from every other
# reason a task might legitimately be sitting in `blocked` (genuine crash/
# timeout circuit-breaker trip, a human's own manual block, or anything else
# -- none of which will ever contain this exact sentinel by chance).
HANDOFF_SENTINEL = 'HANDOFF: awaiting coordinator verification'

# Used only in `kanban comment` text when the coordinator itself records a
# failed verification against an already-blocked handoff task -- never in a
# new block() call (an already-typed blocked task refuses a second one).
COORDINATOR_FAILURE_NOTE = 'VERIFICATION FAILED (coordinator)'

# Run outcomes the dispatcher's own circuit breaker uses for a genuine
# execution failure -- never a worker's own intentional completion signal.
# 'gave_up' is the breaker's own terminal "exhausted retries" status
# (its metadata carries a `trigger_outcome`, e.g. spawn_failed/crashed/
# timed_out, naming the real failure that tripped it) -- confirmed live on a
# disposable board when this coordinator itself passed a bad relative
# `--workspace` path: the worker never started, outcome='gave_up',
# trigger_outcome='spawn_failed', and classify_blocked_task correctly
# refused to certify it (category was 'ambiguous' before this fix was
# added), hard-stopping with zero file mutation rather than guessing.
GENUINE_FAILURE_OUTCOMES = {'crashed', 'timed_out', 'spawn_failed', 'gave_up'}

TERMINAL_OK = {'done'}
# 'blocked' is deliberately NOT in here any more -- it is no longer a single
# meaning. classify_blocked_task() must run first; only its verdict decides
# whether a blocked task is a handoff, a genuine failure, or ambiguous.
TERMINAL_FAIL = {'crashed', 'timed_out', 'poll_timeout'}

POLL_INTERVAL_S = 2
POLL_TIMEOUT_S = 600


def fail(msg: str):
    raise SystemExit(f'ERROR: {msg}')


# --------------------------------------------------------------------------- #
# Team + plan loading / validation
# --------------------------------------------------------------------------- #

def load_team(team_path: Path) -> dict:
    if not team_path.is_file():
        fail(f'team manifest not found: {team_path}')
    return yaml.safe_load(team_path.read_text()) or {}


def approved_instances(team: dict) -> dict:
    """slug -> member dict, for every team member with a real, resolved
    `instance` (a member still only at `planned_instance` is not yet built
    and is never an eligible execution target)."""
    out = {}
    for m in team.get('members', []) or []:
        inst = m.get('instance')
        if inst:
            out[inst] = m
    return out


def load_plan(plan_path: Path) -> dict:
    if not plan_path.is_file():
        fail(f'execution plan not found: {plan_path}')
    plan = yaml.safe_load(plan_path.read_text()) or {}
    if not isinstance(plan.get('tasks'), list) or not plan['tasks']:
        fail(f'{plan_path}: "tasks" must be a non-empty list')
    ids = set()
    for t in plan['tasks']:
        if not t.get('id') or not t.get('agent') or not t.get('instruction'):
            fail(f'{plan_path}: every task needs id, agent, instruction')
        if t['id'] in ids:
            fail(f'{plan_path}: duplicate task id {t["id"]!r}')
        ids.add(t['id'])
    for t in plan['tasks']:
        for dep in t.get('depends_on', []) or []:
            if dep not in ids:
                fail(f'{plan_path}: task {t["id"]!r} depends_on unknown task {dep!r}')
    return plan


def topo_order(tasks: list) -> list:
    by_id = {t['id']: t for t in tasks}
    order, seen, visiting = [], set(), set()

    def visit(tid):
        if tid in seen:
            return
        if tid in visiting:
            fail(f'circular dependency involving task {tid!r}')
        visiting.add(tid)
        for dep in by_id[tid].get('depends_on', []) or []:
            visit(dep)
        visiting.discard(tid)
        seen.add(tid)
        order.append(by_id[tid])

    for t in tasks:
        visit(t['id'])
    return order


def validate_agents(plan: dict, team: dict) -> None:
    """One agent may run multiple tasks; multiple agents may run independent
    or dependent tasks -- this never assumes 1 member == 1 task. It only
    requires every referenced agent to be an approved, built team member."""
    instances = approved_instances(team)
    for t in plan['tasks']:
        if t['agent'] not in instances:
            fail(f'task {t["id"]!r} references agent {t["agent"]!r} which is not an '
                 f'approved, built team-member instance in this manifest')


# --------------------------------------------------------------------------- #
# Deterministic file verification (never an AI judgment call)
# --------------------------------------------------------------------------- #

@dataclass
class VerifyResult:
    ok: bool
    detail: str


def _hash_tree(project_dir: Path) -> dict:
    out = {}
    if not project_dir.is_dir():
        return out
    for f in project_dir.rglob('*'):
        if f.is_file():
            out[str(f.relative_to(project_dir))] = hashlib.md5(f.read_bytes()).hexdigest()
    return out


def verify_file_contains(project_dir: Path, path: str, pattern, forbid_other_changes: bool = False,
                          baseline_hashes: Optional[dict] = None) -> VerifyResult:
    """`pattern` is a single regex, or a list of explicitly PERMITTED alternative
    representations of the same real fact (e.g. "November 27, 2026" and
    "2026-11-27" for the same date) -- ANY one matching is a pass. This is not
    a loosened/fuzzy match: every alternative must still be listed explicitly
    in the plan ahead of time, so a wrong date or a different fact still fails
    -- only an accepted, pre-approved spelling of the SAME correct fact passes."""
    if not path:
        return VerifyResult(False, 'verify.path is required')
    patterns = [pattern] if isinstance(pattern, str) else list(pattern)
    if not patterns:
        return VerifyResult(False, 'verify.pattern is required (string or non-empty list)')
    target = project_dir / path
    if not target.is_file():
        return VerifyResult(False, f'expected output file missing: {path}')
    text = target.read_text()
    if not any(re.search(p, text) for p in patterns):
        return VerifyResult(False, f'{path} does not contain any permitted pattern: {patterns!r}')
    if forbid_other_changes and baseline_hashes is not None:
        now_hashes = _hash_tree(project_dir)
        changed = set()
        for rel, h in now_hashes.items():
            if rel == path:
                continue
            if baseline_hashes.get(rel) != h:
                changed.add(rel)
        if changed:
            return VerifyResult(False, f'unexpected file modification(s): {", ".join(sorted(changed))}')
    return VerifyResult(True, f'{path} verified: pattern matched, no unauthorized changes')


# --------------------------------------------------------------------------- #
# Execution report
# --------------------------------------------------------------------------- #

@dataclass
class TaskRun:
    task_id: str
    kanban_id: Optional[str] = None
    status: str = 'pending'
    verify: Optional[VerifyResult] = None
    note: str = ''


@dataclass
class ExecutionReport:
    project: str
    run_id: str
    dry_run: bool
    runs: list = field(default_factory=list)
    ok: bool = True

    def as_dict(self) -> dict:
        return {
            'project': self.project, 'run_id': self.run_id, 'dry_run': self.dry_run, 'ok': self.ok,
            'tasks': [
                {
                    'task_id': r.task_id, 'kanban_id': r.kanban_id, 'status': r.status,
                    'verify_ok': (r.verify.ok if r.verify else None),
                    'verify_detail': (r.verify.detail if r.verify else None),
                    'note': r.note,
                }
                for r in self.runs
            ],
        }


# --------------------------------------------------------------------------- #
# Blocked-task handoff identification -- NEVER trust status=='blocked' alone
# --------------------------------------------------------------------------- #

@dataclass
class HandoffVerdict:
    category: str   # 'handoff' | 'genuine_failure' | 'ambiguous'
    detail: str


def classify_blocked_task(backend, kid: str, expected_assignee: str) -> HandoffVerdict:
    """Every one of the required checks, applied in order, before anything
    downstream is allowed to act on a `blocked` task:
      - exactly one run exists (single-attempt policy; more is unexplained)
      - that run's outcome is not a genuine failure (crashed/timed_out/
        spawn_failed)
      - that run's outcome is literally 'blocked' (block_task's own marker --
        anything else is unrecognized and therefore not trusted)
      - that run's profile matches the assignee THIS coordinator dispatched
        the task to (not some other profile's leftover run)
      - the block reason contains HANDOFF_SENTINEL, never the coordinator's
        own COORDINATOR_FAILURE_NOTE and never a generic/missing reason
    Any failure of these checks returns 'ambiguous' (stop and report) except
    a confirmed genuine execution failure, which returns 'genuine_failure'
    (a normal, expected branch-only stop, not an anomaly)."""
    runs = backend.runs(kid)
    if not runs:
        return HandoffVerdict('ambiguous', 'task is blocked but has no run history at all')
    if len(runs) != 1:
        return HandoffVerdict('ambiguous',
                               f'expected exactly 1 run under the single-attempt policy, found {len(runs)}')
    run = runs[0]
    outcome = run.get('outcome')
    if outcome in GENUINE_FAILURE_OUTCOMES:
        return HandoffVerdict('genuine_failure',
                               f'latest run outcome is {outcome!r} -- a real execution failure, not a handoff')
    if outcome != 'blocked':
        return HandoffVerdict('ambiguous',
                               f'latest run outcome {outcome!r} is neither a known failure nor a worker handoff')
    profile = run.get('profile')
    if profile != expected_assignee:
        return HandoffVerdict('ambiguous',
                               f'latest run profile {profile!r} does not match the dispatched '
                               f'assignee {expected_assignee!r}')
    reason = run.get('summary') or ''
    if COORDINATOR_FAILURE_NOTE in reason:
        return HandoffVerdict('genuine_failure',
                               'this block carries the coordinator\'s own failure note, not a worker handoff')
    if HANDOFF_SENTINEL not in reason:
        return HandoffVerdict('ambiguous',
                               f'block reason does not identify a worker-completed handoff: {reason!r}')
    return HandoffVerdict('handoff', f'worker handoff confirmed: {reason!r}')


# --------------------------------------------------------------------------- #
# Coordinator
# --------------------------------------------------------------------------- #

def _poll_until_terminal(backend, kid: str, interval=POLL_INTERVAL_S, timeout=POLL_TIMEOUT_S) -> str:
    deadline = time.time() + timeout
    while True:
        status = backend.show(kid).get('status')
        if status in TERMINAL_OK or status in TERMINAL_FAIL or status == 'blocked':
            return status
        if time.time() >= deadline:
            return 'poll_timeout'
        time.sleep(interval)


FRESH_CREATE_STATUSES = {'ready', 'todo'}  # run_team.py never passes --initial-status, so a
# plain create_task() call can only ever return one of these two (verified live against the
# real installed CLI: an unparented create lands 'ready', a parented one lands 'todo'). Any
# other status returned means the idempotency key resolved to a task from a PRIOR invocation.


def reconcile_existing_task(backend, kid: str) -> dict:
    """Creation idempotency (did `create_task` return a pre-existing id?) is
    NOT execution idempotency (did that task already run, with real side
    effects?). Never assume a coordinator/gateway restart means no changes
    were made. 'blocked' is deliberately NOT auto-classified as unresumable
    here -- the caller must run `classify_blocked_task` to find out whether
    it is a legitimate pending handoff (fully resumable) or a genuine
    failure/ambiguous state."""
    row = backend.show(kid)
    status = row.get('status')
    previously_created = status not in FRESH_CREATE_STATUSES
    info = {'status': status, 'previously_created': previously_created, 'resumable': True, 'note': ''}
    if not previously_created:
        info['note'] = 'new task, no prior attempt to reconcile'
        return info
    if status in TERMINAL_FAIL:
        info['resumable'] = False
        info['note'] = (f'idempotency key already resolves to task {kid} in terminal state '
                         f'{status!r} from a PRIOR attempt -- not safe to just poll again; this '
                         f'run must stop and be investigated by a human before any retry')
    elif status == 'running':
        info['resumable'] = False
        info['note'] = (f'idempotency key resolves to task {kid} still "running" -- may be a live '
                         f'worker from a prior invocation or a zombie from a dead one; this coordinator '
                         f'does not guess which, and does not assume no file changes happened')
    else:
        info['note'] = f'idempotency key resolves to pre-existing task {kid} in resumable state {status!r}'
    return info


def _blocked_by_ancestor(tid: str, by_id: dict, failed_branches: set, _seen=None) -> bool:
    """True if `tid` or any transitive dependency is in `failed_branches`."""
    _seen = _seen or set()
    if tid in _seen:
        return False
    _seen.add(tid)
    for dep in by_id[tid].get('depends_on') or []:
        if dep in failed_branches or _blocked_by_ancestor(dep, by_id, failed_branches, _seen):
            return True
    return False


def _verify_and_certify(backend, kid: str, project_dir: Path, vcfg: dict,
                         baseline_hashes: dict, run: TaskRun) -> bool:
    """Runs the deterministic file check and, on pass, calls `kanban complete`;
    on failure, leaves the already-blocked task exactly where it is and
    records a `kanban comment` for the human. Returns True on success."""
    vr = verify_file_contains(
        project_dir, vcfg.get('path', ''), vcfg.get('pattern', '.'),
        forbid_other_changes=vcfg.get('forbid_other_changes', False),
        baseline_hashes=baseline_hashes,
    )
    run.verify = vr
    if vr.ok:
        backend.complete(kid, result=vr.detail)
        run.status = 'done'
        return True
    backend.comment(kid, f'{COORDINATOR_FAILURE_NOTE}: {vr.detail}')
    run.note = f'verification failed; left blocked for human review: {vr.detail}'
    return False


def run_plan(*, project: str, project_dir: Path, team: dict, plan: dict, backend,
             approved: bool, dry_run: bool, run_id: str) -> ExecutionReport:
    """Staged, dependency-gated execution on top of the blocked-state handoff
    protocol (see module docstring). A task is only CREATED in Kanban once
    every one of its declared dependencies has passed the coordinator's own
    verification and been explicitly completed BY THE COORDINATOR.

    Independent branches (no shared ancestor) are created and processed in
    the same "wave" when all are simultaneously eligible.

    A genuine execution failure or a failed verification stops only that
    task's own dependent branch; unrelated branches continue. Any AMBIGUOUS
    evidence (a blocked task classify_blocked_task cannot positively
    identify) or a self-completion bypass (status reaches 'done' without
    ever having been blocked first) stops the WHOLE workflow immediately --
    "if there is uncertainty about prior side effects or approval state,
    stop and report rather than guessing."

    Restart safety: idempotency keys are deterministic per (project, run_id,
    task_id). A task whose key already resolves to an existing kanban task is
    never blindly treated as fresh or as already-safe -- `reconcile_
    existing_task` classifies it, `classify_blocked_task` re-examines a
    pre-existing blocked task exactly as it would a freshly-observed one, and
    even an already-'done' task is re-verified against the real files before
    anything downstream is allowed to become eligible.
    """
    validate_agents(plan, team)
    tasks = plan['tasks']
    topo_order(tasks)  # cycle check only -- staged creation drives the real order
    by_id = {t['id']: t for t in tasks}
    report = ExecutionReport(project=project, run_id=run_id, dry_run=dry_run)

    if dry_run:
        for t in topo_order(tasks):
            report.runs.append(TaskRun(
                task_id=t['id'], status='planned',
                note=f"agent={t['agent']} depends_on={t.get('depends_on', [])}",
            ))
        return report

    if not approved:
        fail('real execution requires approved=True (explicit human go-ahead); refused')

    verified_ids: set = set()      # coordinator-verified-and-completed task ids
    created_kids: dict = {}        # task_id -> kanban id
    failed_branches: set = set()   # task ids whose own branch must not proceed further
    pending: set = set(by_id)
    baseline_hashes = _hash_tree(project_dir)
    hard_stop = False

    while pending and not hard_stop:
        eligible = sorted(
            tid for tid in pending
            if not _blocked_by_ancestor(tid, by_id, failed_branches)
            and all(d in verified_ids for d in (by_id[tid].get('depends_on') or []))
        )
        if not eligible:
            break

        for tid in eligible:
            pending.discard(tid)
            t = by_id[tid]
            vcfg = t.get('verify') or {}
            parents_kids = [created_kids[d] for d in (t.get('depends_on') or [])]
            kid = backend.create_task(
                title=tid, body=t['instruction'], assignee=t['agent'], parents=parents_kids,
                workspace=str(project_dir), project=project,
                idempotency_key=f'{project}:{run_id}:{tid}',
                max_runtime=t.get('max_runtime', '5m'), max_retries=t.get('max_retries', 1),
            )
            created_kids[tid] = kid
            run = TaskRun(task_id=tid, kanban_id=kid, status='created')
            report.runs.append(run)

            reconciled = reconcile_existing_task(backend, kid)
            run.note = reconciled['note']
            if not reconciled['resumable']:
                run.status = reconciled['status']
                failed_branches.add(tid)
                report.ok = False
                continue

            if reconciled['previously_created'] and reconciled['status'] == 'done':
                # Restart case: this task was already coordinator-verified and
                # completed in a PRIOR invocation. Never blindly trust that --
                # re-run the file check now before letting its children in.
                vr = (verify_file_contains(
                    project_dir, vcfg.get('path', ''), vcfg.get('pattern', '.'),
                    forbid_other_changes=vcfg.get('forbid_other_changes', False),
                    baseline_hashes=baseline_hashes,
                ) if vcfg else VerifyResult(True, 'no verify configured for this task'))
                run.verify = vr
                run.status = 'done'
                if vr.ok:
                    run.note += f'; resumed from a prior run, safety-net verify passed: {vr.detail}'
                    verified_ids.add(tid)
                else:
                    run.note = (f'ANOMALY: task already "done" from a prior run but fails the safety-net '
                                f'file check now ({vr.detail}) -- stopping rather than guessing')
                    failed_branches.add(tid)
                    report.ok = False
                baseline_hashes = _hash_tree(project_dir)
                continue

            if reconciled['previously_created'] and reconciled['status'] == 'blocked':
                # Restart case: a prior invocation got as far as the worker's
                # handoff (or a genuine failure) but never reached completion.
                # Re-classify exactly as the live-poll path below does --
                # resuming correctly, not blindly re-trusting or discarding it.
                verdict = classify_blocked_task(backend, kid, t['agent'])
                if verdict.category == 'ambiguous':
                    run.status = 'blocked'
                    run.note = f'ANOMALY: {verdict.detail} -- stopping the entire workflow'
                    report.ok = False
                    hard_stop = True
                    break
                if verdict.category == 'genuine_failure':
                    run.status = 'blocked'
                    run.note = f'resumed: {verdict.detail}; stopping this branch, no auto-retry'
                    failed_branches.add(tid)
                    report.ok = False
                    continue
                ok = _verify_and_certify(backend, kid, project_dir, vcfg, baseline_hashes, run)
                run.note = (run.note or '') + f'; resumed handoff: {verdict.detail}'
                if ok:
                    verified_ids.add(tid)
                else:
                    failed_branches.add(tid)
                    report.ok = False
                baseline_hashes = _hash_tree(project_dir)
                continue

            backend.dispatch()
            status = _poll_until_terminal(backend, kid)
            run.status = status

            if status in TERMINAL_FAIL:
                run.note = f'task ended in {status}; stopping this branch, no auto-retry'
                failed_branches.add(tid)
                report.ok = False
            elif status == 'blocked':
                verdict = classify_blocked_task(backend, kid, t['agent'])
                if verdict.category == 'ambiguous':
                    run.note = f'ANOMALY: {verdict.detail} -- stopping the entire workflow'
                    report.ok = False
                    hard_stop = True
                    break
                if verdict.category == 'genuine_failure':
                    run.note = f'{verdict.detail}; stopping this branch, no auto-retry'
                    failed_branches.add(tid)
                    report.ok = False
                else:
                    ok = _verify_and_certify(backend, kid, project_dir, vcfg, baseline_hashes, run)
                    if ok:
                        verified_ids.add(tid)
                    else:
                        failed_branches.add(tid)
                        report.ok = False
            elif status == 'done':
                # Self-completed, bypassing the handoff protocol entirely (never
                # blocked first). Still run the check for the report's sake, but
                # the stop is unconditional -- "do not create downstream tasks,
                # even if the output appears correct."
                vr = verify_file_contains(
                    project_dir, vcfg.get('path', ''), vcfg.get('pattern', '.'),
                    forbid_other_changes=vcfg.get('forbid_other_changes', False),
                    baseline_hashes=baseline_hashes,
                ) if vcfg else None
                run.verify = vr
                detail = f' (post-hoc check: {vr.detail})' if vr else ''
                run.note = ('ANOMALY: task self-completed via kanban_complete, bypassing the handoff '
                            'protocol' + detail + ' -- stopping the entire workflow; no further task, '
                            'in this or any other branch, will be created')
                report.ok = False
                hard_stop = True
                break
            baseline_hashes = _hash_tree(project_dir)
        # end for eligible
    # end while

    for tid in sorted(pending):
        report.runs.append(TaskRun(
            task_id=tid, status='skipped',
            note='never created: an ancestor failed/blocked, or the workflow hard-stopped on an anomaly',
        ))
    return report


# --------------------------------------------------------------------------- #
# Real backend: thin subprocess wrapper around the installed `hermes kanban`
# CLI. Never used by tests (those use the in-memory FakeKanban) -- exercised
# live only via small isolated-board contract tests, never against real
# Lighthouse agents from this module.
# --------------------------------------------------------------------------- #

class RealKanbanCLI:
    def __init__(self, board: str):
        self.board = board

    def _run(self, args, check=True):
        import subprocess
        cmd = ['hermes', 'kanban', '--board', self.board] + args
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if check and res.returncode != 0:
            fail(f'kanban command failed: {" ".join(cmd)}\n{res.stderr or res.stdout}')
        return res.stdout

    def create_task(self, *, title, body, assignee, parents, workspace, project,
                     idempotency_key, max_runtime, max_retries):
        import json
        if not Path(workspace).is_absolute():
            fail(f'workspace path must be absolute, got {workspace!r} -- a relative path is '
                 f'ambiguous against the dispatcher\'s own CWD and will fail the worker\'s spawn')
        args = ['create', title, '--body', body, '--workspace', f'dir:{workspace}',
                '--idempotency-key', idempotency_key, '--max-runtime', str(max_runtime),
                '--max-retries', str(max_retries), '--json']
        if assignee:
            args += ['--assignee', assignee]
        for p in parents:
            args += ['--parent', p]
        out = self._run(args)
        return json.loads(out)['id']

    def dispatch(self):
        self._run(['dispatch'], check=False)

    def show(self, task_id):
        import json
        out = self._run(['show', task_id, '--json'])
        return json.loads(out)['task']

    def runs(self, task_id):
        """Full run history (profile, outcome, summary=reason, ...) -- the
        basis for classify_blocked_task()'s identification checks."""
        import json
        out = self._run(['show', task_id, '--json'])
        return json.loads(out).get('runs') or []

    def complete(self, task_id, result=None):
        args = ['complete', task_id]
        if result:
            args += ['--result', result]
        self._run(args)
        return True

    def comment(self, task_id, text):
        self._run(['comment', task_id, text])
        return True

    def unassign(self, task_id):
        self._run(['assign', task_id, 'none'])
        return True

    def block(self, task_id, reason=None, kind='needs_input'):
        args = ['block', task_id, reason or 'verification failed', '--kind', kind]
        self._run(args)
        return True


# --------------------------------------------------------------------------- #
# CLI entrypoint
# --------------------------------------------------------------------------- #

def _default_run_id() -> str:
    return time.strftime('%Y%m%d-%H%M%S')


def main(argv=None):
    import argparse
    import json as _json

    ap = argparse.ArgumentParser(
        prog='run_team.py',
        description='Deterministic coordinator: executes an execution plan against an '
                     'approved Agents/teams/<project>.yaml team, on Hermes native Kanban.')
    ap.add_argument('--project', required=True, help='Project name, matches the team manifest\'s project')
    ap.add_argument('--team', help='Path to Agents/teams/<project>.yaml (default: Agents/teams/<project>.yaml)')
    ap.add_argument('--plan', required=True, help='Path to the execution-plan YAML')
    ap.add_argument('--project-dir', help='Project working directory (default: inferred from --plan\'s sibling, '
                                           'or must be passed explicitly)')
    ap.add_argument('--board', default=None, help='Kanban board slug (default: "<project-slug>"; '
                                                    'created if missing)')
    ap.add_argument('--run-id', default=None, help='Run identifier, used in every idempotency key '
                                                     '(default: a timestamp -- pass a fixed value to '
                                                     'make a restart resume the SAME run)')
    ap.add_argument('--dry-run', action='store_true', help='Print the plan, call nothing, change nothing')
    ap.add_argument('--approved', action='store_true', help='Explicit human go-ahead for a REAL run; '
                                                              'required unless --dry-run')
    ap.add_argument('--json', action='store_true', help='Emit the final report as JSON')
    a = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent  # .../Agents
    team_path = Path(a.team) if a.team else (root / 'teams' / f'{a.project}.yaml')
    plan_path = Path(a.plan)
    project_dir = (Path(a.project_dir) if a.project_dir else (root.parent / a.project)).resolve()
    # project_dir MUST be absolute before it reaches RealKanbanCLI.create_task's
    # `--workspace dir:<path>` -- a relative path is ambiguous against the
    # dispatcher's own CWD and fails the worker's spawn before it ever starts
    # (confirmed live: outcome='gave_up', trigger_outcome='spawn_failed', zero
    # file mutation, caught cleanly by classify_blocked_task as 'ambiguous'
    # rather than silently certified -- but it should never happen in the
    # first place, hence this explicit .resolve()).

    team = load_team(team_path)
    plan = load_plan(plan_path)
    run_id = a.run_id or _default_run_id()

    if a.dry_run:
        report = run_plan(project=a.project, project_dir=project_dir, team=team, plan=plan,
                           backend=None, approved=False, dry_run=True, run_id=run_id)
    else:
        if not a.approved:
            fail('a real run requires --approved (explicit human go-ahead); refused')
        board = a.board or re.sub(r'[^a-z0-9-]+', '-', a.project.lower())
        backend = RealKanbanCLI(board)
        report = run_plan(project=a.project, project_dir=project_dir, team=team, plan=plan,
                           backend=backend, approved=True, dry_run=False, run_id=run_id)

    if a.json:
        print(_json.dumps(report.as_dict(), indent=2))
    else:
        print(f'Project: {report.project}  run_id: {report.run_id}  dry_run: {report.dry_run}  ok: {report.ok}')
        for r in report.runs:
            print(f'  - {r.task_id}: {r.status}'
                  + (f'  [{r.verify.detail}]' if r.verify else '')
                  + (f'  ({r.note})' if r.note else ''))
    if not report.ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
