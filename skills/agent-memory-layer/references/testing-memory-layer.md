# Testing a memory layer

Three layers of tests, in this order: contract, isolated lifecycle, live. The first two need no API key and must be green before a live call or a provider switch.

## 1. Mock contract test (no key)

Run a tiny HTTP server that accepts the exact payload and returns answers shaped like the real API. This catches payload and parsing bugs without spending tokens.

```python
class MockJev(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append({"headers": dict(self.headers), "body": body})
        answers = {}
        for name, q in body["questions"].items():
            if q["type"] == "noul":
                answers[name] = {"type": "noul", "noul": 0.9, "confidence": 0.9}
            elif q["type"] == "choice":
                pick = next(iter(q["criteria"]))
                answers[name] = {"type": "choice", "choice": pick, "confidence": 0.8}
            elif q["type"] == "score":
                answers[name] = {"type": "score", "score": 3, "confidence": 0.8}
        payload = json.dumps({"model": "mock", "answers": answers}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
```

Assert, not just “it responded”:

- `Authorization` is `Bearer <key>`.
- `model` is pinned, `state` is the object you sent, `questions.kind.type == "choice"` with criteria, `remember` is `noul`, `importance` is `score`.
- Choice/score/noul answers are parsed into the intended fields.
- A second identical classify is served from cache: request count does not increase and `cache_hits` increments.
- A contradiction (`supersede_0 >= 0.72`) returns the old uid in `superseded`, and recall excludes the old row.

## 2. Isolated lifecycle test

Never use the production home or port.

```python
home = Path.home() / ".hermes" / "cache" / "scratch" / ("jevmem-test-%d" % os.getpid())
port = free_port()  # bind(('127.0.0.1', 0)) then close
# write config.json with db_path=home/memory.db, port=port, idle_timeout_s=30
env = {**os.environ, "JEV_MEMORY_HOME": str(home), "JEV_MEMORY_PORT": str(port)}
proc = subprocess.Popen([sys.executable, "jevmemd.py", "--serve"], start_new_session=True, env=env)
```

Cover:

- retain → recall: text comes back with kind/tags/importance.
- short noise (`"ok thanks"`) is rejected by admission.
- exact/near duplicate is not stored twice.
- `forget` hides the row; `hard=true` removes it.
- MCP handshake: `initialize`, `notifications/initialized`, `tools/list`, `tools/call memory_stats`; process exits on stdin EOF.
- second instance exits without stealing the port.
- daemon is not a zombie and has no zombie children.
- idle daemon self-terminates and leaves no orphan process.
- bad model endpoint degrades in under a second and retain still works.

## 3. Stress and growth

- 300 **distinct** writes, 100 recalls. Measure p50/p95 and `db_bytes` from `/v1/stats`.
- Use random distinct words. Near-duplicate Jaccard (0.92) will collapse “same sentence with a different number” into one row; that is correct dedupe and not a growth test.
- Expected on the heuristic path: retain p95 ~3 ms, recall p95 ~3 ms, 300 rows ~336 KB. If `db_bytes` is several MB after a small run, checkpoint the WAL (`wal_autocheckpoint=256`) before blaming the schema.
- After the run, stop the daemon and remove `memory.db`, `-wal`, `-shm`; reapply `600` permissions when recreated.

## 4. Live test

```bash
cd ~/.hermes/memory-layer && python3 test_layer.py --live
```

- Read `TYPESAFE_API_KEY` from `~/.hermes/.env` explicitly (`load_env()` or a small parser). A plain `python3` run does **not** inherit Hermes's environment; without this the test prints `SKIP` and looks green.
- Expect a real classify, a preference classification, a tag, an admission, and a rerank. A 401/429 is a failure, not a skip.
- Keep live tests on an isolated port/home so a bad model call cannot corrupt production memory.

## Python version pitfall

On macOS, `python3` may be 3.9 while Hermes runs 3.14. Importing Hermes modules under 3.9 can fail at import time on runtime `str | object` expressions:

```text
TypeError: unsupported operand type(s) for |: 'type' and 'type'
```

`from __future__ import annotations` does not help — it postpones annotations, not expressions evaluated while importing. Use the interpreter the Hermes launcher uses (`~/.hermes/tools/python-*/bin/python3`, or `sys.executable` inside Hermes) for provider import tests.

## Harness hygiene

- `finally`: stop the daemon, `proc.wait(timeout=4)`, `kill()` on timeout, `shutil.rmtree(home)`.
- `ps` zombie checks: guard `len(parts) >= 3` before indexing; short/malformed rows exist.
- Wait for `/health` with a deadline (8 s) rather than `sleep(2)`.
- Free-port helper: bind to port 0, read the port, close; there is a tiny race, acceptable for a local test.
- Never run a test that calls `/v1/shutdown` against the user's live daemon unless that is the explicit intent.
