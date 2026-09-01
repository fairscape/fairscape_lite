"""Ingest the whole corpus and time the read paths.

The numbers in SCHEMA.md come from here. Run it after any change to
ingest, and update SCHEMA.md if they move.

    python3 bench.py [root] [--db PATH]
"""

import sys
import time
from pathlib import Path

from fairscape_lite import db, graph


def main(root: str, db_path: str) -> None:
    Path(db_path).unlink(missing_ok=True)
    con = db.connect(db_path)

    started = time.perf_counter()
    results = db.ingest_tree(con, root)
    elapsed = time.perf_counter() - started

    nodes = sum(r.nodes for r in results)
    entities = con.execute("SELECT COUNT(*) FROM entity").fetchone()[0]
    edges = con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
    size = Path(db_path).stat().st_size

    print(f"ingest        {len(results)} crates, {nodes:,} nodes "
          f"in {elapsed:.1f}s ({nodes/elapsed:,.0f} nodes/s)")
    print(f"index         {entities:,} entities, {edges:,} edges, "
          f"{size/1e6:.0f} MB on disk ({size/nodes:.0f} bytes/node)")
    print(f"re-ingest     {sum(1 for r in db.reingest_all(con, force=False) if r.skipped)}"
          f"/{len(results)} skipped as unchanged")

    slowest = max(results, key=lambda r: r.nodes)
    print(f"largest crate {slowest.nodes:,} nodes  {Path(slowest.path).parent.name}")

    sample = [r["id"] for r in con.execute(
        "SELECT id FROM entity ORDER BY RANDOM() LIMIT 500")]
    started = time.perf_counter()
    for guid in sample:
        db.resolve(con, guid)
    per = (time.perf_counter() - started) / len(sample) * 1e6
    print(f"resolve       {per:.0f} us/lookup (n={len(sample)})")

    started = time.perf_counter()
    for _ in range(20):
        db.search(con, "protein")
    print(f"search        {(time.perf_counter() - started) / 20 * 1000:.1f} ms/query")

    roots = [r["id"] for r in con.execute(
        "SELECT id FROM crate ORDER BY node_count DESC LIMIT 3")]
    for root_id in roots:
        started = time.perf_counter()
        built = graph.build(con, root_id)
        elapsed = time.perf_counter() - started
        stats = built["condensation_stats"]
        print(f"evidencegraph {len(built['@graph']):>6,} nodes in {elapsed:5.2f}s  "
              f"(collapsed {stats.get('datasets_collapsed', 0):,})  {root_id[-46:]}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = args[0] if args else ".."
    db_path = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else "/tmp/bench.db"
    main(root, db_path)
