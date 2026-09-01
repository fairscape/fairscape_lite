"""Evidence graphs: parity with fairscape_graph_tools, plus condensation."""

import json

import pytest
from fairscape_graph_tools.evidence_graph_builder import EvidenceGraphBuilder
from pydantic import ValidationError

from conftest import FIXTURES, write_crate
from fairscape_lite import db, graph
from fairscape_lite.models import validate_crate

NO_CONDENSE = 10 ** 9          # a threshold nothing can exceed


class CaptureSink:
    """A ResultSink that keeps the graph instead of persisting it."""

    def persist_evidence_graph(self, evidence_graph, source_node_id):
        self.evidence_graph = evidence_graph
        return evidence_graph.guid

    def persist_condensed(self, *args, **kwargs):
        raise NotImplementedError

    def persist_aeg(self, *args, **kwargs):
        raise NotImplementedError


def reference_graph(con, node_id):
    """What the real builder produces, over the same store."""
    sink = CaptureSink()
    EvidenceGraphBuilder(
        graph.CrateReader(con), sink, condense_threshold=NO_CONDENSE
    ).build(node_id, owner_email="test@example.org")
    return sink.evidence_graph


# --- identifiers ----------------------------------------------------------

@pytest.mark.parametrize("node_id,expected", [
    ("ark:59852/foo", "ark:59852/evidence-graph-foo"),
    ("ark:/59852/foo", "ark:59852/evidence-graph-foo"),
    ("https://example.org/x", "https://example.org/x-evidence-graph"),
])
def test_evidence_graph_id(node_id, expected):
    assert graph.evidence_graph_id(node_id) == expected


# --- parity ---------------------------------------------------------------

def test_parity_with_the_real_builder_across_the_store(store):
    """Same BFS, same projection, same output -- condensation off both sides.

    Condensation is deliberately *not* compared: the lite condenser groups
    look-alike siblings inside one reference list, where the real one
    derives provenance signatures over whole subgraphs. The traversal
    underneath has to agree exactly, and this is what proves it does.
    """
    targets = [r["id"] for r in store.execute(
        "SELECT id FROM entity WHERE id IN (SELECT subject FROM edge) "
        "ORDER BY pk LIMIT 40"
    )]
    assert len(targets) >= 20, "fixtures should give us plenty to compare"

    for node_id in targets:
        mine = graph.build(store, node_id, threshold=None)
        theirs = reference_graph(store, node_id)
        assert mine["@graph"] == (theirs.graph or {}), node_id
        assert mine["outputs"] == (theirs.outputs or []), node_id


def test_parity_on_a_rocrate_root(store):
    root = "ark:59852/cm4ai-june-2025-release"
    mine = graph.build(store, root, threshold=None)
    theirs = reference_graph(store, root)
    assert mine["@graph"] == theirs.graph
    assert mine["outputs"] == theirs.outputs


# --- traversal ------------------------------------------------------------

def test_collect_walks_back_through_provenance(store):
    start = "ark:59852/dataset-analysis-results-wglai2pfrni"
    cache = graph.collect(graph.CrateReader(store), start)
    assert start in cache
    assert any("Computation" in str(n.get("@type")) for n in cache.values())
    assert any("Software" in str(n.get("@type")) for n in cache.values())


def test_unresolvable_references_become_error_stubs(con, tmp_path):
    node = {"@id": "ark:99999/here", "@type": "https://w3id.org/EVI#Dataset",
            "generatedBy": {"@id": "ark:99999/missing"}}
    db.ingest(con, write_crate(tmp_path / "c", "ark:99999/root", nodes=[node]))
    built = graph.build(con, "ark:99999/here")
    assert built["@graph"]["ark:99999/missing"] == {
        "@id": "ark:99999/missing", "error": "not found"}


def test_build_returns_none_for_an_unknown_id(store):
    assert graph.build(store, "ark:59852/never-heard-of-it") is None


def test_projection_survives_a_provenance_cycle(con, tmp_path):
    """A claims-before-expanding projection cannot loop; recursion would."""
    nodes = [
        {"@id": "ark:99999/a", "@type": "https://w3id.org/EVI#Dataset",
         "generatedBy": {"@id": "ark:99999/comp"}},
        {"@id": "ark:99999/comp", "@type": "https://w3id.org/EVI#Computation",
         "usedDataset": [{"@id": "ark:99999/a"}]},
    ]
    db.ingest(con, write_crate(tmp_path / "c", "ark:99999/root", nodes=nodes))
    built = graph.build(con, "ark:99999/a")
    assert set(built["@graph"]) == {"ark:99999/a", "ark:99999/comp"}


# --- condensation ---------------------------------------------------------

def _crate_with_siblings(tmp_path, count):
    members = [
        {"@id": f"ark:99999/img{i}", "@type": "https://w3id.org/EVI#Dataset",
         "name": f"image {i}", "format": "image/jpeg",
         "generatedBy": {"@id": "ark:99999/comp"}}
        for i in range(count)
    ]
    comp = {"@id": "ark:99999/comp", "@type": "https://w3id.org/EVI#Computation",
            "name": "imaging run"}
    path = write_crate(tmp_path / "c", "ark:99999/root", nodes=[comp, *members])
    data = json.loads(path.read_text())
    for node in data["@graph"]:
        if node["@id"] == "ark:99999/root":
            node["https://w3id.org/EVI#outputs"] = [
                {"@id": m["@id"]} for m in members]
    path.write_text(json.dumps(data))
    return path


def test_siblings_above_the_threshold_collapse(con, tmp_path):
    db.ingest(con, _crate_with_siblings(tmp_path, 8))
    built = graph.build(con, "ark:99999/root", threshold=5)
    groups = [n for n in built["@graph"].values()
              if "DatasetGroup" in str(n.get("@type"))]
    assert len(groups) == 1
    assert groups[0]["evi:memberCount"] == 8
    assert groups[0]["evi:commonFormat"] == "image/jpeg"
    assert built["condensation_stats"]["datasets_collapsed"] == 8


def test_the_representative_is_still_reachable(con, tmp_path):
    db.ingest(con, _crate_with_siblings(tmp_path, 8))
    built = graph.build(con, "ark:99999/root", threshold=5)
    group = next(n for n in built["@graph"].values()
                 if "DatasetGroup" in str(n.get("@type")))
    assert group["evi:representativeDataset"]["@id"] in built["@graph"]


def test_siblings_below_the_threshold_are_left_alone(con, tmp_path):
    db.ingest(con, _crate_with_siblings(tmp_path, 4))
    built = graph.build(con, "ark:99999/root", threshold=5)
    assert built["condensation_stats"]["condensed"] is False
    assert all("DatasetGroup" not in str(n.get("@type"))
               for n in built["@graph"].values())


def test_condensation_can_be_disabled(con, tmp_path):
    db.ingest(con, _crate_with_siblings(tmp_path, 8))
    built = graph.build(con, "ark:99999/root", threshold=None)
    assert len(built["@graph"]) == 10          # root + comp + 8 images


def test_one_crate_file_is_parsed_once_per_build(store, monkeypatch):
    parses = []
    original = db.read_crate
    monkeypatch.setattr(db, "read_crate", lambda p: (parses.append(str(p)), original(p))[1])
    graph.build(store, "ark:59852/rocrate-untreated-if-data-release-blue")
    assert len(parses) == len(set(parses))


# --- validation -----------------------------------------------------------

def test_validate_accepts_the_fixtures_without_mutating_them():
    for name in ("release", "LakeDB", "images"):
        raw = json.loads((FIXTURES / name / "ro-crate-metadata.json").read_text())
        before = json.dumps(raw, sort_keys=True)
        validate_crate(raw)
        assert json.dumps(raw, sort_keys=True) == before


def test_validate_rejects_garbage():
    with pytest.raises(ValidationError):
        validate_crate({"not": "a crate"})
