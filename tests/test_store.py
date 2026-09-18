"""The index: ingest rules, collisions, drift, and the read paths."""

import json
import sqlite3
from pathlib import Path

import pytest

from conftest import CRATE_NAMES, FIXTURES, write_crate
from fairscape_lite import db
from fairscape_lite.models import Crate, Edge, Entity


# --- vocabulary -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("https://w3id.org/EVI#Dataset", "Dataset"),
    (["prov:Entity", "https://w3id.org/EVI#Dataset"], "Dataset"),
    (["prov:Activity", "https://w3id.org/EVI#Computation"], "Computation"),
    (["Dataset", "https://w3id.org/EVI#ROCrate"], "ROCrate"),
    (["https://w3id.org/EVI#Dataset", "https://w3id.org/EVI:ROCrate"], "ROCrate"),
    ("evi:schema", "Schema"),
    ("EVI:Schema", "Schema"),
    ("CreativeWork", "CreativeWork"),
    ([], "Thing"),
])
def test_normalize_type(raw, expected):
    assert db.normalize_type(raw) == expected


@pytest.mark.parametrize("identifier,expected", [
    ("ark:59852/rocrate-foo-bar", "59852/rocratefoobar"),
    ("ark:59852/rocrate-foo-bar/", "59852/rocratefoobar"),
    ("ark:/59852/foo", "59852/foo"),
    ("https://example.org/thing", None),
    ("ro-crate-metadata.json", None),
])
def test_ark_key(identifier, expected):
    assert db.ark_key(identifier) == expected


@pytest.mark.parametrize("field,expected", [
    ("hasPart", "hasPart"),
    ("prov:wasGeneratedBy", "generatedBy"),       # collapses onto the EVI twin
    ("prov:wasDerivedFrom", "derivedFrom"),       # sole derivation link in c2m2
    ("evi:Schema", "schema"),
    ("EVI:Schema", "schema"),                     # case variant, same predicate
    ("https://w3id.org/EVI#outputs", "outputs"),
    ("usedTreatment", "usedTreatment"),           # long tail, via the used* rule
    ("cfde:describedByC2M2Table", "describedByC2M2Table"),
    ("author", None),                             # not a provenance link
    ("associatedDisease", None),
])
def test_edge_predicate(field, expected):
    assert db.edge_predicate(field) == expected


# --- ingest ---------------------------------------------------------------

def test_schema_is_idempotent(tmp_path):
    path = str(tmp_path / "x.db")
    db.connect(path).close()
    db.connect(path).close()          # would raise if DDL were not IF NOT EXISTS


def test_ingest_counts_every_node_but_the_descriptor(con):
    stats = db.ingest(con, FIXTURES / "images")
    assert stats.nodes == 3978
    assert stats.entities_inserted == 3977
    assert con.execute(
        "SELECT COUNT(*) FROM entity WHERE id = 'ro-crate-metadata.json'"
    ).fetchone()[0] == 0


def test_descriptor_would_otherwise_collide_across_crates(store):
    """Every crate on earth names its descriptor the same thing."""
    for name in CRATE_NAMES:
        data = json.loads((FIXTURES / name / "ro-crate-metadata.json").read_text())
        assert any(n.get("@id") == "ro-crate-metadata.json" for n in data["@graph"])


def test_reingest_unchanged_file_is_skipped(store):
    stats = db.ingest(store, FIXTURES / "LakeDB")
    assert stats.skipped is True
    assert stats.entities_inserted == 0


def test_forced_reingest_refreshes_rather_than_reinserts(store):
    before = store.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
    stats = db.ingest(store, FIXTURES / "LakeDB", force=True)
    assert (stats.entities_inserted, stats.entities_refreshed) == (0, 5)
    assert store.execute("SELECT COUNT(*) FROM entity").fetchone()[0] == before


def test_ingest_tree_finds_every_crate(con):
    results = db.ingest_tree(con, FIXTURES)
    assert len(results) == len(CRATE_NAMES)
    assert len(db.list_crates(con)) == len(CRATE_NAMES)


def test_ingest_rolls_back_on_failure(con, tmp_path, monkeypatch):
    path = write_crate(tmp_path / "c", "ark:99999/rollback")
    monkeypatch.setattr(db, "_drop_vanished",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        db.ingest(con, path)
    assert db.list_crates(con) == []
    assert con.execute("SELECT COUNT(*) FROM entity").fetchone()[0] == 0


# --- the collision rule ---------------------------------------------------

def test_own_root_wins_over_a_parents_rich_copy(con, tmp_path):
    """A parent embeds a full copy of its child's root, not a thin stub."""
    child_root = "ark:99999/child"
    child = write_crate(tmp_path / "child", child_root)
    parent = write_crate(
        tmp_path / "parent", "ark:99999/parent",
        nodes=[{"@id": child_root, "@type": ["Dataset", "https://w3id.org/EVI#ROCrate"],
                "name": "stale copy held by the parent", "description": "outdated"}],
    )
    db.ingest(con, parent)
    db.ingest(con, child)
    entity = db.resolve(con, child_root)
    assert entity.source_crate == child_root      # the child owns its own root
    assert entity.name == "synthetic crate"       # its own file, not the copy


def test_both_ingest_orders_converge(con, tmp_path):
    child_root = "ark:99999/child"
    child = write_crate(tmp_path / "child", child_root)
    parent = write_crate(
        tmp_path / "parent", "ark:99999/parent",
        nodes=[{"@id": child_root, "@type": ["Dataset", "https://w3id.org/EVI#ROCrate"],
                "name": "stale copy", "description": "outdated"}],
    )
    def rows(order):
        connection = db.connect(":memory:")
        for path in order:
            db.ingest(connection, path)
        return [tuple(r) for r in connection.execute(
            "SELECT id, name, source_crate FROM entity ORDER BY id")]

    assert rows([parent, child]) == rows([child, parent])


def test_first_wins_for_everything_that_is_not_a_root(con, tmp_path):
    shared = {"@id": "ark:99999/shared", "@type": "https://w3id.org/EVI#Dataset",
              "name": "from A"}
    a = write_crate(tmp_path / "a", "ark:99999/a", nodes=[shared])
    b = write_crate(tmp_path / "b", "ark:99999/b",
                    nodes=[{**shared, "name": "from B"}])
    db.ingest(con, a)
    stats = db.ingest(con, b)
    assert stats.entities_kept == 1
    assert db.resolve(con, "ark:99999/shared").name == "from A"


# --- drift ----------------------------------------------------------------

def test_changing_a_root_id_does_not_leave_a_ghost_crate(con, tmp_path):
    """UNIQUE(path): regenerating a crate must not leave two rows on one file."""
    directory = tmp_path / "c"
    write_crate(directory, "ark:99999/first")
    db.ingest(con, directory)
    write_crate(directory, "ark:99999/second")
    db.ingest(con, directory, force=True)

    crates = db.list_crates(con)
    assert [c.id for c in crates] == ["ark:99999/second"]
    assert db.resolve(con, "ark:99999/first") is None


def test_entities_removed_from_a_crate_are_dropped(con, tmp_path):
    directory = tmp_path / "c"
    node = {"@id": "ark:99999/gone", "@type": "https://w3id.org/EVI#Dataset",
            "name": "temporary"}
    write_crate(directory, "ark:99999/root", nodes=[node])
    db.ingest(con, directory)
    assert db.resolve(con, "ark:99999/gone") is not None

    write_crate(directory, "ark:99999/root")
    stats = db.ingest(con, directory, force=True)
    assert stats.entities_dropped == 1
    assert db.resolve(con, "ark:99999/gone") is None


def test_stale_lists_crates_whose_file_moved(store, tmp_path):
    assert db.stale(store) == []
    path = write_crate(tmp_path / "c", "ark:99999/movable")
    db.ingest(store, path)
    path.unlink()
    assert [c.id for c in db.stale(store)] == ["ark:99999/movable"]


def test_metadata_raises_when_the_file_is_gone(con, tmp_path):
    path = write_crate(tmp_path / "c", "ark:99999/vanishing")
    db.ingest(con, path)
    entity = db.resolve(con, "ark:99999/vanishing")
    path.unlink()
    with pytest.raises(db.MissingCrateFile):
        db.metadata(con, entity)


def test_metadata_returns_none_when_the_node_is_gone(con, tmp_path):
    directory = tmp_path / "c"
    node = {"@id": "ark:99999/dropped", "@type": "https://w3id.org/EVI#Dataset"}
    write_crate(directory, "ark:99999/root", nodes=[node])
    db.ingest(con, directory)
    entity = db.resolve(con, "ark:99999/dropped")
    write_crate(directory, "ark:99999/root")         # rewrite without the node
    assert db.metadata(con, entity) is None


def test_forget_removes_entities_and_edges(store):
    crate_id = "ark:59852/rocrate-untreated-if-data-release-blue"
    assert db.forget(store, crate_id) is True
    assert db.resolve(store, crate_id) is None
    assert store.execute(
        "SELECT COUNT(*) FROM entity WHERE source_crate = ?", (crate_id,)
    ).fetchone()[0] == 0


def test_reingest_all_reads_every_registered_crate(store):
    results = db.reingest_all(store)
    assert len(results) == len(CRATE_NAMES)
    assert all(not r.skipped for r in results)


# --- reads ----------------------------------------------------------------

def test_resolve_is_dash_insensitive(store):
    exact = "ark:59852/rocrate-untreated-if-data-release-blue"
    assert db.resolve(store, exact).id == exact
    assert db.resolve(store, "ark:59852/rocrateuntreatedifdatareleaseblue").id == exact


def test_resolve_handles_non_ark_ids(con, tmp_path):
    root = "https://fairscape.net/api/ark:59853/url-rooted"
    db.ingest(con, write_crate(tmp_path / "c", root))
    entity = db.resolve(con, root)
    assert entity.id == root and entity.ark_key is None


def test_metadata_reads_the_node_back_from_disk(store):
    entity = db.resolve(store, "ark:59852/rocrate-test-analysis-workflow-qt7fpvq3pq")
    node = db.metadata(store, entity)
    assert node["@id"] == entity.id
    assert "hasPart" in node          # a field the index never stored


def test_search_matches_and_survives_punctuation(store):
    assert any("Analysis" in (r.name or "") for r in db.search(store, "analysis"))
    assert db.search(store, 'ark:59852/x (unbalanced') == []      # no raise


def test_list_entities_scopes_to_one_crate(store):
    crate_id = "ark:59852/rocrate-untreated-if-data-release-blue"
    found = db.list_entities(store, crate=crate_id, limit=500)
    assert found and all(e.source_crate == crate_id for e in found)


def test_list_entities_filters_by_type(store):
    found = db.list_entities(store, entity_type="Software")
    assert [e.type for e in found] == ["Software"]


def test_neighbors_reports_both_directions(store):
    crate_id = "ark:59852/rocrate-test-analysis-workflow-qt7fpvq3pq/"
    links = db.neighbors(store, crate_id)
    assert links["outgoing"] and all("@id" in e for e in links["outgoing"])


# --- the models mirror the schema ----------------------------------------

def test_generated_sql_matches_the_table(store):
    columns = {r[1] for r in store.execute("PRAGMA table_info(entity)")}
    assert columns == set(Entity.model_fields)
    assert {r[1] for r in store.execute("PRAGMA table_info(crate)")} == set(Crate.model_fields)
    assert {r[1] for r in store.execute("PRAGMA table_info(edge)")} == set(Edge.model_fields)


def test_upsert_does_not_cascade_delete_entities(store):
    """INSERT OR REPLACE would have; the upsert must not."""
    before = store.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
    db.ingest(store, FIXTURES / "images", force=True)
    assert store.execute("SELECT COUNT(*) FROM entity").fetchone()[0] == before


def test_edges_may_dangle(con, tmp_path):
    """An edge to an unregistered crate is information, not an error."""
    node = {"@id": "ark:99999/here", "@type": "https://w3id.org/EVI#Dataset",
            "generatedBy": {"@id": "ark:99999/elsewhere"}}
    db.ingest(con, write_crate(tmp_path / "c", "ark:99999/root", nodes=[node]))
    assert con.execute(
        "SELECT COUNT(*) FROM edge WHERE object = 'ark:99999/elsewhere'"
    ).fetchone()[0] == 1
    assert db.resolve(con, "ark:99999/elsewhere") is None


def test_ingest_tree_survives_a_malformed_crate(con, tmp_path):
    """One bad file must not abort the walk or lose its neighbours."""
    write_crate(tmp_path / "a-good", "ark:99999/good-a")
    (tmp_path / "b-bad").mkdir()
    (tmp_path / "b-bad" / "ro-crate-metadata.json").write_text("{ not json")
    (tmp_path / "c-notacrate").mkdir()
    (tmp_path / "c-notacrate" / "ro-crate-metadata.json").write_text('{"@graph": []}')
    write_crate(tmp_path / "d-good", "ark:99999/good-d")

    results = db.ingest_tree(con, tmp_path)

    assert [r.crate for r in results if not r.error] == ["ark:99999/good-a", "ark:99999/good-d"]
    errors = {Path(r.path).parent.name: r.error for r in results if r.error}
    assert set(errors) == {"b-bad", "c-notacrate"}
    assert "not valid JSON" in errors["b-bad"]
    assert "no RO-Crate root" in errors["c-notacrate"]
    assert {c.id for c in db.list_crates(con)} == {"ark:99999/good-a", "ark:99999/good-d"}


def test_ingest_tree_applies_the_validator(con, tmp_path):
    write_crate(tmp_path / "x", "ark:99999/x")

    def reject(data):
        raise ValueError("rejected by validator")

    results = db.ingest_tree(con, tmp_path, validate=reject)
    assert [r.error for r in results] == ["rejected by validator"]
    assert db.list_crates(con) == []
