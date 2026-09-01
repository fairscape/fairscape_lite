"""Evidence graphs, built at read time.

On the old server this was a Celery task: a worker walked MongoDB, wrote
the result back as its own identifier, and the API polled for it. Here it
is a function. A department-scale corpus rebuilds one in milliseconds, and
a graph that is computed on demand can never be stale.

The output is the same shape the old server returned -- `outputs` plus a
`@graph` keyed by @id -- because the web client destructures it. Parity
with `fairscape_graph_tools.EvidenceGraphBuilder` is enforced by a test.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from . import db

CONDENSE_THRESHOLD = 5

# Followed backward from a Dataset-ish node, and forward from an activity.
GENERATED_BY = "generatedBy"
USED_FIELDS = ("usedDataset", "usedSoftware", "usedSample", "usedInstrument", "usedMLModel")

_ARK = re.compile(r"^ark:/?(\d+)/(.*)$")


def evidence_graph_id(node_id: str) -> str:
    """`ark:NAAN/postfix` -> `ark:NAAN/evidence-graph-postfix`."""
    match = _ARK.match(node_id)
    if match:
        return f"ark:{match.group(1)}/evidence-graph-{match.group(2)}"
    return f"{node_id}-evidence-graph"


# --------------------------------------------------------------------------
# Reading nodes out of crate files
# --------------------------------------------------------------------------

class CrateReader:
    """Resolves @ids to their JSON-LD nodes.

    Each contributing crate file is parsed at most once per build and its
    nodes indexed by @id. That is the whole reason a build is fast: a
    graph spanning three crates costs three parses no matter how many
    nodes it touches. The flip side is memory -- a build that reaches into
    the 33 MB images crate holds its parse until the reader is dropped, so
    readers are per-request and never cached between them.
    """

    def __init__(self, con):
        self.con = con
        self._by_path: Dict[str, Dict[str, dict]] = {}

    def _index(self, path: str) -> Dict[str, dict]:
        if path not in self._by_path:
            data = db.read_crate(path)
            self._by_path[path] = {
                node["@id"]: node
                for node in data.get("@graph") or []
                if isinstance(node, dict) and isinstance(node.get("@id"), str)
            }
        return self._by_path[path]

    def find_many(self, ids: Iterable[str]) -> Dict[str, dict]:
        found = {}
        for guid in ids:
            entity = db.resolve(self.con, guid)
            if entity is None:
                continue
            path = db.crate_path(self.con, entity.source_crate)
            if path is None:
                continue
            try:
                node = self._index(path).get(entity.id)
            except db.MissingCrateFile:
                continue
            if node is not None:
                found[guid] = node
        return found

    # `GraphSource` protocol conformance, so the parity test can hand this
    # same reader to the real EvidenceGraphBuilder.
    def find_entity(self, ark_id: str) -> Optional[dict]:
        return self.find_many([ark_id]).get(ark_id)

    def find_dataset_stats(self, ark_ids: Iterable[str]) -> Dict[str, dict]:
        return {}          # no statistics service in the lite server

    def build_full_graph(self, rocrate_id: str) -> List[dict]:
        return list(collect(self, rocrate_id).values())


# --------------------------------------------------------------------------
# Vocabulary helpers -- deliberately mirror fairscape_graph_tools so the
# two implementations agree on what a node "is".
# --------------------------------------------------------------------------

def is_rocrate(node_type: Any) -> bool:
    if isinstance(node_type, list):
        return any("ROCrate" in str(t) for t in node_type)
    return "ROCrate" in node_type if isinstance(node_type, str) else False


def type_string(node_type: Any) -> str:
    """Reduce @type to the one token the traversal rules switch on."""
    if isinstance(node_type, list):
        for known in ("Dataset", "Computation", "Sample", "Software",
                      "MLModel", "Experiment", "Activity"):
            if known in node_type:
                return known
        return str(node_type[-1]) if node_type else ""
    return node_type if isinstance(node_type, str) else ""


def is_entity_like(type_str: str) -> bool:
    return any(t in type_str for t in
               ("Dataset", "Sample", "Instrument", "Software", "MLModel"))


def is_activity_like(type_str: str) -> bool:
    return any(t in type_str for t in
               ("Computation", "Experiment", "Annotation", "Activity"))


def refs(value: Any) -> List[str]:
    items = value if isinstance(value, list) else [value]
    return [i["@id"] for i in items
            if isinstance(i, dict) and isinstance(i.get("@id"), str)]


def first_ref(value: Any) -> Optional[str]:
    found = refs(value)
    return found[0] if found else None


def rocrate_outputs(node: dict) -> List[dict]:
    for field in ("https://w3id.org/EVI#outputs", "EVI:outputs", "outputs"):
        if field in node:
            value = node[field]
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                return [value]
    return []


def referenced_ids(node: dict) -> set[str]:
    """The next hop of the BFS: one step further back in provenance."""
    type_str = type_string(node.get("@type", ""))
    if is_entity_like(type_str):
        comp = first_ref(node.get(GENERATED_BY))
        return {comp} if comp else set()
    if is_activity_like(type_str):
        out: set[str] = set()
        for field in USED_FIELDS:
            out.update(refs(node.get(field)))
        return out
    return set()


# --------------------------------------------------------------------------
# 1. Collect
# --------------------------------------------------------------------------

def collect(reader: CrateReader, start_id: str) -> Dict[str, dict]:
    """Breadth-first walk backward through provenance from `start_id`.

    Iterative on purpose -- provenance chains in a real pipeline can be
    hundreds of steps deep and there is no reason to spend stack on them.
    Unresolvable ids become `{"error": "not found"}` stubs rather than
    disappearing, because "this crate references something nobody
    registered" is a finding, not a gap.
    """
    start = reader.find_many([start_id]).get(start_id)
    if start is None:
        return {start_id: {"@id": start_id, "error": "not found"}}

    cache: Dict[str, dict] = {start_id: start}
    frontier = {start_id}
    if is_rocrate(start.get("@type", "")):
        frontier |= {r["@id"] for r in rocrate_outputs(start) if r.get("@id")}

    processed: set[str] = set()
    while frontier:
        pending = frontier - processed
        if not pending:
            break

        missing = [g for g in pending if g not in cache]
        if missing:
            cache.update(reader.find_many(missing))
            for guid in missing:
                cache.setdefault(guid, {"@id": guid, "error": "not found"})

        nxt: set[str] = set()
        for guid in pending:
            processed.add(guid)
            node = cache.get(guid)
            if node and "error" not in node:
                nxt |= referenced_ids(node)
        frontier = nxt

    return cache


# --------------------------------------------------------------------------
# 2. Condense
# --------------------------------------------------------------------------

def _family(node: dict) -> tuple:
    """What makes two sibling datasets interchangeable for display."""
    return (node.get("format") or node.get("encodingFormat"),
            first_ref(node.get(GENERATED_BY)))


def _group_node(group_id: str, members: List[str], cache: Dict[str, dict]) -> dict:
    first = cache[members[0]]
    fmt, generated_by = _family(first)
    node = {
        "@id": group_id,
        "@type": ["evi:DatasetGroup"],
        "name": f"{len(members)} similar datasets",
        "description": (
            f"{len(members)} datasets generated the same way and collapsed "
            f"for display. Representative: {members[0]}"
        ),
        "evi:memberCount": len(members),
        "evi:representativeDataset": {"@id": members[0]},
        "evi:commonFormat": fmt,
        "evi:condensationThreshold": CONDENSE_THRESHOLD,
    }
    if generated_by:
        node[GENERATED_BY] = {"@id": generated_by}
        software = first_ref((cache.get(generated_by) or {}).get("usedSoftware"))
        if software:
            node["evi:commonSoftware"] = {"@id": software}
    return node


def _condense_refs(
    ref_list: List[dict], cache: Dict[str, dict], owner: str, threshold: int
) -> tuple[List[dict], int]:
    """Replace look-alike families inside one list of references.

    A family is a set of datasets in the same list sharing a format and a
    generating computation. Above `threshold` they become one DatasetGroup
    reference; the members stay in the cache but nothing points at them
    any more, so projection simply never reaches them.
    """
    families: Dict[tuple, List[str]] = defaultdict(list)
    order: List[Any] = []
    for ref in ref_list:
        guid = ref.get("@id") if isinstance(ref, dict) else None
        node = cache.get(guid) if guid else None
        if node is None or "error" in node or "Dataset" not in type_string(node.get("@type", "")):
            order.append(ref)
            continue
        key = _family(node)
        if key not in families:
            order.append(key)
        families[key].append(guid)

    condensed, collapsed = [], 0
    for item in order:
        if not isinstance(item, tuple):
            condensed.append(item)
            continue
        members = families[item]
        if len(members) <= threshold:
            condensed.extend({"@id": m} for m in members)
            continue
        group_id = f"{owner}-group-{len(condensed)}"
        cache[group_id] = _group_node(group_id, members, cache)
        condensed.append({"@id": group_id})
        collapsed += len(members)
    return condensed, collapsed


def condense(
    cache: Dict[str, dict], start_id: str, threshold: int = CONDENSE_THRESHOLD
) -> dict:
    """Collapse repetitive sibling datasets, in place.

    Two places produce them in practice, and this handles exactly those:
    a crate that outputs thousands of near-identical files, and a
    computation that consumes them. Deliberately non-recursive -- the full
    condenser derives provenance signatures over whole subgraphs, which is
    a lot of machinery for a display concern.
    """
    if threshold is None:
        return {"condensed": False, "reason": "condensation disabled"}

    collapsed, groups_before = 0, len([n for n in cache.values()
                                       if "DatasetGroup" in str(n.get("@type"))])

    start = cache.get(start_id)
    if start and is_rocrate(start.get("@type", "")):
        outputs = rocrate_outputs(start)
        if outputs:
            replaced, n = _condense_refs(outputs, cache, start_id, threshold)
            collapsed += n
            if n:
                start = dict(start)
                for field in ("https://w3id.org/EVI#outputs", "EVI:outputs", "outputs"):
                    if field in start:
                        start[field] = replaced
                cache[start_id] = start

    for guid, node in list(cache.items()):
        if "error" in node or not is_activity_like(type_string(node.get("@type", ""))):
            continue
        used = node.get("usedDataset")
        if not used:
            continue
        replaced, n = _condense_refs(
            used if isinstance(used, list) else [used], cache, guid, threshold
        )
        if n:
            collapsed += n
            node = dict(node)
            node["usedDataset"] = replaced
            cache[guid] = node

    groups = len([n for n in cache.values()
                  if "DatasetGroup" in str(n.get("@type"))]) - groups_before
    return {
        "condensed": bool(collapsed),
        "threshold": threshold,
        "groups_created": groups,
        "datasets_collapsed": collapsed,
    }


# --------------------------------------------------------------------------
# 3. Project
# --------------------------------------------------------------------------

def _expand_used_dataset(value: Any, cache: Dict[str, dict]) -> List[dict]:
    """A used dataset that is itself a crate contributes its outputs."""
    out = []
    for guid in refs(value):
        node = cache.get(guid)
        if node and "error" not in node and is_rocrate(node.get("@type", "")):
            nested = [r["@id"] for r in rocrate_outputs(node) if r.get("@id")]
            out.extend({"@id": n} for n in nested) if nested else out.append({"@id": guid})
        else:
            out.append({"@id": guid})
    return out


def _project_node(
    node: dict, cache: Dict[str, dict],
    is_start_rocrate: bool, start_outputs: Optional[List[dict]],
) -> tuple[dict, List[str]]:
    """One node reduced to display fields, plus the ids it points at."""
    built = {
        "@id": node.get("@id"),
        "@type": node.get("@type"),
        "name": node.get("name"),
        "description": node.get("description"),
    }
    if node.get("createdBy"):
        built["createdBy"] = node["createdBy"]
    if is_start_rocrate and start_outputs:
        built["hasOutputs"] = start_outputs

    follow: List[str] = []
    type_str = type_string(node.get("@type", ""))

    if is_entity_like(type_str):
        generated_by = node.get(GENERATED_BY)
        comp = first_ref(generated_by)
        if comp:
            built[GENERATED_BY] = {"@id": comp}
            follow.append(comp)
        elif generated_by:
            built[GENERATED_BY] = generated_by

    elif is_activity_like(type_str):
        if node.get("usedDataset"):
            expanded = _expand_used_dataset(node["usedDataset"], cache)
            if expanded:
                built["usedDataset"] = expanded
                follow.extend(r["@id"] for r in expanded)
        for field in ("usedSoftware", "usedSample", "usedInstrument", "usedMLModel"):
            found = refs(node.get(field))
            if found:
                built[field] = [{"@id": g} for g in found]
                follow.extend(found)

    if "DatasetGroup" in str(node.get("@type")):
        for field in ("evi:memberCount", "evi:representativeDataset",
                      "evi:commonFormat", "evi:commonSoftware", "format",
                      "evi:condensationThreshold"):
            if field in node:
                built[field] = node[field]
        representative = node.get("evi:representativeDataset")
        rep_id = (representative.get("@id") if isinstance(representative, dict)
                  else representative)
        if rep_id:
            follow.append(rep_id)

    return built, follow


def project(
    cache: Dict[str, dict], start_id: str
) -> tuple[Dict[str, dict], List[dict]]:
    """Turn the node cache into (graph, outputs).

    Iterative, so a long provenance chain cannot exhaust the stack and a
    cycle cannot wedge it -- a node is claimed in `graph` before its
    references are queued.
    """
    start = cache.get(start_id)
    if start is None or "error" in start:
        return ({start_id: {"@id": start_id, "error": "not found"}},
                [{"@id": start_id}])

    outputs: List[dict] = []
    start_rocrate_outputs: Optional[List[dict]] = None
    if is_rocrate(start.get("@type", "")):
        start_rocrate_outputs = list(rocrate_outputs(start))
        for ref in start_rocrate_outputs + [{"@id": start_id}]:
            if isinstance(ref, dict) and ref.get("@id"):
                outputs.append({"@id": ref["@id"]})
    else:
        outputs.append({"@id": start_id})

    graph: Dict[str, dict] = {}
    queue = [ref["@id"] for ref in outputs]
    while queue:
        guid = queue.pop(0)
        if guid in graph:
            continue
        node = cache.get(guid)
        if node is None:
            graph[guid] = {"@id": guid, "error": "not found"}
            continue
        if "error" in node:
            graph[guid] = node
            continue
        graph[guid] = {}                      # claim before expanding
        built, follow = _project_node(
            node, cache,
            is_start_rocrate=(guid == start_id and start_rocrate_outputs is not None),
            start_outputs=start_rocrate_outputs,
        )
        graph[guid] = built
        queue.extend(follow)

    return graph, outputs


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def build(
    con, node_id: str, threshold: Optional[int] = CONDENSE_THRESHOLD
) -> Optional[dict]:
    """The evidence graph for one @id, or None if it is not indexed."""
    entity = db.resolve(con, node_id)
    if entity is None:
        return None

    reader = CrateReader(con)
    cache = collect(reader, entity.id)
    stats = condense(cache, entity.id, threshold)
    graph, outputs = project(cache, entity.id)

    return {
        "@id": evidence_graph_id(entity.id),
        "@type": "evi:EvidenceGraph",
        "name": f"Evidence graph for {entity.name or entity.id}",
        "description": f"Provenance of {entity.id}, built from the crate index.",
        "outputs": outputs,
        "@graph": graph,
        "condensation_stats": stats,
    }
