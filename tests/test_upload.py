"""POST /rocrate/upload: crates that arrive as bytes, not paths.

The property under test throughout: a local contentUrl written
crate-relatively (`file:///data/x.csv` or `data/x.csv`) still names a
real file after upload, because the archive is unpacked verbatim.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, write_crate
from fairscape_lite import app as app_module
from fairscape_lite import db, upload

ROOT = "ark:99999/rocrate-uploaded"
DATA = "ark:99999/dataset-uploaded-table"


def dataset(guid=DATA, content_url="file:///data/table.csv"):
    return {
        "@id": guid,
        "@type": "https://w3id.org/EVI#Dataset",
        "name": "a table",
        "description": "written by the upload tests",
        "keywords": ["test"],
        "author": "Test Suite",
        "datePublished": "2026-01-01",
        "version": "1.0",
        "format": "text/csv",
        "contentUrl": content_url,
    }


def build_zip(tmp_path: Path, root_id=ROOT, wrapper="my-crate", nodes=None,
              files=None, extra_members=None) -> Path:
    """A crate directory on disk, zipped the way `zip -r` would zip it."""
    nodes = [dataset()] if nodes is None else nodes
    files = {"data/table.csv": "a,b\n1,2\n"} if files is None else files
    crate_dir = tmp_path / "src" / (wrapper or "")
    write_crate(crate_dir, root_id, nodes=nodes)
    for rel, text in files.items():
        (crate_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (crate_dir / rel).write_text(text)

    archive = tmp_path / "crate.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in sorted((tmp_path / "src").rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(tmp_path / "src").as_posix())
        for name, text in (extra_members or {}).items():
            zf.writestr(name, text)
    return archive


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setattr(app_module, "CRATE_ROOT", None)
    monkeypatch.setattr(upload, "UPLOAD_DIR", tmp_path / "uploads")
    with TestClient(app_module.app) as test_client:
        yield test_client


def post(client, path: Path, name=None):
    with open(path, "rb") as handle:
        return client.post("/rocrate/upload",
                           files={"file": (name or path.name, handle)})


def post_bytes(client, raw: bytes, name="ro-crate-metadata.json"):
    return client.post("/rocrate/upload", files={"file": (name, io.BytesIO(raw))})


# --------------------------------------------------------------------------
# The main property
# --------------------------------------------------------------------------

def test_zip_lands_verbatim_and_local_files_still_resolve(client, tmp_path):
    body = post(client, build_zip(tmp_path)).json()

    assert body["crate"] == ROOT and body["kind"] == "zip"
    metadata = Path(body["path"])
    # wrapper folder kept, metadata file where the archive had it
    assert metadata.parts[-2:] == ("my-crate", "ro-crate-metadata.json")
    assert Path(body["directory"]) == metadata.parents[1]
    assert metadata.parents[1].parent == tmp_path / "uploads"
    # file:///data/table.csv means <crate dir>/data/table.csv, and it is there
    assert (metadata.parent / "data" / "table.csv").read_text() == "a,b\n1,2\n"
    assert body["files"] == {"local": 1, "found": 1, "missing": [],
                             "missing_truncated": False}
    assert [r["crate"] for r in body["registered"]] == [ROOT]

    # and it is an ordinary registered crate from here on
    assert client.get(f"/{ROOT}").json()["sourceCrate"] == ROOT
    assert client.get(f"/{DATA}").json()["metadata"]["contentUrl"] == "file:///data/table.csv"
    assert client.get("/rocrate/stale").json() == {"stale": []}
    assert Path(client.get("/rocrate").json()["crates"][0]["path"]) == metadata


def test_files_endpoint_answers_where_is_the_file(client, tmp_path):
    post(client, build_zip(tmp_path))
    body = client.get("/rocrate/files", params={"id": ROOT}).json()
    assert body["uploaded"] is True
    (row,) = body["files"]
    assert row["@id"] == DATA and row["contentUrl"] == "file:///data/table.csv"
    assert row["exists"] is True
    assert Path(row["path"]) == Path(body["directory"]) / "data" / "table.csv"
    assert Path(row["path"]).read_text().startswith("a,b")


def test_files_endpoint_works_for_path_registered_crates_too(client, tmp_path):
    path = write_crate(tmp_path / "local", "ark:99999/by-path",
                       nodes=[dataset("ark:99999/ds-by-path", "data/x.csv")])
    client.post("/rocrate", json={"path": str(path)})
    body = client.get("/rocrate/files", params={"id": "ark:99999/by-path"}).json()
    assert body["uploaded"] is False
    assert body["files"][0]["exists"] is False
    assert Path(body["files"][0]["path"]) == tmp_path / "local" / "data" / "x.csv"
    assert client.get("/rocrate/files", params={"id": "ark:99999/nope"}).status_code == 404


def test_bare_relative_paths_are_local_references_too(client, tmp_path):
    archive = build_zip(tmp_path, nodes=[dataset(content_url="data/table.csv")])
    body = post(client, archive).json()
    assert body["files"]["found"] == 1


def test_remote_and_opaque_content_urls_are_not_checked(client, tmp_path):
    nodes = [
        dataset("ark:99999/ds-https", "https://dataverse.example/api/access/datafile/1"),
        dataset("ark:99999/ds-ftp", "ftp://massive.example/x.csv"),
        dataset("ark:99999/ds-embargo", "Embargoed"),
        dataset("ark:99999/ds-abs", "/home/someone/else/x.csv"),
    ]
    body = post(client, build_zip(tmp_path, nodes=nodes, files={})).json()
    assert body["files"]["local"] == 0


def test_zip_without_wrapper_folder(client, tmp_path):
    body = post(client, build_zip(tmp_path, wrapper=None)).json()
    metadata = Path(body["path"])
    assert metadata.parent == Path(body["directory"])
    assert body["files"]["found"] == 1


def test_missing_data_files_are_reported_not_hidden(client, tmp_path):
    body = post(client, build_zip(tmp_path, files={})).json()
    assert body["files"] == {
        "local": 1, "found": 0,
        "missing": [{"@id": DATA, "contentUrl": "file:///data/table.csv"}],
        "missing_truncated": False,
    }


def test_sub_crates_in_the_archive_are_registered(client, tmp_path):
    archive = build_zip(tmp_path)
    child = "ark:99999/rocrate-child"
    with zipfile.ZipFile(archive, "a") as zf:
        write_crate(tmp_path / "child", child, nodes=[dataset("ark:99999/ds-child")])
        zf.write(tmp_path / "child" / "ro-crate-metadata.json",
                 "my-crate/child/ro-crate-metadata.json")
    body = post(client, archive).json()
    assert body["crate"] == ROOT
    assert sorted(r["crate"] for r in body["registered"]) == sorted([ROOT, child])
    assert len(client.get("/rocrate").json()["crates"]) == 2


def test_junk_members_are_skipped_not_fatal(client, tmp_path):
    archive = build_zip(tmp_path, extra_members={
        "__MACOSX/my-crate/._ro-crate-metadata.json": "resource fork",
        "my-crate/.DS_Store": "finder",
    })
    body = post(client, archive).json()
    assert sorted(body["skipped_members"]) == [
        "__MACOSX/my-crate/._ro-crate-metadata.json", "my-crate/.DS_Store"]
    assert not (Path(body["directory"]) / "__MACOSX").exists()


# --------------------------------------------------------------------------
# Re-upload
# --------------------------------------------------------------------------

def test_reuploading_a_zip_replaces_the_crate_in_place(client, tmp_path):
    first = post(client, build_zip(tmp_path, files={"data/table.csv": "old",
                                                    "data/stale.txt": "gone"})).json()
    second = post(client, build_zip(tmp_path / "again",
                                    files={"data/table.csv": "new"})).json()
    assert second["directory"] == first["directory"]
    assert (Path(second["path"]).parent / "data" / "table.csv").read_text() == "new"
    assert not (Path(second["path"]).parent / "data" / "stale.txt").exists()
    assert len(client.get("/rocrate").json()["crates"]) == 1
    assert second["registered"][0]["skipped"] is False


def test_reuploading_with_a_different_wrapper_moves_the_registration(client, tmp_path):
    first = post(client, build_zip(tmp_path)).json()
    second = post(client, build_zip(tmp_path / "again", wrapper="renamed")).json()
    assert Path(second["path"]).parts[-2] == "renamed"
    assert not Path(first["path"]).exists()
    crates = client.get("/rocrate").json()["crates"]
    assert [c["path"] for c in crates] == [second["path"]]


def test_bare_metadata_upload_makes_a_one_file_crate(client, tmp_path):
    path = write_crate(tmp_path / "bare", ROOT, nodes=[dataset()])
    body = post(client, path).json()
    assert body["kind"] == "metadata" and body["members"] == 0
    assert Path(body["path"]) == Path(body["directory"]) / "ro-crate-metadata.json"
    assert body["files"]["missing"] == [{"@id": DATA, "contentUrl": "file:///data/table.csv"}]
    assert client.get(f"/{DATA}").status_code == 200


def test_bare_metadata_reupload_keeps_the_data_files(client, tmp_path):
    first = post(client, build_zip(tmp_path)).json()
    edited = write_crate(tmp_path / "edit", ROOT,
                         nodes=[dataset(), dataset("ark:99999/ds-added", "data/table.csv")])
    second = post(client, edited).json()
    # same file replaced, wrapper folder and data untouched
    assert second["path"] == first["path"]
    assert second["files"] == {"local": 2, "found": 2, "missing": [],
                               "missing_truncated": False}
    assert client.get("/ark:99999/ds-added").status_code == 200


# --------------------------------------------------------------------------
# Rejections leave nothing behind
# --------------------------------------------------------------------------

def uploads_are_clean(tmp_path):
    root = tmp_path / "uploads"
    return not root.exists() or not [p for p in root.iterdir()]


def test_archive_without_a_crate_is_422(client, tmp_path):
    archive = tmp_path / "nocrate.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "nothing here")
    response = post(client, archive)
    assert response.status_code == 422 and "ro-crate-metadata.json" in response.json()["detail"]
    assert uploads_are_clean(tmp_path)


def test_two_crates_side_by_side_is_422(client, tmp_path):
    archive = build_zip(tmp_path, wrapper="one")
    write_crate(tmp_path / "two", "ark:99999/second")
    with zipfile.ZipFile(archive, "a") as zf:
        zf.write(tmp_path / "two" / "ro-crate-metadata.json", "two/ro-crate-metadata.json")
    response = post(client, archive)
    assert response.status_code == 422 and "side by side" in response.json()["detail"]
    assert uploads_are_clean(tmp_path)


def test_invalid_crate_in_archive_is_422(client, tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("x/ro-crate-metadata.json", '{"@context": {}, "@graph": [{"@id": "x"}]}')
    response = post(client, archive)
    assert response.status_code == 422
    assert response.json()["detail"].startswith("not a valid RO-Crate")
    assert uploads_are_clean(tmp_path)


def test_neither_zip_nor_json_is_422(client, tmp_path):
    assert post_bytes(client, b"\x00\x01 not anything", "blob.bin").status_code == 422
    assert post_bytes(client, b"{ not json").status_code == 422
    assert uploads_are_clean(tmp_path)


def test_zip_slip_is_refused(client, tmp_path):
    archive = build_zip(tmp_path, extra_members={"../escaped.txt": "no"})
    response = post(client, archive)
    assert response.status_code == 422 and "escapes" in response.json()["detail"]
    assert not (tmp_path / "escaped.txt").exists()
    assert uploads_are_clean(tmp_path)


def test_oversized_archive_is_413(client, tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "MAX_UNPACKED_BYTES", 10)
    response = post(client, build_zip(tmp_path))
    assert response.status_code == 413
    assert uploads_are_clean(tmp_path)


def test_crate_root_does_not_apply_to_uploads(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "CRATE_ROOT", str(tmp_path / "elsewhere"))
    assert post(client, build_zip(tmp_path)).status_code == 200


# --------------------------------------------------------------------------
# Delete
# --------------------------------------------------------------------------

def test_purge_removes_only_uploaded_files(client, tmp_path):
    uploaded = Path(post(client, build_zip(tmp_path)).json()["directory"])
    local = write_crate(tmp_path / "local", "ark:99999/by-path")
    client.post("/rocrate", json={"path": str(local)})

    body = client.request("DELETE", "/rocrate", params={"id": ROOT, "purge": "true"}).json()
    assert body == {"forgotten": ROOT, "purged": str(uploaded)}
    assert not uploaded.exists()

    body = client.request("DELETE", "/rocrate",
                          params={"id": "ark:99999/by-path", "purge": "true"}).json()
    assert body["purged"] is None and local.exists()


def test_delete_without_purge_keeps_the_files(client, tmp_path):
    uploaded = Path(post(client, build_zip(tmp_path)).json()["directory"])
    assert client.request("DELETE", "/rocrate", params={"id": ROOT}).json()["purged"] is None
    assert uploaded.exists()


# --------------------------------------------------------------------------
# Unit: the pieces
# --------------------------------------------------------------------------

@pytest.mark.parametrize("url, expected", [
    ("file:///data/x.csv", "data/x.csv"),
    ("file://data/x.csv", "data/x.csv"),
    ("file:///data/with%20space.csv", "data/with space.csv"),
    ("data/x.csv", "data/x.csv"),
    ("./data/x.csv", "./data/x.csv"),
    ("https://example.org/x.csv", None),
    ("ftp://example.org/x.csv", None),
    ("ark:59852/dataset-x", None),
    ("doi:10.1/xyz", None),
    ("Embargoed", None),
    ("/absolute/x.csv", None),
    ("", None),
    (None, None),
    (["file:///a.csv"], None),     # lists are unpacked by the caller
])
def test_local_reference(url, expected):
    assert upload.local_reference(url) == expected


def test_crate_dirname_is_stable_readable_and_collision_free():
    a = upload.crate_dirname("ark:59852/rocrate-foo-bar")
    assert a == upload.crate_dirname("ark:59852/rocrate-foo-bar")
    assert a.startswith("ark-59852-rocrate-foo-bar-")
    assert a != upload.crate_dirname("ark:59852/rocrate-foo_bar")
    assert "/" not in upload.crate_dirname("https://example.org/crates/1")


def test_real_fixture_crate_round_trips(client, tmp_path):
    """The LakeDB fixture, zipped as a CM4AI release would be."""
    archive = tmp_path / "lakedb.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(FIXTURES / "LakeDB" / "ro-crate-metadata.json",
                 "LakeDB/ro-crate-metadata.json")
    body = post(client, archive).json()
    assert body["crate"] == "ark:59852/rocrate-test-analysis-workflow-qt7fpvq3pq/"
    assert body["files"]["local"] == 0       # its contentUrls are all "Embargoed"
    on_disk = json.loads(Path(body["path"]).read_text())
    assert on_disk == json.loads((FIXTURES / "LakeDB" / "ro-crate-metadata.json").read_text())
