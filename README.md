# fairscape_lite

A local FAIRSCAPE metadata server. One SQLite file, one process, no auth.

Point it at RO-Crates already on your disk. It indexes them. You get a
web UI, search, and evidence graphs.

## Install

```bash
pip install -e .
cd web && npm install && npm run build && cd ..
```

## Run

```bash
uvicorn fairscape_lite.app:app --port 8000
```

Open http://localhost:8000 — that's the UI.

## Add your crates

```bash
curl -X POST localhost:8000/rocrate \
     -H 'Content-Type: application/json' \
     -d '{"path": "/data/my-crates"}'
```

A directory gets walked. A single `ro-crate-metadata.json` registers
just itself. Nothing is copied — the server indexes files where they are.

## Endpoints

| Endpoint | Does |
|---|---|
| `POST /rocrate` | register a crate file, or walk a directory |
| `GET /rocrate` | list registered crates |
| `GET /rocrate/metadata?id=` | a crate's metadata file, verbatim |
| `GET /rocrate/stale` | crates whose files moved or changed |
| `POST /rocrate/reingest` | re-read every registered crate |
| `DELETE /rocrate?id=` | forget a crate |
| `GET /ark:{naan}/{postfix}` | resolve an ARK |
| `GET /identifier?id=` | resolve any @id (URLs too) |
| `GET /entity?crate=&type=` | list entities, filterable |
| `GET /search?q=` | full-text search |
| `GET /evidencegraph/ark:{naan}/{postfix}` | provenance graph, built fresh |
| `GET /evidencegraph?id=` | same, for non-ARK @ids |
| `GET /ui/` | the web app |

## Settings (all optional)

| Env var | Default | Does |
|---|---|---|
| `FAIRSCAPE_LITE_DB` | `./fairscape.db` | where the index lives |
| `FAIRSCAPE_LITE_ROOT` | unset | only register crates under this directory. Set it if the port isn't localhost-only |

## Develop

```bash
pip install -e ".[test]"
pytest                     # 85 tests
cd web && npm run dev      # UI with hot reload on :5173
```

Read [SCHEMA.md](SCHEMA.md) before changing the database or graph code.
