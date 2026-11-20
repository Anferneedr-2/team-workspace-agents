# Hindsight knowledge-base pages (compiled layer)

Hindsight's local server already carries a compiled knowledge layer. Read this before designing any
"wiki", "knowledge base" or "compiled memory" work — building a parallel store duplicates it.

Bank path always includes the tenant segment `default`:
`http://127.0.0.1:9177/v1/default/banks/{bank_id}/...`

## Endpoints (from the server's own `/openapi.json`)

| Operation | Call |
|---|---|
| Tree of folders/pages | `GET .../knowledge-base/tree` |
| Create folder | `POST .../knowledge-base/folders` |
| Create page | `POST .../knowledge-base/pages` |
| Read / update / delete node | `GET .../knowledge-base/pages/{page_id}`, `PATCH` / `DELETE .../knowledge-base/nodes/{node_id}` |
| Hybrid search over pages | `GET .../knowledge-base/search?q=&limit=&tags=&tags_match=&tag_groups=` (BM25 + vector) |
| Markdown bundle of the whole KB | `GET .../knowledge-base/export` |
| List memories | `GET .../memories/list?type=&q=&document_id=&entity_id=&tags=&tags_match=&time_field=&start_date=&end_date=&limit=&offset=` |
| Stats / graph / entities | `GET .../stats`, `.../graph`, `.../entities` |
| Mental models | `GET/POST .../mental-models`, `POST .../{id}/refresh`, `.../dry-run-refresh`, `.../clear` |

## What a page actually is

`CreatePageRequest` = `name` (required), `source_query`, `parent_id`, `tags`.

A page is a **saved query over memories**, rendered by the server's LLM — not a markdown document
you write. `tags` **scope** the memory set; they are not labels. Default matching is `all_strict`:
a memory must carry **every** tag, and untagged memories are excluded entirely. A `type:<x>` tag
sets the page's rendered type. Mental models are the same idea with explicit refresh triggers.

So the design split is: memories = raw/episodic, KB pages = compiled/projection, export = the
interop artifact (git, humans, agents with no MCP client). Never hand-write a second wiki beside it.

## Observed bank state (probe, not assumption)

`GET .../stats` is the cheapest orientation call — it returns `total_nodes`, `total_links`,
`total_documents`, `nodes_by_fact_type` (`world`/`experience`/`observation`), link counts by type,
`last_consolidated_at`, `pending_operations`.

Auto-retained memories come back from `memories/list` with `tags: ["session:<sha256>"]` only, and
`entities` as a comma-separated string (`"user, Hermes, Obsidian"`); `context` is a one-line
provenance string. Explicit bridge `retain` is the only writer of `kind:` / `domain:` /
`sensitivity:` tags.

## Pitfalls

- **Invented tags render an empty page.** With `all_strict` scoping, a topic tag that no memory
  carries matches nothing, and the page looks like a rendering bug rather than a scope bug.
- **The automatic gate path drops the facets.** `~/.hermes/plugins/jev/` overrides `sync_turn` and
  delegates to `super().sync_turn(...)` with no tags, so per-turn memories never gain `kind:` /
  `domain:`. Annotate before delegating whenever pages are meant to scope on those facets.
- **Tag backfill is unproven.** The provider's `update_memory` cannot add tags or metadata. Whether
  HTTP `PATCH /memories/{id}` accepts them is untested — round-trip one memory before promising a
  backfill job to the user.
- **Rendering costs a server LLM call.** Refresh pages on a memory-count delta, never on every write.
- **`format=json` on sibling endpoints is not always the shape you expect** (memory search returns a
  bare array of paths, not snippet objects). Parse one live response before writing the client.

## Probe recipe

```bash
curl -s http://127.0.0.1:9177/openapi.json -o /tmp/hs.json    # ~350 KB, authoritative
python3 -c "import json;d=json.load(open('/tmp/hs.json'));print('\n'.join(sorted(d['paths'])))"
python3 -c "import json;d=json.load(open('/tmp/hs.json'));print(json.dumps(d['components']['schemas']['CreatePageRequest'],indent=1))"
```

Read the schema rather than guessing field names — the `tags` description in `CreatePageRequest` is
where the `all_strict` scoping rule is documented.
