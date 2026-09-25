# fairscape-lite

A small FAIRSCAPE server you run yourself: one FastAPI process and one SQLite
file. Point it at a folder of RO-Crates and you get a web UI, search, ARK
resolution and evidence graphs.

It is the self-hosted **publish** step of [FAIRSCAPE](https://fairscape.github.io),
next to [fairscape_publish](https://github.com/fairscape/fairscape_publish),
which pushes crates to public repositories.

## Install

```bash
git clone https://github.com/fairscape/fairscape_lite && cd fairscape_lite
pip install -e .
cd web && npm install && npm run build && cd ..
```

## Example

```bash
uvicorn fairscape_lite.app:app --port 8000
```

Register a folder of crates. The server indexes them where they are and copies
nothing:

```bash
curl -X POST localhost:8000/rocrate -H 'Content-Type: application/json' \
     -d '{"path": "/data/my-crates"}'
```

Or upload a zipped crate:

```bash
curl -F file=@my-crate.zip localhost:8000/rocrate/upload
```

Then open http://localhost:8000/ui/.

## Endpoints

| Endpoint | Does |
|---|---|
| `POST /rocrate` | Registers a crate file, or indexes every crate in a folder |
| `POST /rocrate/upload` | Uploads a crate zip (or a bare metadata file) |
| `GET /rocrate` | Lists registered crates |
| `GET /search?q=` | Full-text search |
| `GET /ark:{naan}/{postfix}` | Resolves an ARK |
| `GET /evidencegraph/ark:{naan}/{postfix}` | Returns the provenance graph |
| `GET /entity/links?id=` | Returns the edges into and out of one `@id` |
| `GET /rocrate/files?id=` | Returns a crate's local files, found on disk |
| `DELETE /rocrate?id=` | Removes a crate from the index |

The full list is at `/docs` while the server is running.

## Settings

| Env var | Default | Does |
|---|---|---|
| `FAIRSCAPE_LITE_DB` | `./fairscape.db` | Where the index is stored |
| `FAIRSCAPE_LITE_ROOT` | unset | Only register crates under this folder. Set it if the port is open beyond localhost. |
| `FAIRSCAPE_LITE_UPLOADS` | `./uploads` | Where uploaded crates are unpacked |
| `FAIRSCAPE_LITE_MAX_UNPACKED` | 8 GiB | Rejects zips that would unpack larger than this |

## Develop

```bash
pip install -e ".[test]"
pytest
cd web && npm run dev      # UI with hot reload on :5173
```

Read [SCHEMA.md](SCHEMA.md) before changing the database or graph code.
