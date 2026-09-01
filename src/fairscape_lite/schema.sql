-- fairscape_lite: the whole database.
--
-- Three tables and a full-text index. The design rule that explains all
-- of it: this is an INDEX, not a copy. The ro-crate-metadata.json files
-- on disk stay the source of truth; we store only what is needed to FIND
-- a node, plus the path back to the file that supplied it. Fetching a
-- node's full metadata re-reads that file (see db.metadata).
--
-- Everything is IF NOT EXISTS so two concurrent first-requests can both
-- run this script without one of them dying on "table already exists".

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;


-- One row per registered ro-crate-metadata.json file.
CREATE TABLE IF NOT EXISTS crate (
    -- The crate root's @id. Not the descriptor node ("ro-crate-metadata.json"),
    -- which is the same string in every crate on earth and is never indexed.
    id          TEXT PRIMARY KEY,

    -- Absolute path to the ro-crate-metadata.json file. UNIQUE: without it,
    -- regenerating a crate so its root @id changes leaves a ghost row still
    -- pointing at this file, and skip-detection becomes order-dependent.
    path        TEXT NOT NULL UNIQUE,

    -- Verbatim @context. Dict, list or string depending on the crate, so
    -- it is kept as JSON text and handed back untouched on read.
    context     TEXT,

    -- st_mtime / st_size at ingest. Re-ingesting an unchanged file is a
    -- no-op; these two columns are how that is decided.
    mtime       REAL    NOT NULL,
    size        INTEGER NOT NULL,

    -- len(@graph) as it was on disk, including the nodes we chose not to
    -- index. Purely diagnostic: it makes "indexed 3977 of 3978" legible.
    node_count  INTEGER NOT NULL,

    ingested_at TEXT    NOT NULL,

    -- The root is also an entity. DEFERRABLE because ingest writes this
    -- row before the entities, inside one transaction.
    FOREIGN KEY (id) REFERENCES entity (id) DEFERRABLE INITIALLY DEFERRED
);


-- One row per globally-unique @id.
--
-- "Globally unique" is the load-bearing rule: the same @id seen in a
-- second crate does NOT create a second row, it is the same thing. On
-- this corpus that matters a lot -- 55,793 of 169,145 distinct @ids
-- appear in more than one crate.
--
-- Which crate wins a contested @id (see SCHEMA.md, "collision rule"):
--   1. a crate's own root node always wins, unconditionally
--   2. otherwise a crate may refresh rows it already owns
--   3. otherwise first-wins; later crates only contribute edges
CREATE TABLE IF NOT EXISTS entity (
    -- rowid alias. entity_fts is an external-content table keyed by it,
    -- so it must be a real INTEGER PRIMARY KEY (a plain UNIQUE id would
    -- let VACUUM renumber rowids out from under the index).
    pk             INTEGER PRIMARY KEY,

    -- The @id exactly as the crate wrote it. 170k ARKs, 59k URLs and a
    -- handful of relative paths in the local corpus, so: no normalising.
    id             TEXT NOT NULL UNIQUE,

    -- 'naan/postfix' with dashes stripped, for dash-insensitive ARK
    -- lookup (ark:59852/foo-bar and ark:59852/foobar find each other).
    -- NULL for non-ARK @ids, which are looked up by exact id instead.
    ark_key        TEXT,

    -- @type reduced to one short name: Dataset, Computation, Software,
    -- Sample, ROCrate, Schema... Real crates write this five ways
    -- (bare, prefixed, full-URI, and as a list led by prov:Entity), so
    -- the raw value is kept alongside it in `types`.
    fairscape_type TEXT NOT NULL,

    -- Verbatim @type, JSON text. String or list, whatever was on disk.
    types          TEXT NOT NULL,

    name           TEXT,
    description    TEXT,
    keywords       TEXT,          -- verbatim, JSON text
    content_url    TEXT,          -- where the bytes live; we never serve them

    -- The crate whose file this row's metadata came from, and therefore
    -- the file db.metadata re-reads. Losing this row's crate loses the
    -- ability to answer anything but "it existed".
    source_crate   TEXT NOT NULL REFERENCES crate (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS entity_ark_key  ON entity (ark_key);
CREATE INDEX IF NOT EXISTS entity_crate    ON entity (source_crate);
CREATE INDEX IF NOT EXISTS entity_type     ON entity (fairscape_type);


-- Every link between two @ids: containment (hasPart / isPartOf) and
-- provenance (generatedBy / used* / derivedFrom / ...) alike. There is
-- no separate mechanism for crate-contains-sub-crate; that is a hasPart
-- edge like any other, and what makes it a sub-crate is the target
-- entity's type.
--
-- Deliberately has NO foreign keys. An edge routinely points at an @id
-- that is not indexed here -- a node in a crate nobody registered, or a
-- dangling reference. Dropping those would be dropping exactly the
-- information that tells you a crate is incomplete.
CREATE TABLE IF NOT EXISTS edge (
    subject   TEXT NOT NULL,
    predicate TEXT NOT NULL,   -- canonical short name; see db.EDGE_ALIASES
    object    TEXT NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0,   -- index within a list-valued field
    PRIMARY KEY (subject, predicate, object)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS edge_object ON edge (object, predicate);


-- Full-text search over the three human-readable columns.
CREATE VIRTUAL TABLE IF NOT EXISTS entity_fts USING fts5 (
    name, description, keywords,
    content = 'entity',
    content_rowid = 'pk',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS entity_fts_insert AFTER INSERT ON entity BEGIN
    INSERT INTO entity_fts (rowid, name, description, keywords)
    VALUES (new.pk, new.name, new.description, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS entity_fts_delete AFTER DELETE ON entity BEGIN
    INSERT INTO entity_fts (entity_fts, rowid, name, description, keywords)
    VALUES ('delete', old.pk, old.name, old.description, old.keywords);
END;

CREATE TRIGGER IF NOT EXISTS entity_fts_update AFTER UPDATE ON entity BEGIN
    INSERT INTO entity_fts (entity_fts, rowid, name, description, keywords)
    VALUES ('delete', old.pk, old.name, old.description, old.keywords);
    INSERT INTO entity_fts (rowid, name, description, keywords)
    VALUES (new.pk, new.name, new.description, new.keywords);
END;
