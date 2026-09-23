# fairscape_lite

A local FAIRSCAPE metadata server. One SQLite file and one fastapi process.

Point it at a directory already containing RO-Crates. It indexes them. You get a
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

Open http://localhost:8000, that's the UI.

## Add your crates

```bash
curl -X POST localhost:8000/rocrate \
     -H 'Content-Type: application/json' \
     -d '{"path": "/data/my-crates"}'
```

A directory gets walked. A single `ro-crate-metadata.json` registers
just itself. Nothing is copied — the server indexes files where they are.

No shared path? Upload the crate instead:

```bash
curl -F file=@my-crate.zip localhost:8000/rocrate/upload
```

The zip is unpacked verbatim under `uploads/` (wrapping folder and all)
and then registered like any other path. Because nothing inside is
moved or renamed, a crate-relative `contentUrl` — `file:///data/x.csv`
or `data/x.csv`, both meaning "next to my ro-crate-metadata.json" —
still points at the right file. The response says where the crate
landed and which of its local references resolve there:

```json
{"crate": "ark:59852/rocrate-…", "kind": "zip",
 "directory": "/srv/fairscape/uploads/ark-59852-rocrate-…-1a2b3c4d",
 "path": "/srv/fairscape/uploads/ark-59852-rocrate-…-1a2b3c4d/my-crate/ro-crate-metadata.json",
 "files": {"local": 12, "found": 12, "missing": []}, "registered": [ … ]}
```

Later, `GET /rocrate/files?id=…` answers "where is the file for dataset
X" for any registered crate. Uploading a crate again replaces it in
place; uploading a bare `ro-crate-metadata.json` for a crate you already
uploaded replaces just that file and keeps the data.

## Endpoints

| Endpoint                                  | Does                                       |
| ----------------------------------------- | ------------------------------------------ |
| `POST /rocrate`                           | register a crate file, or walk a directory |
| `POST /rocrate/upload`                    | upload a crate zip (or bare metadata file) |
| `GET /rocrate`                            | list registered crates                     |
| `GET /rocrate/files?id=`                  | a crate's local files, resolved on disk    |
| `GET /rocrate/metadata?id=`               | a crate's metadata file, verbatim          |
| `GET /rocrate/stale`                      | crates whose files moved or changed        |
| `POST /rocrate/reingest`                  | re-read every registered crate             |
| `DELETE /rocrate?id=&purge=`              | forget a crate (`purge` deletes an upload) |
| `GET /ark:{naan}/{postfix}`               | resolve an ARK                             |
| `GET /identifier?id=`                     | resolve any @id (URLs too)                 |
| `GET /entity?crate=&type=`                | list entities, filterable                  |
| `GET /search?q=`                          | full-text search                           |
| `GET /entity/links?id=`                   | edges into and out of one @id              |
| `GET /evidencegraph/ark:{naan}/{postfix}` | provenance graph, built fresh              |
| `GET /evidencegraph?id=`                  | same, for non-ARK @ids                     |
| `GET /ui/`                                | the web app                                |

## Settings (all optional)

| Env var               | Default          | Does                                                                               |
| --------------------- | ---------------- | ---------------------------------------------------------------------------------- |
| `FAIRSCAPE_LITE_DB`   | `./fairscape.db` | where the index lives                                                              |
| `FAIRSCAPE_LITE_ROOT` | unset            | only register crates under this directory. Set it if the port isn't localhost-only |
| `FAIRSCAPE_LITE_UPLOADS` | `./uploads`   | where uploaded crates are unpacked                                                 |
| `FAIRSCAPE_LITE_MAX_UNPACKED` | 8 GiB    | refuse a zip that would unpack past this many bytes                                |

## Develop

```bash
pip install -e ".[test]"
pytest                     # 128 tests
cd web && npm run dev      # UI with hot reload on :5173
```

Read [SCHEMA.md](SCHEMA.md) before changing the database or graph code.
