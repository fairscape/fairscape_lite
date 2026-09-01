import json
from pathlib import Path

import pytest

from fairscape_lite import db

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT.parent / "fairscape_models" / "tests" / "test_rocrates"
CRATE_NAMES = ("release", "LakeDB", "images")


@pytest.fixture
def con(tmp_path):
    """An empty index on disk (not :memory:, so paths and stat work)."""
    connection = db.connect(str(tmp_path / "test.db"))
    yield connection
    connection.close()


@pytest.fixture
def store(con):
    """The three fixture crates, ingested."""
    for name in CRATE_NAMES:
        db.ingest(con, FIXTURES / name)
    return con


def write_crate(directory: Path, root_id: str, nodes=(), context=None) -> Path:
    """A minimal but valid crate on disk, for the cases fixtures don't cover."""
    directory.mkdir(parents=True, exist_ok=True)
    graph = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2-DRAFT"},
            "about": {"@id": root_id},
        },
        {
            "@id": root_id,
            "@type": ["Dataset", "https://w3id.org/EVI#ROCrate"],
            "name": "synthetic crate",
            "description": "written by the test suite",
            "keywords": ["test"],
            "version": "1.0",
            "license": "https://opensource.org/licenses/MIT",
            "author": "Test Suite",
            "hasPart": [{"@id": n["@id"]} for n in nodes],
        },
        *nodes,
    ]
    path = directory / "ro-crate-metadata.json"
    path.write_text(json.dumps(
        {"@context": context or {"@vocab": "https://schema.org/"}, "@graph": graph}
    ))
    return path
