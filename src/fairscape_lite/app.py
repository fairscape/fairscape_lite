"""The whole HTTP surface: fourteen endpoints over a SQLite index.

Deployment posture -- read this before exposing the port
--------------------------------------------------------
This is the *shared-filesystem* server, and it has no auth: it is meant
for localhost, or for a network segment you already trust. Registration
hands the server a path on the local filesystem and it indexes what it
finds there, copying nothing. Upload is the one exception: a peer with
no shared mount POSTs a zip and the server unpacks it under
FAIRSCAPE_LITE_UPLOADS, then registers the result like any other path
(see upload.py for how local file references are kept intact). The
server still never serves file bytes -- a local `contentUrl` resolves
because the peer mounts the same tree, or because GET /rocrate/files
tells them the path.

FAIRSCAPE_LITE_ROOT confines registration to one directory. Without it,
anyone who can reach the port can ask the server to read any
world-readable JSON on the host and then serve it back. It is unset by
default, which is right for `localhost` and wrong for anything else.
Uploads are not confined by it -- they land where the server chooses --
but anyone who can reach the port can fill the disk up to
FAIRSCAPE_LITE_MAX_UNPACKED per request.
"""

from __future__ import annotations

import os
import sqlite3
import zipfile
from pathlib import Path
import ijson
import zipfile
from typing import Iterator, Optional, Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import sessionmaker, session
from sqlalchemy import select, func
from collections import defaultdict
import sqlalchemy
import re

from fairscape_models.sql.models import (
    MetadataTypeEnumSQL, 
    IdentifiersSQL,
    ROCrateRegistration,
    ROCrateMetadataElemSQL,
    DatasetSQL,
    SoftwareSQL,
    ComputationSQL,
    ComputationUsedDatasetSQL,
    ComputationGeneratedDatasetSQL,
    MembershipSQL,
)
from fairscape_models.sql.utils import DetermineMetadataTypeSQL


from . import db, graph, upload as uploads
from .models import Identifier, validate_crate
from .config import SQLConfig, FilepathConfig

CRATE_ROOT = os.environ.get("FAIRSCAPE_LITE_ROOT")

app = FastAPI(
    title="fairscape_lite",
    version="0.1.0",
    description=__doc__,
)

# creating sql config
sql_config = SQLConfig(filepath="/tmp/fairscape.db")
sql_engine = sql_config.engine()
session_factory = sessionmaker(bind=sql_engine)

storage = FilepathConfig("/tmp/server_content")

def get_connection()->session:
    return session_factory()    

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


def invalid_crate(exc: ValidationError) -> HTTPException:
    return HTTPException(422, f"not a valid RO-Crate: {exc.error_count()} "
                              f"problem(s); first: {exc.errors()[0]}")


class Registration(BaseModel):
    path: str          # a ro-crate-metadata.json, or a directory to walk
    force: bool = False

# --------------------------------------------------------------------------
# Crate Crud Functions
# --------------------------------------------------------------------------
def getZipInfo(zip_ref, path_within_zip):
    try:
        return zip_ref.getinfo(path_within_zip)
    except KeyError:
        return None

def findRootMetadata(input_filepath, input_filename)->zipfile.ZipInfo:
    with zipfile.ZipFile(input_filepath) as zip_ref:
    # With local file tests
    #with zipfile.ZipFile(str(input_filepath), 'r') as zip_ref:
        # is ro-crate-metadata.json at the top of the directory
        name = 'ro-crate-metadata.json'
        results = getZipInfo(zip_ref, name)	

        # within the zip a folder named as the stem with ro-crate-metadata.json
        if not results:
            name = f"{Path(input_filename).stem}/{name}"
            results = getZipInfo(zip_ref, name)	

        # default to search namelist
        if not results:
            namelist = zip_ref.infolist()
            matchingROCrates = [ elem for elem in namelist if 'ro-crate-metadata.json' in elem]

            if len(matchingROCrates) == 0:
                raise Exception(f"No ROCrate Found within Zip {input_filename}")
            else:
                results = matchingROCrates[0]

        return results

def getBasicRootMetadata(input_filepath, input_filename):
    """ Return ROCrate GUID, Name, and Version from zipped input file"""
    root_metadata = findRootMetadata(input_filepath, input_filename)
    metadata_path_within_zip = root_metadata.filename

    with zipfile.ZipFile(input_filepath) as zip_ref:
    # With local file tests
    #with zipfile.ZipFile(str(input_filepath), 'r') as zip_ref:
        f = zip_ref.open(metadata_path_within_zip)
        objects = ijson.items(f, '@graph.item')
        rocrates = [ 
            {
                "@id": o.get("@id"), 
                "name": o.get("name"), 
                "version": o.get("version")
            } for o in objects if "https://w3id.org/EVI#ROCrate" in o.get('@type')]

    return rocrates[0]

def determineVersion(session, crate_guid: str) -> int:
    """ Determine version for input rocrate"""
    max_version_query = select(func.max(ROCrateRegistration.version)).filter_by(guid=crate_guid)
    max_version_results = session.scalar(max_version_query)

    if not max_version_results:
        input_version = 1
    # if it exists set the version 
    else:
        input_version = max_version_results + 1

    return input_version

def writeOutputFile(input_file, output_path: Path):
    """ Write out input ROCrate to Output Path"""
    input_file.seek(0)

    chunk_size = 65536
    output_path.parent.mkdir(exist_ok=True, parents=True)
    with output_path.open("wb") as output_file:
        while True:
            chunk = input_file.read(chunk_size)
            if not chunk:
                break
            output_file.write(chunk)

# Crate Registration

def sanitize_ark(input_guid: str)->str:
    """ Given an input GUID strip out the ark, if no ark is present return the existing string
    """
    identifier_expression = r'ark:[0-9]{5}/[a-zA-Z0-9_-]+.$'
    ark_matches = re.search(identifier_expression, input_guid)

    if ark_matches:
        return ark_matches.group()
    else:
        return input_guid

def processIdentifierValue(input_list)->list[str]:
    """ Convert a list of Identifiers which may come as strings or dictionaries into a list of strings
    
    
    e.g.
        [
            "doi:9999/test",
            {"@id": "ark:59853/example"}	
        ]	

        returns ["doi:9999/test", "@id": "ark:59853/example"]
    """
    output_list = []
    for elem in input_list:
        if isinstance(elem, dict):
            output_list.append(sanitize_ark(elem.get("@id")))
        elif isinstance(elem, str): 
            output_list.append(sanitize_ark(elem))

    return output_list


def writeComputationProv(session, computation_generator):
    for comp in computation_generator:
        comp_guid = sanitize_ark(comp.get("@id"))

        comp_generated = processIdentifierValue(comp.get("generated"))
        comp_used_dataset = processIdentifierValue(comp.get("usedDataset"))

        generated_prov_rows = [ {
            "computationGUID": comp_guid,
            "datasetGUID": gen_ds 
        } for gen_ds in comp_generated]

        used_prov_rows = [ {
            "computationGUID": comp_guid,
            "datasetGUID": gen_ds 
        } for gen_ds in comp_used_dataset]

        session.execute(
            sqlalchemy.insert(ComputationGeneratedDatasetSQL), 
            generated_prov_rows
        )	

        session.execute(
            sqlalchemy.insert(ComputationUsedDatasetSQL), 
            used_prov_rows
        )	

selectDictKeys = lambda inputData, keyList: { key: inputData.get(key) for key in keyList}

ROCrateMetadataElemDictKeys = ["name", "description", "keywords", "version", "datePublished"]
DatasetDictKeys = ["name", "description", "keywords", "version", "datePublished"]
SoftwareDictKeys = ["name", "description", "keywords", "version", "datePublished"]
ComputationDictKeys = ["name", "description", "keywords", "dateCreated"]


TABLE_SPECS = {
    MetadataTypeEnumSQL.DATASET:     (DatasetSQL,     DatasetDictKeys,     "author"),
    MetadataTypeEnumSQL.SOFTWARE:    (SoftwareSQL,    SoftwareDictKeys,    "author"),
    MetadataTypeEnumSQL.COMPUTATION: (ComputationSQL, ComputationDictKeys, "runBy"),
    MetadataTypeEnumSQL.ROCRATE: (ROCrateMetadataElemSQL, ROCrateMetadataElemDictKeys, "author")
}


def transformDictAuthor(input_author)->list:
    if isinstance(input_author, str):
        author_list = [ auth_elem.lstrip(" ") for auth_elem in re.split(f'[,&]', input_author)]

    elif isinstance(input_author, list):
        # TODO processing and cleaning list of authors
        author_list = input_author

        # list of strings

        # list of dictionary
    return author_list


def uploadMetadata(session, metadata_fp):
    """ Given an open metadata file and a session to a database, process all ro-crate-metadata.json entities into SQL"""
    rows = defaultdict(list)
    computations, identifiers, members = [], [], []
    rocrate_guid = None

    metadata_fp.seek(0)
    for o in ijson.items(metadata_fp, "@graph.item"):
        guid = sanitize_ark(o.get("@id"))

        if guid == "ro-crate-metadata.json":
            rocrate_guid = sanitize_ark(o.get("about", {}).get("@id"))
            continue
        
        members.append({"childGUID": guid, "childType": mtype})

        # check if guid exists in the identifier table
        # if the guid exists, i.e. a piece of software being used in multiple ro-crates
        # it will not be added again to the transaction
        guid_exists = session.query(IdentifiersSQL.guid).filter_by(guid=guid).count()

        if guid_exists>0:
            continue
                    
        mtype = DetermineMetadataTypeSQL(o.get("@type"))   # classify once
        identifiers.append({"guid": guid, "name": o.get("name"), "metadataType": mtype})


        spec = TABLE_SPECS.get(mtype)
        if spec:
            model, keys, author_field = spec
            row_data = {
                "guid": guid,
                "author": transformDictAuthor(o.get(author_field)),
                "fileFormat": o.get("format"),
                **selectDictKeys(o, keys),
            }

            if mtype == MetadataTypeEnumSQL.COMPUTATION:
                computations.append(o)
                # adding usedSoftware prov to computation
                usedSoftware = processIdentifierValue(o.get("usedSoftware"))

                if isinstance(usedSoftware, list):
                    if len(usedSoftware) == 1:
                        row_data['usedSoftware'] = usedSoftware[0]
            
            rows[model].append(row_data)

    if rocrate_guid is None:
        raise ValueError("ro-crate-metadata.json descriptor not found")
    for m in members:
        m["parentGUID"] = rocrate_guid
        m["parentType"] = MetadataTypeEnumSQL.ROCRATE

    # Writes
    for model in (DatasetSQL, SoftwareSQL, ComputationSQL):
        if rows[model]:
            session.execute(sqlalchemy.insert(model), rows[model])

    writeComputationProv(session, iter(computations))

    if identifiers:
        session.execute(sqlalchemy.insert(IdentifiersSQL), identifiers)
    if members:
        session.execute(sqlalchemy.insert(MembershipSQL), members)
    session.commit()


# --------------------------------------------------------------------------
# Crates
# --------------------------------------------------------------------------
@app.post("/validate")
def validate_registration(conn=Depends(get_connection)):
    pass

@app.post("/upload")
def upload(inputFile: UploadFile, conn=Depends(get_connection)):
    if not inputFile:
        return {"error": "file cannot be null"}
    if not inputFile.filename:
        return {"error": "file missing filename"}

    # get the metadata from the input file
    input_metadata = getBasicRootMetadata(inputFile.file, inputFile.filename)
    input_crate_guid = input_metadata.get("@id")

    if not input_crate_guid:
        return {"error": "@id not found"}
    
    input_version = determineVersion(conn, input_crate_guid)

    input_file_stem = Path(inputFile.filename).stem
    output_path = storage.storageFilepath / input_file_stem / f"v{input_version}" / inputFile.filename 

    new_registration = ROCrateRegistration(
        guid = input_crate_guid,
        filepath = str(output_path),
        version = input_version,
        processed = False
    )
    conn.add(new_registration)
    conn.commit()
    response = {
        "@id": new_registration.guid, 
        "upload_id": new_registration.id,
        "filepath": new_registration.filepath,
        "version": new_registration.version,
        "time_registered": new_registration.time_registered,
        "processed": False
    }

    conn.close()

    # write the output file
    writeOutputFile(inputFile.file, output_path)

    # return the registration 
    return response 


@app.get("/upload")
def list_uploads(conn=Depends(get_connection)):
    upload_query = select(ROCrateRegistration)
    upload_results = conn.scalars(upload_query)

    return [{
        "@id": up.guid,
        "filepath": up.filepath,
        "version": up.version,
        "processed": up.processed
    }
    for up in upload_results]


@app.post("/register")
def register_rocrate(upload_id: int, conn=Depends(get_connection)):
    # find registered rocrate
    matched_crate = conn.query(ROCrateRegistration).filter_by(id=upload_id).first()

    if not matched_crate:
        return {"error": "ROCrate Upload not found"}

    if matched_crate.processed:
        return {"error": "ROCrate is already processed"}

    crate_filepath = Path(matched_crate.filepath)
    with crate_filepath.open("rb") as open_crate_file:
        root_metadata_within_zip = findRootMetadata(
            input_filepath =  open_crate_file,
            input_filename=crate_filepath.name
        ).filename

    zip_ref = zipfile.ZipFile(str(crate_filepath), 'r')
    open_metadata_file = zip_ref.open(root_metadata_within_zip)

    uploadMetadata(session=conn, metadata_fp=open_metadata_file)

    open_metadata_file.close()

    # update the ROCrateRegistration to set processed to true
    matched_crate.processed = True
    conn.commit()
    

    return {"registered": {"@id": matched_crate.guid}}


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
        raise invalid_crate(exc)

    try:
        stats = db.ingest(con, file_path, data=data, force=body.force)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except db.MissingCrateFile as exc:
        raise HTTPException(404, str(exc))
    return stats.model_dump()


@app.post("/rocrate/upload")
def upload_crate(
    file: UploadFile = File(description="a .zip of the crate directory, or a bare "
                                        "ro-crate-metadata.json"),
    con=Depends(connection),
):
    """Receive a crate the client has no shared path for, then index it.

    The archive is unpacked verbatim under FAIRSCAPE_LITE_UPLOADS -- the
    directory that holds ro-crate-metadata.json arrives with everything
    under it at the same relative paths, which is exactly what keeps a
    `file:///data/x.csv` or `data/x.csv` contentUrl pointing at the
    right file. Sub-crates in the archive are registered too. The
    response says where the crate landed and which of its local
    references resolve there; GET /rocrate/files repeats that later.

    A bare ro-crate-metadata.json is accepted as well. For a crate
    uploaded before, it replaces only the metadata file and keeps the
    data files; otherwise it becomes a one-file crate whose local
    references are all reported missing.

    Always re-indexes (unpacked files have fresh mtimes), so this is
    also how a peer updates a crate: upload it again.
    """
    source = uploads.spool(file.file)
    try:
        try:
            unpacked = uploads.receive(
                source, validate=validate_crate,
                existing=_registered_path(con, source),
            )
        except uploads.TooLarge as exc:
            raise HTTPException(413, str(exc))
        except ValidationError as exc:
            raise invalid_crate(exc)
        except (uploads.BadUpload, ValueError, zipfile.BadZipFile) as exc:
            raise HTTPException(422, str(exc))
    finally:
        source.unlink(missing_ok=True)

    registered = db.ingest_tree(con, unpacked.directory, force=True,
                                validate=validate_crate)
    return {
        "crate": unpacked.root_id,
        "kind": unpacked.kind,
        "directory": str(unpacked.directory),
        "path": str(unpacked.metadata),
        "members": unpacked.members,
        "skipped_members": unpacked.skipped,
        "files": uploads.file_report(
            uploads.local_files(unpacked.data, unpacked.metadata.parent)),
        "registered": [s.model_dump() for s in registered],
    }


def _registered_path(con, source: Path) -> Optional[Path]:
    """Where this crate's metadata file already is, for a bare-JSON upload.

    Cheap peek: only a non-zip upload can need it, and the parse is the
    same one `receive` is about to do.
    """
    if zipfile.is_zipfile(source):
        return None
    try:
        root_id = db.find_root(db.read_crate(source))[1]
    except (ValueError, db.MissingCrateFile):
        return None
    path = db.crate_path(con, root_id)
    return Path(path) if path else None


@app.get("/rocrate")
def crates(con=Depends(connection)):
    return {"crates": [c.model_dump() for c in db.list_crates(con)]}


@app.get("/rocrate/files")
def crate_files(
    id: str = Query(description="the crate root's @id"),
    con=Depends(connection),
):
    """Every local contentUrl in a crate, resolved to a path on this host.

    "The metadata says file:///data/x.csv -- where is it?" answered
    for uploaded and path-registered crates alike: the reference is
    joined to the directory holding the crate's ro-crate-metadata.json
    and checked for existence. Remote URLs (https, ftp, ...) are not
    listed; they resolve wherever they point.
    """
    entity = must_resolve(con, id)
    path = db.crate_path(con, entity.id)
    if path is None:
        raise HTTPException(404, f"{id} is not a registered crate")
    try:
        data = db.read_crate(path)
    except db.MissingCrateFile as exc:
        raise HTTPException(409, str(exc))
    crate_dir = Path(path).parent
    return {
        "crate": entity.id,
        "directory": str(crate_dir),
        "uploaded": uploads.is_uploaded(path),
        "files": uploads.local_files(data, crate_dir),
    }


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
    purge: bool = Query(default=False, description="also delete the files, "
                        "if this crate was uploaded"),
    con=Depends(connection),
):
    """Forget a crate and everything it supplied.

    Entities another crate contributed are untouched; entities *this*
    crate owned go, even where another crate's file also contains them.
    Re-register that crate to bring them back.

    `purge` additionally removes the crate's directory, but only when it
    lies under FAIRSCAPE_LITE_UPLOADS. Files registered by path are the
    user's own and are never deleted, whatever the flag says.
    """
    entity = must_resolve(con, id)
    path = db.crate_path(con, entity.id)
    if not db.forget(con, entity.id):
        raise HTTPException(404, f"{id} is not a registered crate")
    purged = uploads.purge(path) if purge and path else None
    return {"forgotten": entity.id, "purged": purged}


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
