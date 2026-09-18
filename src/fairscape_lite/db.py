"""SQLite index over a directory of RO-Crates.

The whole module rests on one decision: crate files are the source of
truth and this database is only an index into them. Nothing here copies a
node's metadata. `metadata()` re-opens the crate file and reads the node
back out, which costs a parse but means the index can never disagree with
the file -- the worst it can do is go stale, and `stale()` lists exactly
that.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

from .models import (
    Crate,
    CrateSummary,
    Edge,
    Entity,
    EntitySummary,
    IngestStats,
)

HERE = Path(__file__).resolve().parent
SCHEMA = (HERE / "schema.sql").read_text()
# The index lands in the working directory, not the package: the package
# may be installed somewhere read-only, and "the db is where I ran it" is
# the least surprising rule for a local tool.
DB_PATH = os.environ.get("FAIRSCAPE_LITE_DB", "fairscape.db")

METADATA_FILENAME = "ro-crate-metadata.json"


class MissingCrateFile(Exception):
    """The index points at a crate file that is no longer readable."""


# --------------------------------------------------------------------------
# JSON-LD vocabulary
#
# Real crates spell the same term five ways: bare (`hasPart`), prefixed
# (`evi:Schema`, `EVI:Schema`), full-URI (`https://w3id.org/EVI#inputs`),
# and PROV-flavoured (`prov:wasGeneratedBy`). All of them are reduced to
# one short name here so a query does not have to know which crate it is
# talking to.
# --------------------------------------------------------------------------

def short_name(term: str) -> str:
    """`https://w3id.org/EVI#Dataset` -> `Dataset`; `evi:Schema` -> `Schema`."""
    return str(term).split("#")[-1].rsplit("/", 1)[-1].split(":")[-1]


TYPE_CANON = {
    t.lower(): t
    for t in (
        "ROCrate", "Dataset", "Computation", "Software", "Sample", "Experiment",
        "Instrument", "Schema", "MLModel", "ModelCard", "Person", "Organization",
        "BioChemEntity", "DefinedTerm", "MedicalCondition", "Patient",
        "CreativeWork", "EvidenceGraph", "DatasetGroup", "AIReadyScore",
    )
}


def normalize_type(raw) -> str:
    """@type -> one short name.

    ROCrate always wins, because "is this a crate" is a question the rest
    of the code asks constantly. Otherwise the bare `prov:Entity` /
    `prov:Activity` wrappers are dropped -- 197k nodes in the local corpus
    are typed `['prov:Entity', 'https://w3id.org/EVI#Dataset']` and the
    interesting half is the second one.
    """
    terms = [t for t in (raw if isinstance(raw, list) else [raw]) if t]
    if not terms:
        return "Thing"

    names = [short_name(t) for t in terms]
    if any(n.lower() == "rocrate" for n in names):
        return "ROCrate"

    specific = [
        n for t, n in zip(terms, names)
        if not str(t).lower().startswith("prov:")
    ] or names
    return TYPE_CANON.get(specific[-1].lower(), specific[-1])


_ARK = re.compile(r"^ark:/?(\d+)/(.+)$")


def ark_key(identifier: str) -> Optional[str]:
    """`ark:59852/rocrate-foo-bar` -> `59852/rocratefoobar`.

    Dash-insensitive so a caller need not reproduce them exactly; case is
    preserved, because two ARKs differing only in case are two ARKs. A
    trailing slash is ignored (one real crate root ends in one).
    """
    match = _ARK.match(identifier.strip())
    if not match:
        return None
    naan, postfix = match.group(1), match.group(2).rstrip("/")
    return f"{naan}/{postfix.replace('-', '')}"


# Canonical spelling for each link we store, keyed by lowercased short
# name. Aliases collapse onto one predicate on purpose: `prov:wasDerivedFrom`
# is the *only* derivation link on 9,621 nodes in the local corpus, while
# elsewhere it duplicates `derivedFrom` -- mapping both to `derivedFrom`
# keeps the first and de-duplicates the second.
EDGE_ALIASES = {
    # containment
    "haspart": "hasPart",
    "ispartof": "isPartOf",
    # provenance, forward
    "generatedby": "generatedBy",
    "wasgeneratedby": "generatedBy",        # prov: twin
    "derivedfrom": "derivedFrom",
    "wasderivedfrom": "derivedFrom",        # prov: twin, sole link in c2m2
    "used": "used",                         # prov:used, untyped
    "inputs": "inputs",
    "outputs": "outputs",
    # provenance, inverse / back-pointers (kept as their own predicates)
    "generated": "generated",
    "datasetusedby": "datasetUsedBy",
    "softwareusedby": "softwareUsedBy",
    "usedby": "usedBy",
    "derivedto": "derivedTo",
    # typed `used*` spellings we want canonical casing for
    "useddataset": "usedDataset",
    "usedsoftware": "usedSoftware",
    "usedsample": "usedSample",
    "usedinstrument": "usedInstrument",
    "usedmlmodel": "usedMLModel",
    # structural / domain links worth traversing
    "schema": "schema",                     # evi:Schema and EVI:Schema
    "conformsto": "conformsTo",
    "about": "about",
    "localevidencegraph": "localEvidenceGraph",
    "bait": "bait",
    "describedbyc2m2table": "describedByC2M2Table",
    "referencestable": "referencesTable",
}


def edge_predicate(field: str) -> Optional[str]:
    """The predicate to store this field under, or None to skip it.

    Anything not in EDGE_ALIASES but spelled `used*` is kept under its own
    name -- that is how domain-specific links like `usedTreatment` and
    `usedStain` (10k references locally) survive without being enumerated.
    Everything else (author, associatedDisease, ...) stays out of the edge
    table and is read from the node itself via `metadata()`.
    """
    short = short_name(field)
    canonical = EDGE_ALIASES.get(short.lower())
    if canonical:
        return canonical
    return short if short.lower().startswith("used") else None


def _id_refs(value) -> list[str]:
    """Every `{"@id": ...}` packed in a field value, in order."""
    items = value if isinstance(value, list) else [value]
    return [
        item["@id"] for item in items
        if isinstance(item, dict) and isinstance(item.get("@id"), str)
    ]


# --------------------------------------------------------------------------
# Connection + crate files
# --------------------------------------------------------------------------

def connect(path: Optional[str] = None) -> sqlite3.Connection:
    """Open (creating if needed) the index.

    The schema script is idempotent, so it just runs every time rather
    than racing on a "does the entity table exist yet" check.

    check_same_thread is off because FastAPI runs the sync `connection`
    dependency and the endpoint it feeds in threadpool threads that need
    not be the same one. Each connection is still request-private and
    used sequentially, which is the case SQLite is actually fine with.
    """
    con = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.isolation_level = None          # we manage BEGIN/COMMIT ourselves
    con.executescript(SCHEMA)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def metadata_file(path: str | os.PathLike) -> Path:
    """Accept either a crate directory or its metadata file."""
    resolved = Path(path).expanduser().resolve()
    if resolved.is_dir():
        resolved = resolved / METADATA_FILENAME
    return resolved


def read_crate(path: str | os.PathLike) -> dict:
    """Parse a crate file. Unreadable -> MissingCrateFile, malformed -> ValueError."""
    try:
        with open(path) as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    except FileNotFoundError as exc:
        raise MissingCrateFile(f"crate file is gone: {path}") from exc
    except OSError as exc:
        raise MissingCrateFile(f"cannot read crate file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def find_root(data: dict) -> tuple[Optional[dict], str, dict]:
    """Return (descriptor, root_id, root_node).

    The descriptor is the `CreativeWork` node whose @id is the literal
    string "ro-crate-metadata.json"; its `about` points at the real root.
    All 67 local crates are shaped that way, but fall back to the first
    ROCrate-typed node so a hand-written crate still loads.
    """
    graph = [n for n in (data.get("@graph") or []) if isinstance(n, dict)]

    descriptor = next(
        (n for n in graph if n.get("@id") == METADATA_FILENAME), None
    ) or next((n for n in graph if n.get("@type") == "CreativeWork"), None)

    root_id = None
    if descriptor:
        about = descriptor.get("about")
        refs = _id_refs(about)
        root_id = refs[0] if refs else None

    by_id = {n.get("@id"): n for n in graph}
    if root_id not in by_id:
        root = next(
            (n for n in graph if normalize_type(n.get("@type")) == "ROCrate"), None
        )
        if root is None:
            raise ValueError("no RO-Crate root node found in @graph")
        root_id = root["@id"]

    return descriptor, root_id, by_id[root_id]


def _indexable_nodes(data: dict, descriptor: Optional[dict]) -> Iterator[dict]:
    """Every @graph node that becomes an entity row.

    Skips the descriptor (its @id is the same relative path in every crate
    on earth, so indexing it would merge all crates into one row) and any
    node without an @id. Within one crate the first occurrence of an @id
    wins -- 5 local crates repeat one.
    """
    seen: set[str] = set()
    for node in data.get("@graph") or []:
        if not isinstance(node, dict):
            continue
        guid = node.get("@id")
        if not isinstance(guid, str) or not guid:
            continue
        if descriptor is not None and node is descriptor:
            continue
        if guid == METADATA_FILENAME or guid in seen:
            continue
        seen.add(guid)
        yield node


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------

def _as_json(value) -> Optional[str]:
    return None if value is None else json.dumps(value)


def _first_str(node: dict, *fields: str) -> Optional[str]:
    for field in fields:
        value = node.get(field)
        if isinstance(value, str) and value:
            return value
        if isinstance(value, dict) and isinstance(value.get("@id"), str):
            return value["@id"]
    return None


def _entity_row(node: dict, crate_id: str) -> Entity:
    guid = node["@id"]
    return Entity(
        id=guid,
        ark_key=ark_key(guid),
        fairscape_type=normalize_type(node.get("@type")),
        types=_as_json(node.get("@type")) or '""',
        name=_first_str(node, "name"),
        description=_first_str(node, "description"),
        keywords=_as_json(node.get("keywords")),
        content_url=_first_str(node, "contentUrl", "distribution", "url"),
        source_crate=crate_id,
    )


def _store_entity(cur: sqlite3.Cursor, node: dict, crate_id: str, root_id: str) -> str:
    """Write one node, returning the IngestStats field it counted toward.

    The collision rule lives here and nowhere else:
      1. a crate's own root always wins -- its file is authoritative for it
      2. a crate may refresh rows it already owns (that is what re-ingest is)
      3. otherwise first-wins: the row stands, and this crate only adds edges
    """
    row = _entity_row(node, crate_id)
    owner = cur.execute(
        "SELECT source_crate FROM entity WHERE id = ?", (row.id,)
    ).fetchone()

    if owner is None:
        cur.execute(Entity.insert(), row.values())
        return "entities_inserted"

    if row.id == root_id or owner["source_crate"] == crate_id:
        cur.execute(Entity.update("id = ?"), row.values() + (row.id,))
        return "entities_refreshed"

    return "entities_kept"


def _store_edges(cur: sqlite3.Cursor, node: dict) -> int:
    """Write every allowlisted link leaving this node."""
    subject = node["@id"]
    written = 0
    for field, value in node.items():
        predicate = edge_predicate(field)
        if predicate is None:
            continue
        for position, target in enumerate(_id_refs(value)):
            edge = Edge(
                subject=subject, predicate=predicate,
                object=target, position=position,
            )
            cur.execute(Edge.insert("INSERT OR IGNORE"), edge.values())
            written += cur.rowcount
    return written


def _unchanged(con: sqlite3.Connection, path: Path, stat: os.stat_result):
    """The crate row for this path, if the file has not changed since."""
    row = con.execute(
        "SELECT * FROM crate WHERE path = ? AND mtime = ? AND size = ?",
        (str(path), stat.st_mtime, stat.st_size),
    ).fetchone()
    return Crate.from_row(row)


def _reset_crate(
    cur: sqlite3.Cursor, crate: Crate, previous_id: Optional[str]
) -> None:
    """Upsert the crate row and clear the links it previously asserted.

    Edges are keyed only by (subject, predicate, object) -- there is no
    crate column -- so what can be cleaned up is edges leaving nodes this
    crate owns. A link this crate asserted *about* a node another crate
    owns survives until that crate is re-ingested. See SCHEMA.md.
    """
    if previous_id and previous_id != crate.id:
        # The file's root @id changed. Drop the old registration rather
        # than leave a second crate row pointing at this same file.
        _forget(cur, previous_id)

    cur.execute(
        "DELETE FROM edge WHERE subject IN "
        "(SELECT id FROM entity WHERE source_crate = ?)",
        (crate.id,),
    )
    cur.execute(Crate.upsert("id"), crate.values())


def _drop_vanished(cur: sqlite3.Cursor, crate_id: str, seen: Iterable[str]) -> int:
    """Delete rows this crate owns that are no longer in its file."""
    cur.execute("CREATE TEMP TABLE IF NOT EXISTS seen_ids (id TEXT PRIMARY KEY)")
    cur.execute("DELETE FROM seen_ids")
    cur.executemany("INSERT OR IGNORE INTO seen_ids VALUES (?)", ((i,) for i in seen))
    cur.execute(
        "DELETE FROM entity WHERE source_crate = ? "
        "AND id NOT IN (SELECT id FROM seen_ids)",
        (crate_id,),
    )
    return cur.rowcount


def ingest(
    con: sqlite3.Connection,
    path: str | os.PathLike,
    data: Optional[dict] = None,
    force: bool = False,
    validate: Optional[Callable[[dict], None]] = None,
) -> IngestStats:
    """Index one ro-crate-metadata.json.

    `data` lets a caller that already parsed the file hand it over rather
    than have it read a second time -- the HTTP endpoint validates the
    parse it made, then passes it straight through. `validate` is called
    on the parse before anything is written (it raises to reject); the
    endpoint passes fairscape_models validation so a tree walk applies
    the same rule a single-file registration does.
    """
    file_path = metadata_file(path)
    try:
        stat = file_path.stat()
    except OSError as exc:
        raise MissingCrateFile(f"cannot stat crate file {file_path}: {exc}") from exc

    previous = _unchanged(con, file_path, stat)
    if previous and not force:
        return IngestStats(
            crate=previous.id, path=str(file_path),
            skipped=True, nodes=previous.node_count,
        )

    if data is None:
        data = read_crate(file_path)
    if validate is not None:
        validate(data)

    descriptor, root_id, _root = find_root(data)
    graph = data.get("@graph") or []

    crate = Crate(
        id=root_id,
        path=str(file_path),
        context=_as_json(data.get("@context")),
        mtime=stat.st_mtime,
        size=stat.st_size,
        node_count=len(graph),
        ingested_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    stats = IngestStats(crate=root_id, path=str(file_path), nodes=len(graph))

    registered = con.execute(
        "SELECT id FROM crate WHERE path = ?", (str(file_path),)
    ).fetchone()

    cur = con.cursor()
    cur.execute("BEGIN")
    try:
        _reset_crate(cur, crate, registered["id"] if registered else None)

        seen: list[str] = []
        for node in _indexable_nodes(data, descriptor):
            seen.append(node["@id"])
            stats.count(_store_entity(cur, node, root_id=root_id, crate_id=root_id))
            stats.count("edges", _store_edges(cur, node))

        stats.entities_dropped = _drop_vanished(cur, root_id, seen)
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise

    return stats


def ingest_tree(
    con: sqlite3.Connection,
    directory: str | os.PathLike,
    force: bool = False,
    validate: Optional[Callable[[dict], None]] = None,
) -> list[IngestStats]:
    """Index every crate under `directory`.

    This is the entry point for a shared-filesystem deployment: point it
    at the department's crate mount and it registers whatever is there.
    Sub-crates are found by walking, not by following links out of a
    parent -- a parent's copy of a child root is just another node.

    One bad file must not sink the walk: a crate that is malformed, not a
    crate, or unreadable gets an IngestStats with `error` set and the walk
    goes on. Each ingest is its own transaction, so a failure leaves the
    crates before it registered and the index consistent.
    """
    skip = {"node_modules", ".git", "__pycache__", ".venv", "venv"}
    results = []
    for dirpath, dirnames, filenames in os.walk(Path(directory).expanduser()):
        dirnames[:] = sorted(d for d in dirnames if d not in skip)
        if METADATA_FILENAME not in filenames:
            continue
        file_path = Path(dirpath) / METADATA_FILENAME
        try:
            results.append(ingest(con, file_path, force=force, validate=validate))
        except (ValueError, MissingCrateFile) as exc:
            # pydantic's ValidationError is a ValueError; give it the same
            # wording the single-file endpoint uses.
            reason = str(exc)
            if hasattr(exc, "error_count") and hasattr(exc, "errors"):
                reason = (f"not a valid RO-Crate: {exc.error_count()} "
                          f"problem(s); first: {exc.errors()[0]}")
            results.append(IngestStats(path=str(file_path), skipped=True, error=reason))
    return results


def reingest_all(con: sqlite3.Connection, force: bool = True) -> list[IngestStats]:
    """Re-read every registered crate file, in place."""
    paths = [r["path"] for r in con.execute("SELECT path FROM crate ORDER BY path")]
    results = []
    for path in paths:
        try:
            results.append(ingest(con, path, force=force))
        except MissingCrateFile as exc:
            results.append(IngestStats(path=path, skipped=True, crate=str(exc)))
    return results


def forget(con: sqlite3.Connection, crate_id: str) -> bool:
    """Unregister a crate and everything it supplied."""
    cur = con.cursor()
    cur.execute("BEGIN")
    try:
        dropped = _forget(cur, crate_id)
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    return dropped


def _forget(cur: sqlite3.Cursor, crate_id: str) -> bool:
    """Same, but inside a transaction the caller already opened."""
    cur.execute(
        "DELETE FROM edge WHERE subject IN "
        "(SELECT id FROM entity WHERE source_crate = ?)",
        (crate_id,),
    )
    cur.execute("DELETE FROM entity WHERE source_crate = ?", (crate_id,))
    cur.execute("DELETE FROM crate WHERE id = ?", (crate_id,))
    return cur.rowcount > 0


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def resolve(con: sqlite3.Connection, identifier: str) -> Optional[Entity]:
    """Find one entity by @id, tolerating ARK dash differences."""
    row = con.execute("SELECT * FROM entity WHERE id = ?", (identifier,)).fetchone()
    if row is None:
        key = ark_key(identifier)
        if key:
            row = con.execute(
                "SELECT * FROM entity WHERE ark_key = ? ORDER BY pk LIMIT 1", (key,)
            ).fetchone()
    return Entity.from_row(row)


def crate_path(con: sqlite3.Connection, crate_id: str) -> Optional[str]:
    row = con.execute("SELECT path FROM crate WHERE id = ?", (crate_id,)).fetchone()
    return row["path"] if row else None


def metadata(con: sqlite3.Connection, entity: Entity) -> Optional[dict]:
    """The entity's full JSON-LD node, read back from its crate file.

    Raises MissingCrateFile if the file is unreadable; returns None if the
    file is fine but no longer contains this @id (an index gone stale).
    """
    path = crate_path(con, entity.source_crate)
    if path is None:
        raise MissingCrateFile(f"no crate registered for {entity.source_crate}")

    data = read_crate(path)
    for node in data.get("@graph") or []:
        if isinstance(node, dict) and node.get("@id") == entity.id:
            return node
    return None


def crate_json(con: sqlite3.Connection, crate_id: str) -> dict:
    """The crate's ro-crate-metadata.json, verbatim."""
    path = crate_path(con, crate_id)
    if path is None:
        raise MissingCrateFile(f"no crate registered for {crate_id}")
    return read_crate(path)


def search(
    con: sqlite3.Connection, query: str, limit: int = 25
) -> list[EntitySummary]:
    """Full-text search over name, description and keywords.

    FTS5 treats punctuation as syntax, so a query it cannot parse is
    retried as a single quoted phrase rather than raising at the caller.
    """
    sql = (
        f"SELECT {EntitySummary.select} FROM entity "
        "JOIN entity_fts ON entity_fts.rowid = entity.pk "
        "WHERE entity_fts MATCH ? ORDER BY rank LIMIT ?"
    )
    try:
        rows = con.execute(sql, (query, limit)).fetchall()
    except sqlite3.OperationalError:
        phrase = '"' + query.replace('"', '""') + '"'
        rows = con.execute(sql, (phrase, limit)).fetchall()
    return EntitySummary.from_rows(rows)


def list_entities(
    con: sqlite3.Connection,
    crate: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[EntitySummary]:
    """Entities, optionally scoped to one crate and/or one type.

    Scoped to a crate means "rows that crate supplied". Under first-wins a
    node another crate got to first lists under *that* crate, even though
    this crate's file also contains it.
    """
    clauses, params = [], []
    if crate:
        clauses.append("source_crate = ?")
        params.append(crate)
    if entity_type:
        clauses.append("fairscape_type = ?")
        params.append(entity_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    rows = con.execute(
        f"SELECT {EntitySummary.select} FROM entity {where} "
        "ORDER BY pk LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return EntitySummary.from_rows(rows)


def list_crates(con: sqlite3.Connection) -> list[CrateSummary]:
    rows = con.execute(
        f"SELECT {CrateSummary.select} FROM crate c ORDER BY c.id"
    ).fetchall()
    return CrateSummary.from_rows(rows)


def stale(con: sqlite3.Connection) -> list[CrateSummary]:
    """Registered crates whose files have moved, changed or vanished."""
    recorded = {
        r["id"]: (r["mtime"], r["size"])
        for r in con.execute("SELECT id, mtime, size FROM crate")
    }
    out = []
    for crate in list_crates(con):
        try:
            stat = Path(crate.path).stat()
        except OSError:
            out.append(crate)
            continue
        if recorded[crate.id] != (stat.st_mtime, stat.st_size):
            out.append(crate)
    return out


def neighbors(con: sqlite3.Connection, entity_id: str) -> dict[str, list[dict]]:
    """Edges into and out of one @id, for relationship browsing."""
    out = con.execute(
        "SELECT predicate, object FROM edge WHERE subject = ? "
        "ORDER BY predicate, position", (entity_id,),
    ).fetchall()
    inc = con.execute(
        "SELECT predicate, subject FROM edge WHERE object = ? "
        "ORDER BY predicate LIMIT 500", (entity_id,),
    ).fetchall()
    return {
        "outgoing": [{"predicate": r["predicate"], "@id": r["object"]} for r in out],
        "incoming": [{"predicate": r["predicate"], "@id": r["subject"]} for r in inc],
    }
