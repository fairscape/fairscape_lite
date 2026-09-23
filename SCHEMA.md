# fairscape_lite — the index

A department-scale FAIRSCAPE server: one SQLite file, twelve endpoints, no
Mongo, no Minio, no Redis, no Celery. It indexes RO-Crates that already
live on a shared filesystem and answers the metadata questions the old
server answered.

Everything below rests on one decision.

## The crate files are the source of truth

This database is an **index**, not a copy. It stores what is needed to
*find* a node — the @id, a normalised type, name, description, keywords,
contentUrl — plus the path of the file that supplied it. It does not store
the node. `GET /ark:…` re-opens that file and reads the node back out.

That costs a parse per lookup. In exchange:

- The index can never *disagree* with a crate. The worst it can do is go
  stale, and `GET /rocrate/stale` lists exactly which crates have drifted.
- Editing a crate on disk and re-registering it is the whole update story.
- A node keeps every field it had. There is no schema to widen when
  `fairscape_models` grows a field, and no silent truncation of the `d4d`
  and `rai` extras that real crates carry.

The old server stored a full copy of each node in Mongo and had a
long tail of bugs where the copy and the crate had diverged. Those bugs
are not fixed here; they are structurally impossible.

Uploads do not change this. `POST /rocrate/upload` unpacks the archive
under `FAIRSCAPE_LITE_UPLOADS` and then registers the resulting
`ro-crate-metadata.json` by path, so an uploaded crate is an ordinary
`crate` row whose `path` happens to point into the uploads directory.
`upload.py` explains why the archive is unpacked verbatim (crate-relative
`contentUrl`s must keep resolving) and how the per-crate directory is
named.

## The three tables

### `crate` — one row per registered `ro-crate-metadata.json`

| column | why |
|---|---|
| `id` | the crate **root's** @id (primary key) |
| `path` | absolute path to the file. **UNIQUE** |
| `context` | verbatim `@context` — dict, list or string, so kept as JSON text |
| `mtime`, `size` | `st_mtime`/`st_size` at ingest; how re-ingest decides to skip |
| `node_count` | `len(@graph)` on disk, so "indexed 3977 of 3978" is legible |
| `ingested_at` | |

`UNIQUE(path)` matters more than it looks. Without it, regenerating a
crate so its root @id changes leaves a *ghost* row still pointing at the
file: it lists in `GET /rocrate`, its entities resolve but 404 on
metadata, and skip-detection becomes order-dependent. With it, ingest
notices the file was registered under a different root and drops the old
registration first.

### `entity` — one row per globally unique `@id`

| column | why |
|---|---|
| `pk` | `INTEGER PRIMARY KEY`, i.e. the rowid. `entity_fts` is an external-content index keyed by it, so it must be a real rowid alias — a plain `UNIQUE id` would let `VACUUM` renumber rows out from under the index |
| `id` | the @id exactly as written. 111,513 ARKs, 57,693 non-ARKs locally, so nothing is normalised away |
| `ark_key` | `naan/postfix`, dashes stripped, for dash-insensitive ARK lookup. NULL for non-ARKs |
| `fairscape_type` | one short name: `Dataset`, `Computation`, `ROCrate`… |
| `types` | verbatim `@type`, JSON text |
| `name`, `description`, `keywords` | promoted for listing and FTS |
| `content_url` | where the bytes live. **This server never serves them** |
| `source_crate` | the file `metadata()` re-reads. `ON DELETE CASCADE` |

**Globally unique @id is the load-bearing rule.** The same @id in a second
crate is the *same thing*, not a second row: 55,793 of 169,145 distinct
@ids in the local corpus appear in more than one crate. Membership —
including a crate containing a sub-crate — is expressed as edges, never by
duplicating rows.

**The descriptor node is never indexed.** Its @id is the literal string
`ro-crate-metadata.json` in all 67 local crates and essentially every
crate anywhere. Indexing it would merge every crate on the server into one
row. `find_root()` reads it (its `about` names the real root) and
`_indexable_nodes()` then skips it.

#### The collision rule

Testing forced a correction here once already, so it is written down.

1. **A crate's own root always wins**, unconditionally — its file is
   authoritative for it.
2. Otherwise a crate may **refresh rows it already owns**. That is what
   re-ingest is.
3. Otherwise **first-wins**: the row stands and the later crate
   contributes only edges.

The tempting version — "upgrade the row if the existing one is a stub" —
is wrong. A parent crate embeds a *rich* copy of each child root (18–26
keys in the real fixtures), not a thin stub, so "is it a stub" cannot
distinguish them. Rule 1 makes ingest order irrelevant, which
`test_both_ingest_orders_converge` checks directly.

### `edge` — every link

`(subject, predicate, object, position)`, primary key on the first three,
`WITHOUT ROWID`.

**No foreign keys, on purpose.** An edge routinely points at an @id nobody
registered — 177 such objects locally. Dropping them would discard exactly
the information that says a crate is incomplete.

Predicates are canonicalised to one short name, because real crates spell
the same term five ways. `EDGE_ALIASES` in `db.py` maps them, and anything
else spelled `used*` keeps its own name (that is how `usedTreatment` and
`usedStain`, 10k references locally, survive without being enumerated).
Fields that are not links — `author`, `associatedDisease` — stay out and
are read from the node itself.

Aliasing merges vocabularies deliberately:

- `prov:wasGeneratedBy` → `generatedBy`
- `prov:wasDerivedFrom` → `derivedFrom`
- `evi:Schema`, `EVI:Schema` → `schema`

That last pair of merges is not cosmetic. `prov:wasDerivedFrom` is the
**only** derivation link on 9,621 nodes in the c2m2 crates, which have no
`derivedFrom` twin; elsewhere the two co-occur. Storing both under
`derivedFrom` keeps the first and de-duplicates the second — 16,728 raw
references become 15,869 stored edges.

### `entity_fts`

FTS5 over `name`/`description`/`keywords`, external-content on `entity`,
three sync triggers. Queries FTS5 cannot parse are retried as one quoted
phrase, so punctuation in a search box does not raise.

## Deployment posture

**This is the shared-filesystem server.** Crates live on a filesystem the
department already shares. `POST /rocrate` hands the server a *path*; it
indexes what it finds there. It never receives an upload and never serves
file bytes — `contentUrl` resolves for a peer because the peer mounts the
same tree, or because the URL points at Dataverse, as it does for most
CM4AI crates.

That makes reads safe to expose and writes emphatically not:

| variable | effect |
|---|---|
| `FAIRSCAPE_LITE_ROOT` | confines registration to one directory. **Without it, anyone who can reach the port can have the server read any world-readable JSON on the host and serve it back.** |
| `FAIRSCAPE_LITE_DB` | database location (default `./fairscape.db`) |

There is deliberately no auth: this server is for localhost or a network
segment you already trust. `FAIRSCAPE_LITE_ROOT` is unset by default —
right for `localhost`, wrong for anything else. Set it before binding to
`0.0.0.0`.

If you later need genuinely remote peers, the missing pieces are a
zip-upload path and a byte-serving endpoint. Nothing here forecloses them.

## Endpoints

| | |
|---|---|
| `POST /rocrate` | register a file, or walk a directory. Validates against `fairscape_models` first |
| `GET /rocrate` | registered crates |
| `GET /rocrate/stale` | crates whose file moved, changed or vanished |
| `POST /rocrate/reingest` | re-read every registered crate |
| `GET /rocrate/metadata?id=` | the crate's `ro-crate-metadata.json`, verbatim |
| `DELETE /rocrate?id=` | unregister |
| `GET /ark:{naan}/{postfix}` | resolve an ARK → `Identifier` |
| `GET /identifier?id=` | resolve any @id form → `Identifier` |
| `GET /entity` | list/filter by `crate`, `type`, `limit`, `offset` |
| `GET /search?q=` | full text |
| `GET /evidencegraph/ark:{naan}/{postfix}` | built fresh per request |
| `GET /evidencegraph?id=` | same, for non-ARK @ids |

The `?id=` twins are not redundancy: 57,693 local @ids are URLs, which
cannot be spelled as a path segment.

`Identifier` is the old `StoredIdentifier` reduced to what the web client
actually destructures — `@id`, `@type`, `metadata`, `sourceCrate`.
Permissions, distribution, publication status, descriptive/split
statistics and the 23-class `MetadataUnion` went with the features that
needed them.

## Evidence graphs

Built at read time by `graph.py`; on the old server this was a Celery task
that wrote its result back as an identifier and was polled for. Three
steps: `collect` (iterative BFS backward through `generatedBy` / `used*`),
`condense`, `project`.

`tests/test_graph.py` asserts **byte-identical parity** with
`fairscape_graph_tools.EvidenceGraphBuilder` over the same store, with
condensation disabled on both sides — 41 nodes including a full 18k-node
crate root.

Condensation is deliberately *not* compared, because it is deliberately
simpler: sibling datasets **inside one reference list** sharing a format
and a generating computation collapse into a `DatasetGroup` above
threshold 5. No recursive provenance signatures. Members stay in the cache
but nothing points at them, so projection never reaches them. Pass
`?condense=0` to disable.

Both traversal and projection are iterative. The real builder's projection
recurses and will overflow on a long chain — and loops forever on a
provenance cycle, since it recurses before claiming the node. `project()`
claims first (`test_projection_survives_a_provenance_cycle`).

## Limitations, with numbers

Measured on this machine's corpus — 67 crates, 229,095 nodes — by
a since-removed survey script and `scripts/bench.py`. Re-run the bench
if the corpus changes.

1. **Two files with the same root @id: last one wins.** `crate.id` is the
   primary key, so the second file to register replaces the first's row
   and the first is silently unregistered. **17 of 70 crate files locally
   collide this way** — the same CM4AI crate copied into
   `CM4AIJuneRelease/`, `JanFeb CM4AI ROCrates/` and `wizards/`. 70 files
   walked produce 53 crate rows. *Fix if it matters: key `crate` by `path`
   and let `id` be non-unique.*

2. **First-wins means a crate can lose rows it also contains.** `DELETE
   /rocrate?id=A` removes entities `A` owned, even where crate `B`'s file
   also contains them; they return when `B` is re-ingested. Likewise, if
   `A` drops a node from its file, `_drop_vanished` deletes the row even
   though `B` still has it. `POST /rocrate/reingest` repairs both.

3. **Edges asserted about another crate's nodes are not cleaned up.**
   `edge` has no crate column, so re-ingest can only clear edges leaving
   nodes this crate *owns*. A link crate `A` asserted about a node crate
   `B` owns survives until `B` is re-ingested.

4. **`ark_key` collisions.** Dash-stripping maps `ark:x/a-b` and
   `ark:x/ab` to one key; `resolve()` returns the lowest `pk`. Case is
   preserved, so two ARKs differing only in case stay distinct.

5. **Big crates are re-parsed per lookup.** `metadata()` on a node in the
   33 MB vorinostat crate parses 33 MB. It is ~0.2 s and there is no cache
   — a parsed crate of that size is ~1 GB resident, which is not worth
   holding. Evidence-graph builds parse each contributing crate once per
   build, then drop it.

6. **Registration of a large crate is a slow synchronous request.** The
   vorinostat crate takes ~3 s. Acceptable — it replaces a Celery
   pipeline — but do not "fix" it by making it async without a queue.

## Measured behaviour

`python3 scripts/bench.py .. --db /tmp/bench.db`, on the full local corpus:

```
ingest        70 crates, 229,185 nodes in 46.9s (4,882 nodes/s)
index         169,206 entities, 710,622 edges, 517 MB on disk
re-ingest     53/53 skipped as unchanged
resolve       56 us/lookup
search        0.8 ms/query
evidencegraph 1,473 nodes in 0.61s (collapsed 17,734)  vorinostat root
```

517 MB is mostly `edge`: 156 MB table + 135 MB `edge_object` index, then
131 MB `entity` and 51 MB FTS. `edge_object` exists only for
`neighbors()`' incoming lookups — drop it and the file loses a quarter of
its size.

Ingest is ~24% slower than building rows as bare tuples, which is the
price of the pydantic mirrors in `models.py`. That is once per crate, and
it buys a single place where columns are spelled: a schema change that
isn't mirrored fails loudly at ingest instead of writing values one
position off.

## Files

```
src/fairscape_lite/
  schema.sql   the three tables, FTS index and triggers
  models.py    pydantic mirrors, IngestStats, validate_crate, Identifier
  db.py        vocabulary, ingest, and every read
  graph.py     collect -> condense -> project
  app.py       the twelve endpoints, plus serving web/dist under /ui/
scripts/bench.py   full-corpus ingest and read timings
tests/             85 tests, incl. parity vs fairscape_graph_tools
web/               the view-only UI (React); builds to web/dist
```
