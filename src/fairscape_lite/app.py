"""The whole HTTP surface: twelve endpoints over a SQLite index.

Deployment posture -- read this before exposing the port
--------------------------------------------------------
This is the *shared-filesystem* server, and it has no auth: it is meant
for localhost, or for a network segment you already trust. Registration
hands the server a path on the local filesystem and it indexes what it
finds there. It never receives an upload, never copies a crate, and
never serves file bytes -- `contentUrl` resolves for a peer because the
peer mounts the same tree (or because the URL points at Dataverse, as it
does for most CM4AI crates).

FAIRSCAPE_LITE_ROOT confines registration to one directory. Without it,
anyone who can reach the port can ask the server to read any
world-readable JSON on the host and then serve it back. It is unset by
default, which is right for `localhost` and wrong for anything else.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterator, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ValidationError

from . import db, graph
from .models import Identifier, validate_crate

CRATE_ROOT = os.environ.get("FAIRSCAPE_LITE_ROOT")

app = FastAPI(
    title="fairscape_lite",
    version="0.1.0",
    description=__doc__,
)


def connection() -> Iterator[sqlite3.Connection]:
    con = db.connect()
    try:
        yield con
    finally:
        con.close()


def checked_path(raw: str) -> Path:
    """Resolve a registration path, refusing anything outside CRATE_ROOT."""
    path = Path(raw).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        raise HTTPException(404, f"no such path: {raw}")

    if CRATE_ROOT:
        root = Path(CRATE_ROOT).expanduser().resolve()
        if not resolved.is_relative_to(root):
            raise HTTPException(403, f"path is outside FAIRSCAPE_LITE_ROOT ({root})")
    return resolved


def envelope(con: sqlite3.Connection, entity) -> dict:
    """Wrap one entity in the resolver envelope, reading its node back."""
    try:
        node = db.metadata(con, entity)
    except db.MissingCrateFile as exc:
        raise HTTPException(409, str(exc))
    if node is None:
        raise HTTPException(
            404,
            f"{entity.id} is indexed but no longer in {entity.source_crate}; "
            "the index is stale (POST /rocrate/reingest)",
        )
    return Identifier(
        guid=entity.id,
        metadataType=entity.type_list,
        metadata=node,
        sourceCrate=entity.source_crate,
    ).dump()


def must_resolve(con: sqlite3.Connection, identifier: str):
    entity = db.resolve(con, identifier)
    if entity is None:
        raise HTTPException(404, f"{identifier} not found")
    return entity


class Registration(BaseModel):
    path: str          # a ro-crate-metadata.json, or a directory to walk
    force: bool = False


# --------------------------------------------------------------------------
# Crates
# --------------------------------------------------------------------------

@app.post("/rocrate")
def register(body: Registration, con=Depends(connection)):
    """Index one crate, or every crate under a directory.

    A directory walks (that is how a whole shared mount gets indexed); a
    file registers just itself. The file is parsed once here, validated
    against fairscape_models, and the same parse is handed to the indexer.
    """
    path = checked_path(body.path)

    if path.is_dir() and not (path / db.METADATA_FILENAME).exists():
        return {"registered": [s.model_dump() for s in
                              db.ingest_tree(con, path, force=body.force,
                                             validate=validate_crate)]}

    file_path = db.metadata_file(path)
    try:
        data = db.read_crate(file_path)
    except db.MissingCrateFile as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    try:
        validate_crate(data)
    except ValidationError as exc:
        raise HTTPException(422, f"not a valid RO-Crate: {exc.error_count()} "
                                 f"problem(s); first: {exc.errors()[0]}")

    try:
        stats = db.ingest(con, file_path, data=data, force=body.force)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except db.MissingCrateFile as exc:
        raise HTTPException(404, str(exc))
    return stats.model_dump()


@app.get("/rocrate")
def crates(con=Depends(connection)):
    return {"crates": [c.model_dump() for c in db.list_crates(con)]}


@app.get("/rocrate/stale")
def stale_crates(con=Depends(connection)):
    """Registered crates whose file moved, changed or vanished.

    The cost of indexing rather than copying: this is the one way the
    index can be wrong, so it is enumerable rather than hidden.
    """
    return {"stale": [c.model_dump() for c in db.stale(con)]}


@app.post("/rocrate/reingest")
def reingest(con=Depends(connection)):
    """Re-read every registered crate file in place."""
    return {"reingested": [s.model_dump() for s in db.reingest_all(con)]}


@app.get("/rocrate/metadata")
def crate_metadata(
    id: str = Query(description="the crate root's @id"),
    con=Depends(connection),
):
    """The crate's ro-crate-metadata.json, verbatim off disk."""
    entity = must_resolve(con, id)
    try:
        return db.crate_json(con, entity.id)
    except db.MissingCrateFile as exc:
        raise HTTPException(409, str(exc))


@app.delete("/rocrate")
def unregister(
    id: str = Query(description="the crate root's @id"),
    con=Depends(connection),
):
    """Forget a crate and everything it supplied.

    Entities another crate contributed are untouched; entities *this*
    crate owned go, even where another crate's file also contains them.
    Re-register that crate to bring them back.
    """
    entity = must_resolve(con, id)
    if not db.forget(con, entity.id):
        raise HTTPException(404, f"{id} is not a registered crate")
    return {"forgotten": entity.id}


# --------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------

@app.get("/ark:{naan}/{postfix:path}")
def resolve_ark(naan: str, postfix: str, con=Depends(connection)):
    """Resolve an ARK. Dashes are optional; this is the web client's route."""
    return envelope(con, must_resolve(con, f"ark:{naan}/{postfix}"))


@app.get("/identifier")
def resolve_any(
    id: str = Query(description="any @id: ARK, URL or relative path"),
    con=Depends(connection),
):
    """Resolve any @id.

    A quarter of the local corpus (59k of 229k nodes) has URL-form @ids,
    which cannot be spelled as a path segment -- hence the query param.
    """
    return envelope(con, must_resolve(con, id))


@app.get("/entity")
def entities(
    crate: Optional[str] = Query(default=None, description="scope to one crate @id"),
    type: Optional[str] = Query(default=None, description="Dataset, Computation, ..."),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    con=Depends(connection),
):
    """List entities, newest crate registration last. Index columns only."""
    if crate:
        crate = must_resolve(con, crate).id
    found = db.list_entities(con, crate=crate, entity_type=type,
                             limit=limit, offset=offset)
    return {"entities": [e.model_dump() for e in found]}


@app.get("/entity/links")
def entity_links(
    id: str = Query(description="any @id: ARK, URL or relative path"),
    con=Depends(connection),
):
    """Every indexed edge into and out of one @id.

    Outgoing is what the node itself asserts (hasPart, generatedBy, used*);
    incoming is what other nodes assert about it -- which crates contain
    it, which computations used it. That second direction is the question
    a crate file alone cannot answer, and the reason the edge table exists.
    """
    entity = must_resolve(con, id)
    return {"@id": entity.id, **db.neighbors(con, entity.id)}


@app.get("/search")
def search(
    q: str = Query(min_length=1, description="full-text query"),
    limit: int = Query(default=25, ge=1, le=500),
    con=Depends(connection),
):
    """Full-text search over name, description and keywords."""
    return {"query": q, "results": [r.model_dump() for r in db.search(con, q, limit)]}


# --------------------------------------------------------------------------
# Evidence graphs
# --------------------------------------------------------------------------

def _evidence_graph(con, identifier: str, threshold: Optional[int]) -> dict:
    entity = must_resolve(con, identifier)
    try:
        built = graph.build(con, entity.id, threshold=threshold)
    except db.MissingCrateFile as exc:
        raise HTTPException(409, str(exc))
    return Identifier(
        guid=built["@id"],
        metadataType=built["@type"],
        metadata=built,
        sourceCrate=entity.source_crate,
    ).dump()


@app.get("/evidencegraph/ark:{naan}/{postfix:path}")
def evidence_graph_ark(
    naan: str, postfix: str,
    condense: Optional[int] = Query(
        default=graph.CONDENSE_THRESHOLD, ge=0,
        description="group look-alike siblings above this many; 0 disables",
    ),
    con=Depends(connection),
):
    """Build the evidence graph for an ARK, fresh, on every request."""
    return _evidence_graph(con, f"ark:{naan}/{postfix}", condense or None)


@app.get("/evidencegraph")
def evidence_graph_any(
    id: str = Query(description="any @id: ARK, URL or relative path"),
    condense: Optional[int] = Query(default=graph.CONDENSE_THRESHOLD, ge=0),
    con=Depends(connection),
):
    return _evidence_graph(con, id, condense or None)


# --------------------------------------------------------------------------
# Web UI
# --------------------------------------------------------------------------
# The viewer in web/ builds to web/dist and is served under /ui/ so the API
# keeps the origin root -- client routes can never shadow /rocrate, /search
# or /ark:... . Only active when a build exists; the API alone still works.

# web/ lives at the repo root, two levels above this src/ package. An env
# override covers installs where the package no longer sits in a checkout.
WEB_DIST = Path(
    os.environ.get("FAIRSCAPE_LITE_UI",
                   Path(__file__).resolve().parents[2] / "web" / "dist")
)

if WEB_DIST.is_dir():
    from fastapi.responses import FileResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/ui/assets", StaticFiles(directory=WEB_DIST / "assets"), name="ui-assets")

    @app.get("/", include_in_schema=False)
    def ui_redirect():
        return RedirectResponse("/ui/")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/{rest:path}", include_in_schema=False)
    def ui_spa(rest: str = ""):
        """SPA fallback: every /ui route serves the same index.html."""
        return FileResponse(WEB_DIST / "index.html")
