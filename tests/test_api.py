"""The HTTP surface, end to end against a real index."""

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, write_crate
from fairscape_lite import app as app_module
from fairscape_lite import db

LAKEDB = "ark:59852/rocrate-test-analysis-workflow-qt7fpvq3pq/"
DATASET = "ark:59852/dataset-analysis-results-wglai2pfrni"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setattr(app_module, "CRATE_ROOT", None)
    with TestClient(app_module.app) as test_client:
        test_client.post("/rocrate", json={"path": str(FIXTURES)})
        yield test_client


def test_register_a_tree_then_list(client):
    assert len(client.get("/rocrate").json()["crates"]) == 3


def test_register_reports_a_missing_path_as_404(client):
    assert client.post("/rocrate", json={"path": "/definitely/not/here"}).status_code == 404


def test_register_reports_malformed_json_as_422(client, tmp_path):
    bad = tmp_path / "ro-crate-metadata.json"
    bad.write_text("{ not json")
    assert client.post("/rocrate", json={"path": str(bad)}).status_code == 422


def test_register_rejects_valid_json_that_is_not_a_crate(client, tmp_path):
    bad = tmp_path / "ro-crate-metadata.json"
    bad.write_text('{"@context": {}, "@graph": [{"@id": "x"}]}')
    assert client.post("/rocrate", json={"path": str(bad)}).status_code == 422


def test_resolve_an_ark(client):
    body = client.get(f"/{LAKEDB}").json()
    assert body["@id"] == LAKEDB
    assert body["sourceCrate"] == LAKEDB
    assert "hasPart" in body["metadata"]


def test_resolve_ignores_dashes(client):
    assert client.get("/ark:59852/rocratetestanalysisworkflowqt7fpvq3pq").json()["@id"] == LAKEDB


def test_resolve_unknown_is_404(client):
    assert client.get("/ark:59852/no-such-thing").status_code == 404


def test_identifier_endpoint_handles_any_id_form(client):
    assert client.get("/identifier", params={"id": DATASET}).json()["@id"] == DATASET


def test_a_missing_crate_file_is_409(client, tmp_path):
    path = write_crate(tmp_path / "gone", "ark:99999/temp")
    client.post("/rocrate", json={"path": str(path)})
    path.unlink()
    assert client.get("/ark:99999/temp").status_code == 409


def test_entity_listing_filters_and_caps(client):
    assert client.get("/entity", params={"type": "Software"}).json()["entities"]
    assert client.get("/entity", params={"limit": 10 ** 6}).status_code == 422


def test_entity_listing_scopes_to_a_crate(client):
    found = client.get("/entity", params={"crate": LAKEDB, "limit": 500}).json()["entities"]
    assert found and all(e["source_crate"] == LAKEDB for e in found)


def test_search(client):
    assert client.get("/search", params={"q": "analysis"}).json()["results"]


def test_crate_metadata_is_the_file_verbatim(client):
    body = client.get("/rocrate/metadata", params={"id": LAKEDB}).json()
    assert set(body) == {"@context", "@graph"}


def test_evidence_graph_by_ark(client):
    body = client.get(f"/evidencegraph/{DATASET}").json()
    assert body["@type"] == "evi:EvidenceGraph"
    assert body["@id"].startswith("ark:59852/evidence-graph-")
    assert len(body["metadata"]["@graph"]) == 4


def test_evidence_graph_condense_flag(client):
    off = client.get("/evidencegraph", params={"id": DATASET, "condense": 0}).json()
    assert off["metadata"]["condensation_stats"]["condensed"] is False


def test_stale_and_reingest(client):
    assert client.get("/rocrate/stale").json() == {"stale": []}
    assert len(client.post("/rocrate/reingest").json()["reingested"]) == 3


def test_unregister(client):
    assert client.request("DELETE", "/rocrate", params={"id": LAKEDB}).status_code == 200
    assert client.get(f"/{LAKEDB}").status_code == 404
    assert len(client.get("/rocrate").json()["crates"]) == 2


def test_crate_root_confines_registration(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CRATE_ROOT", str(tmp_path))
    outside = client.post("/rocrate", json={"path": str(FIXTURES)})
    assert outside.status_code == 403
    inside = write_crate(tmp_path / "ok", "ark:99999/inside")
    assert client.post("/rocrate", json={"path": str(inside)}).status_code == 200
