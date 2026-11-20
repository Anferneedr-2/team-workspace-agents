# Sidecar daemon patterns for a memory layer

A memory layer shared by several agents should be one on-demand process, not one per agent and not an always-on service. These are the mechanics that keep it from bloating, double-binding, or leaving zombies.

## Single instance

```python
import fcntl

handle = open(str(home / "jevmemd.lock"), "a+")
try:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    handle.close()
    return 0  # another instance owns the service
```

Hold the handle for the life of the process. A second daemon exits **0**; it must not bind the port or open a second writer. The lock file itself is not the state — the flock is.

## Spawn without creating a zombie

Never let a long-lived agent process be the direct parent of a daemon that may outlive the turn. Use a short-lived launcher:

```python
launcher = subprocess.Popen(
    [
        sys.executable, "-c",
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable, sys.argv[1], '--serve'],"
        " stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,"
        " stderr=open(sys.argv[2], 'ab'),"
        " start_new_session=True, close_fds=True)",
        sys.executable, str(daemon_path), str(log_path),
    ],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,
    close_fds=True,
)
launcher.wait(timeout=5)
```

The launcher exits immediately; the daemon is reparented to init/launchd. If the agent spawns the daemon directly, the daemon becomes a child of a process that never calls `waitpid`, and an idle exit leaves `<defunct>` behind. Guard the spawn with a second lock (`spawn.lock`) so concurrent clients do not start duplicates.

## Idle exit

Run a ticker in the accept loop:

```python
if (STATE.job_queue.empty()
        and time.monotonic() - STATE.last_request > cfg["idle_timeout_s"]):
    server.shutdown()
```

Also require the writer queue to be empty; otherwise a queued retain is dropped. On shutdown, put a `None` sentinel in the queue, join the writer, remove the pid file, and release the lock. A 15-minute idle timeout is a good default: long enough to survive a working session, short enough that nothing lingers overnight.

## SQLite

```python
conn = sqlite3.connect(db_path, timeout=3.0, isolation_level=None)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=3000")
conn.execute("PRAGMA temp_store=MEMORY")
conn.execute("PRAGMA wal_autocheckpoint=256")
```

- `wal_autocheckpoint=256` matters: the default 1000 pages plus an uncheckpointed WAL made a 60-write test look like 3.3 MB; after checkpointing it was 156 KB.
- One connection per request, closed in `finally`. **`with sqlite3.connect(...)` commits but does not close**; use `contextlib.closing` or explicit `close()`.
- A single writer thread owns writes; readers can use short-lived connections.
- FTS5: `CREATE VIRTUAL TABLE memories_fts USING fts5(text, summary, tags, entities, tokenize='porter unicode61')`. Keep it in sync explicitly or with triggers; query with `bm25()` and a `MATCH` expression built from alphanumeric tokens.

## Writer queue

```python
job_queue = queue.Queue(maxsize=64)
```

- Explicit `remember` is synchronous and returns the decision.
- Turn capture is `retain_async`: enqueue a dict, return `202` immediately.
- On `queue.Full`, drop the job and increment a `dropped` counter; never block the request thread.
- The writer catches per-job exceptions and keeps the loop alive; one bad row must not kill retention.

## Timeouts, breaker, cache

- Write deadline: 3.0 s. Recall deadline: 1.8 s. Both are hard; the request thread passes a `deadline` into the client.
- Semaphore (`BoundedSemaphore`) caps concurrent model calls (4 is enough for a personal machine).
- After 5 consecutive failures, open the circuit for 60 s and skip the network entirely.
- Cache key: SHA-256 of the full JSON payload (`model`, `state`, `questions`) with a 30-day TTL. Store the parsed answer, not the raw body.
- One retry only for `429`/`5xx`; never retry a `401`.

## Recall pipeline

1. Build an FTS5 `MATCH` query from the user query; if empty, fall back to importance/recency.
2. Fetch 24 candidates with `bm25` weights (text 1.0, summary 0.5, tags 2.0, entities 1.5).
3. Rerank at most 16 with one `rel_<n>` `noul` question each, in one request.
4. Final score: 60% model relevance + 40% local (importance, recency half-life 45 days, trust).
5. Return 8 by default, 25 max. Exclude `secret` unless `include_secret=true`.

## HTTP server

- `ThreadingHTTPServer` with `daemon_threads=True`, `timeout=0.5` so the idle ticker runs.
- Bind `127.0.0.1`; optional bearer token only if the service is exposed beyond loopback.
- Cap request body size and validate JSON before touching SQLite.
- `/health` is unauthenticated and returns version, pid, model, circuit state, and queue depth.
- `/v1/shutdown` is a POST so a browser prefetch cannot stop the service.

## Process hygiene checks

```bash
ps aux | grep jevmemd | grep -v grep || echo "no jevmemd running"
lsof -nP -iTCP:8791 -sTCP:LISTEN
```

- After `stop`, both should be empty.
- After an idle test, check for `<defunct>` children and a missing pid file.
- Do not install a launchd/systemd unit by default; on-demand spawn plus idle exit is the feature.
- Log rotation: 1 MB × 2 files, so a long-lived log cannot grow without bound.
