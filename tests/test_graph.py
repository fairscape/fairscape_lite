"""Evidence graphs: traversal, projection and condensation."""

import json

import pytest
from pydantic import ValidationError

from conftest import FIXTURES, write_crate
from fairscape_lite import db, graph
from fairscape_lite.models import validate_crate

# Every field a projected node can point along.
REF_FIELDS = ("generatedBy", "usedDataset", "usedSoftware", "usedSample",
              "usedInstrument", "usedMLModel", "hasOutputs",
              "evi:representativeDataset")


def pointed_at(node):
    """The ids one projected node points at."""
    out = set()
    for field in REF_FIELDS:
        value = node.get(field)
        out.update(graph.refs(value))
    out.update(m for m in node.get("evi:memberIds") or [] if isinstance(m, str))
    return out


# --- identifiers ----------------------------------------------------------

@pytest.mark.parametrize("node_id,expected", [
    ("ark:59852/foo", "ark:59852/evidence-graph-foo"),
    ("ark:/59852/foo", "ark:59852/evidence-graph-foo"),
    ("https://example.org/x", "https://example.org/x-evidence-graph"),
])
def test_evidence_graph_id(node_id, expected):
    assert graph.evidence_graph_id(node_id) == expected


# --- closure --------------------------------------------------------------

def test_every_reference_in_a_graph_is_projected(store):
    """Nothing a node points at, nor any output, is missing from @graph."""
    targets = [r["id"] for r in store.execute(
        "SELECT id FROM entity WHERE id IN (SELECT subject FROM edge) "
        "ORDER BY pk LIMIT 40"
    )]
    assert len(targets) >= 20, "fixtures should give us plenty to check"

    for node_id in targets + ["ark:59852/cm4ai-june-2025-release"]:
        for threshold in (None, graph.CONDENSE_THRESHOLD):
            built = graph.build(store, node_id, threshold=threshold)
            nodes = built["@graph"]
            assert node_id in nodes, node_id
            assert {r["@id"] for r in built["outputs"]} <= set(nodes), node_id
            for guid, node in nodes.items():
                assert pointed_at(node) <= set(nodes), (node_id, guid)


def test_a_rocrate_root_outputs_itself_and_what_it_lists(store):
    root = "ark:59852/cm4ai-june-2025-release"
    built = graph.build(store, root, threshold=None)
    listed = built["@graph"][root]["hasOutputs"]
    assert listed
    assert built["outputs"] == [{"@id": r["@id"]} for r in listed] + [{"@id": root}]


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


def _root_listing(tmp_path, field):
    """A crate whose root lists one generated dataset under `field` only."""
    nodes = [
        {"@id": "ark:99999/out", "@type": "https://w3id.org/EVI#Dataset",
         "name": "output", "generatedBy": {"@id": "ark:99999/comp"}},
        {"@id": "ark:99999/comp", "@type": "https://w3id.org/EVI#Computation",
         "name": "run"},
    ]
    path = write_crate(tmp_path / "c", "ark:99999/root", nodes=nodes)
    data = json.loads(path.read_text())
    root = data["@graph"][1]
    listed = root.pop("hasPart")[:1]
    root[field] = listed
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize("field", ["EVI:Outputs", "EVI:outputs", "hasPart"])
def test_a_crate_root_expands_through_any_listing_field(con, tmp_path, field):
    db.ingest(con, _root_listing(tmp_path, field))
    built = graph.build(con, "ark:99999/root", threshold=None)
    assert {"ark:99999/out", "ark:99999/comp"} <= set(built["@graph"])
    assert {"@id": "ark:99999/out"} in built["outputs"]


def _release_with_sub_crate(tmp_path, count):
    """A release crate whose `hasPart` names a sub-crate with `count` outputs."""
    sub = _crate_with_siblings(tmp_path, count)
    release = write_crate(tmp_path / "release", "ark:99999/release")
    data = json.loads(release.read_text())
    data["@graph"][1]["hasPart"] = [{"@id": "ark:99999/root"}]
    data["@graph"].append({
        "@id": "ark:99999/root",
        "@type": ["Dataset", "https://w3id.org/EVI#ROCrate"],
        "name": "sub-crate",
    })
    release.write_text(json.dumps(data))
    return release, sub


def test_a_release_expands_into_its_sub_crates(con, tmp_path):
    release, sub = _release_with_sub_crate(tmp_path, 3)
    db.ingest(con, release)
    db.ingest(con, sub)
    built = graph.build(con, "ark:99999/release", threshold=None)
    nodes = built["@graph"]
    assert nodes["ark:99999/release"]["hasOutputs"] == [{"@id": "ark:99999/root"}]
    assert len(nodes["ark:99999/root"]["hasOutputs"]) == 3
    assert {"ark:99999/img0", "ark:99999/img2", "ark:99999/comp"} <= set(nodes)


def test_a_sub_crates_outputs_condense(con, tmp_path):
    release, sub = _release_with_sub_crate(tmp_path, 8)
    db.ingest(con, release)
    db.ingest(con, sub)
    built = graph.build(con, "ark:99999/release", threshold=5)
    sub_outputs = built["@graph"]["ark:99999/root"]["hasOutputs"]
    assert len(sub_outputs) == 1
    assert "DatasetGroup" in str(built["@graph"][sub_outputs[0]["@id"]]["@type"])


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


def test_every_group_member_is_listed_and_projected(con, tmp_path):
    db.ingest(con, _crate_with_siblings(tmp_path, 8))
    built = graph.build(con, "ark:99999/root", threshold=5)
    group = next(n for n in built["@graph"].values()
                 if "DatasetGroup" in str(n.get("@type")))
    assert sorted(group["evi:memberIds"]) == sorted(
        f"ark:99999/img{i}" for i in range(8))
    assert set(group["evi:memberIds"]) <= set(built["@graph"])


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
