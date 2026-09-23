"""Uploaded crates: the one place this server owns files.

Registration indexes crates where they already are. Upload is for the
peer who has no shared mount: they POST a zip, or a bare
ro-crate-metadata.json, and the server unpacks it under UPLOAD_DIR and
then indexes it exactly as if it had been registered by path. After
that the crate is an ordinary registered crate -- `path` in the crate
table points at the unpacked metadata file, and metadata reads, stale
detection, reingest and delete all work on it unchanged.

The rule that keeps local references working
--------------------------------------------
A FAIRSCAPE crate points at its own files crate-relatively:
`file:///data/foo.csv` (fairscape-cli's spelling: the `file://` scheme
with an empty host, the rest a path relative to the crate) or a bare
`data/foo.csv`. Both mean "next to my ro-crate-metadata.json". Such a
reference survives any move as long as the directory that contains the
metadata file moves with everything under it, unchanged.

So a zip is unpacked verbatim: every member at the path it had in the
archive, wrapping folder included, into one directory per crate.
Nothing is flattened, renamed or re-rooted, and no member of the
archive is rewritten. `local_files()` then walks the crate's local
references and says which ones resolve on disk -- the upload response
carries that report, and GET /rocrate/files serves it for any
registered crate, so "where is the file for dataset X" is one call.

The per-crate directory is named from the root @id (readable slug plus
a short hash of the exact id). Uploading a crate again therefore
replaces its previous copy in place rather than leaving a second one
behind. A zip replaces the whole directory; a bare metadata file
replaces only the metadata file, so re-uploading an edited
ro-crate-metadata.json keeps the data files that came with the zip.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable, Optional
from urllib.parse import unquote

from . import db

# Like the index: uploads land in the working directory unless told
# otherwise. Uploads are the server's own files, so FAIRSCAPE_LITE_ROOT
# (which confines what a *client* may point registration at) does not
# apply to them.
UPLOAD_DIR = Path(os.environ.get("FAIRSCAPE_LITE_UPLOADS", "uploads"))

# Cap on the unpacked size of one zip, checked against the archive's
# own directory before anything is written. A zip bomb declares its
# true size there; a lying one fails the same check during extraction.
MAX_UNPACKED_BYTES = int(os.environ.get("FAIRSCAPE_LITE_MAX_UNPACKED", 8 * 2**30))

METADATA_FILENAME = db.METADATA_FILENAME

# Archive members that are packaging noise, never crate content.
JUNK_DIRS = {"__MACOSX"}
JUNK_FILES = {".DS_Store", "Thumbs.db"}

# fairscape-cli writes this literal in place of a contentUrl for data
# that is deliberately withheld. It is not a path.
EMBARGOED = "Embargoed"

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class BadUpload(ValueError):
    """The upload cannot become a crate. Maps to HTTP 422."""


class TooLarge(BadUpload):
    """The archive would unpack past MAX_UNPACKED_BYTES. Maps to 413."""


@dataclass
class Unpacked:
    """What `receive` produced on disk."""

    root_id: str
    directory: Path         # this crate's directory under UPLOAD_DIR
    metadata: Path          # the root ro-crate-metadata.json inside it
    data: dict              # the parsed root metadata
    kind: str               # "zip" or "metadata"
    members: int = 0        # archive members written (zip only)
    skipped: list[str] = field(default_factory=list)   # junk members left out


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------

def crate_dirname(root_id: str) -> str:
    """A filesystem name for one crate, stable across uploads.

    `ark:59852/rocrate-foo-bar` -> `ark-59852-rocrate-foo-bar-1a2b3c4d`.
    The slug is for the person browsing UPLOAD_DIR; the hash is what
    makes two @ids that slug alike still get two directories.
    """
    digest = hashlib.sha1(root_id.encode()).hexdigest()[:8]
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", root_id).strip("-.")[:80] or "crate"
    return f"{slug}-{digest}"


def crate_directory(root_id: str) -> Path:
    return UPLOAD_DIR / crate_dirname(root_id)


def is_uploaded(path: str | os.PathLike) -> bool:
    """True if `path` lies under UPLOAD_DIR: files this server owns."""
    try:
        return Path(path).resolve().is_relative_to(UPLOAD_DIR.resolve())
    except OSError:
        return False


# --------------------------------------------------------------------------
# Local references
# --------------------------------------------------------------------------

def local_reference(url) -> Optional[str]:
    """The crate-relative path a contentUrl names, or None if it is not local.

    `file:///data/x.csv` and `file://data/x.csv` both -> `data/x.csv`, as
    fairscape-cli, fairscape_models and the grader all read them. A bare
    relative path is itself. Anything with another scheme (http, ftp,
    ark, doi...) is remote, and an absolute path names a file on the
    uploader's machine, which is not something this server can find.
    """
    if not isinstance(url, str) or not url or url == EMBARGOED:
        return None
    if url.startswith("file://"):
        rel = unquote(url[len("file://"):]).lstrip("/")
        return rel or None
    if _SCHEME.match(url):
        return None
    if PurePosixPath(url).is_absolute() or Path(url).is_absolute():
        return None
    return url


def _content_urls(node: dict) -> list[str]:
    value = node.get("contentUrl")
    items = value if isinstance(value, list) else [value]
    return [v for v in items if isinstance(v, str)]


def local_files(data: dict, crate_dir: Path) -> list[dict]:
    """Every local contentUrl in the crate, resolved against its directory.

    One row per reference: the node, the URL as written, the absolute
    path it names on this server, and whether that path exists. This is
    the answer to "the metadata says file:///data/x.csv; where is it".
    """
    rows = []
    for node in data.get("@graph") or []:
        if not isinstance(node, dict) or not isinstance(node.get("@id"), str):
            continue
        for url in _content_urls(node):
            rel = local_reference(url)
            if rel is None:
                continue
            path = crate_dir / rel
            rows.append({
                "@id": node["@id"],
                "name": node.get("name") if isinstance(node.get("name"), str) else None,
                "contentUrl": url,
                "path": str(path),
                "exists": path.exists(),
            })
    return rows


def file_report(rows: list[dict], limit: int = 50) -> dict:
    """The compact form the upload response carries."""
    missing = [r for r in rows if not r["exists"]]
    return {
        "local": len(rows),
        "found": len(rows) - len(missing),
        "missing": [
            {"@id": r["@id"], "contentUrl": r["contentUrl"]} for r in missing[:limit]
        ],
        "missing_truncated": len(missing) > limit,
    }


# --------------------------------------------------------------------------
# Archive inspection
# --------------------------------------------------------------------------

def _is_junk(name: str) -> bool:
    parts = PurePosixPath(name).parts
    return bool(parts) and (parts[0] in JUNK_DIRS or parts[-1] in JUNK_FILES)


def _check_member_name(name: str) -> None:
    """Reject names that would escape the destination (zip slip).

    zipfile.extract would quietly sanitise these. A crate archive has no
    business containing them, so refusing is more honest than rewriting.
    """
    pure = PurePosixPath(name)
    if pure.is_absolute() or name.startswith(("/", "\\")) or ".." in pure.parts:
        raise BadUpload(f"archive member escapes the crate directory: {name!r}")
    if re.match(r"^[A-Za-z]:", name):
        raise BadUpload(f"archive member has a drive letter: {name!r}")


def find_root_member(archive: zipfile.ZipFile) -> str:
    """The archive member that is the root crate's metadata file.

    The shallowest `ro-crate-metadata.json` wins; anything deeper is a
    sub-crate and gets registered by the tree walk. Two at the same
    shallowest depth means the archive is two crates, not one, and there
    is no root @id to name a directory after -- so that is refused.
    """
    candidates = [
        n for n in archive.namelist()
        if not _is_junk(n) and PurePosixPath(n).name == METADATA_FILENAME
    ]
    if not candidates:
        raise BadUpload(f"archive contains no {METADATA_FILENAME}")
    depth = {n: len(PurePosixPath(n).parts) for n in candidates}
    shallowest = min(depth.values())
    roots = sorted(n for n, d in depth.items() if d == shallowest)
    if len(roots) > 1:
        raise BadUpload(
            f"archive holds {len(roots)} crates side by side "
            f"({', '.join(roots[:3])}...); upload one crate per archive"
        )
    return roots[0]


def inspect(archive: zipfile.ZipFile) -> tuple[list[zipfile.ZipInfo], list[str]]:
    """Members to extract, and the junk left out. Raises before any write."""
    keep, skipped, total = [], [], 0
    for info in archive.infolist():
        if _is_junk(info.filename):
            skipped.append(info.filename)
            continue
        _check_member_name(info.filename)
        total += info.file_size
        keep.append(info)
    if total > MAX_UNPACKED_BYTES:
        raise TooLarge(
            f"archive unpacks to {total} bytes; the limit is {MAX_UNPACKED_BYTES} "
            "(FAIRSCAPE_LITE_MAX_UNPACKED)"
        )
    return keep, skipped


def _parse(raw: bytes, label: str) -> dict:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BadUpload(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise BadUpload(f"{label} is not a JSON object")
    return data


def _root_id(data: dict, validate: Optional[Callable[[dict], None]]) -> str:
    if validate is not None:
        validate(data)          # pydantic ValidationError is a ValueError
    return db.find_root(data)[1]


# --------------------------------------------------------------------------
# Landing files
# --------------------------------------------------------------------------

def _staging_dir() -> Path:
    """A fresh directory beside the final one, so the rename is atomic."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    staging = UPLOAD_DIR / f".incoming-{uuid.uuid4().hex}"
    staging.mkdir()
    return staging


def _swap_in(staging: Path, dest: Path) -> None:
    """Replace `dest` with `staging`, restoring `dest` if the swap fails."""
    trash = None
    if dest.exists():
        trash = UPLOAD_DIR / f".trash-{uuid.uuid4().hex}"
        dest.rename(trash)
    try:
        staging.rename(dest)
    except OSError:
        if trash is not None:
            trash.rename(dest)
        raise
    if trash is not None:
        shutil.rmtree(trash, ignore_errors=True)


def _receive_zip(
    source: Path, validate: Optional[Callable[[dict], None]]
) -> Unpacked:
    with zipfile.ZipFile(source) as archive:
        keep, skipped = inspect(archive)
        member = find_root_member(archive)
        data = _parse(archive.read(member), member)
        root_id = _root_id(data, validate)

        dest = crate_directory(root_id)
        staging = _staging_dir()
        try:
            written = 0
            for info in keep:
                archive.extract(info, staging)
                written += 1
            _swap_in(staging, dest)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    return Unpacked(
        root_id=root_id, directory=dest, metadata=dest / Path(*PurePosixPath(member).parts),
        data=data, kind="zip", members=written, skipped=skipped,
    )


def _receive_metadata(
    source: Path,
    validate: Optional[Callable[[dict], None]],
    existing: Optional[Path],
) -> Unpacked:
    """A bare ro-crate-metadata.json.

    If this crate was uploaded before, and its metadata file still sits
    under its upload directory, only that file is replaced -- the data
    files a previous zip brought stay where they are. Otherwise the file
    becomes a one-file crate directory and every local reference in it
    is reported missing, which is the truth.
    """
    data = _parse(source.read_bytes(), "upload (not a zip archive, so read as ro-crate-metadata.json)")
    root_id = _root_id(data, validate)
    dest = crate_directory(root_id)

    target = dest / METADATA_FILENAME
    if existing is not None and existing.name == METADATA_FILENAME:
        try:
            if existing.resolve().is_relative_to(dest.resolve()) and existing.exists():
                target = existing
        except OSError:
            pass

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{METADATA_FILENAME}.{uuid.uuid4().hex}")
    shutil.copyfile(source, tmp)
    os.replace(tmp, target)

    return Unpacked(root_id=root_id, directory=dest, metadata=target,
                    data=data, kind="metadata")


def receive(
    source: Path,
    validate: Optional[Callable[[dict], None]] = None,
    existing: Optional[Path] = None,
) -> Unpacked:
    """Land an uploaded file (already spooled to `source`) under UPLOAD_DIR.

    `validate` runs on the root metadata before anything is written, so
    a rejected upload leaves no directory behind. `existing` is the
    metadata path this crate is currently registered at, if any; it
    only matters for the bare-metadata case.
    """
    if zipfile.is_zipfile(source):
        return _receive_zip(source, validate)
    return _receive_metadata(source, validate, existing)


def spool(stream: BinaryIO) -> Path:
    """Copy an upload stream to a temp file under UPLOAD_DIR.

    Same filesystem as the destination, so nothing here depends on the
    size of /tmp, and zipfile can seek in it. The caller unlinks it.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f".upload-{uuid.uuid4().hex}"
    with open(path, "wb") as handle:
        shutil.copyfileobj(stream, handle, length=1 << 20)
    return path


def purge(crate_file: str | os.PathLike) -> Optional[str]:
    """Delete the upload directory that holds `crate_file`, if it is one.

    Refuses anything outside UPLOAD_DIR: registered-by-path crates are
    the user's files, and this server never deletes those. Returns the
    directory removed, or None if nothing was.
    """
    path = Path(crate_file)
    if not is_uploaded(path):
        return None
    root = UPLOAD_DIR.resolve()
    directory = path.resolve().parent
    # Walk up to the per-crate directory: the immediate child of UPLOAD_DIR.
    while directory.parent != root and directory != root:
        directory = directory.parent
    if directory == root:
        return None
    shutil.rmtree(directory, ignore_errors=True)
    return str(directory)
