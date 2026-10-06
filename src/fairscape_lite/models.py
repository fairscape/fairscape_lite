"""Pydantic mirrors of schema.sql, plus the two things that cross the wire.

Each Table subclass has one field per column, in column order, with the
same nullability. That is the point: db.py never spells a column list or
counts placeholders by hand, so a schema change that isn't mirrored here
fails loudly at ingest instead of quietly writing values one position off.
"""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from typing import Any, ClassVar, Optional

from fairscape_models.rocrate import ROCrateV1_2
from pydantic import BaseModel, ConfigDict, Field


class Row(BaseModel):
    """A thing that can be built from a sqlite3.Row."""

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_row(cls, row: Optional[sqlite3.Row]):
        return cls.model_validate(dict(row)) if row is not None else None

    @classmethod
    def from_rows(cls, rows):
        return [cls.model_validate(dict(r)) for r in rows]


class Table(Row):
    """A Row that knows its table, and can therefore write its own SQL."""

    table: ClassVar[str]
    generated: ClassVar[tuple[str, ...]] = ()   # columns SQLite fills in

    @classmethod
    def columns(cls) -> list[str]:
        return [n for n in cls.model_fields if n not in cls.generated]

    def values(self) -> tuple:
        return tuple(getattr(self, name) for name in self.columns())

    @classmethod
    def insert(cls, verb: str = "INSERT") -> str:
        cols = cls.columns()
        placeholders = ", ".join("?" * len(cols))
        return f"{verb} INTO {cls.table} ({', '.join(cols)}) VALUES ({placeholders})"

    @classmethod
    def upsert(cls, key: str) -> str:
        """INSERT that updates on conflict, rather than replacing.

        `INSERT OR REPLACE` would DELETE the conflicting row first, and any
        ON DELETE CASCADE hanging off it fires -- which for `crate` means
        silently dropping every entity the crate owns.
        """
        assignments = ", ".join(
            f"{c} = excluded.{c}" for c in cls.columns() if c != key
        )
        return f"{cls.insert()} ON CONFLICT({key}) DO UPDATE SET {assignments}"

    @classmethod
    def update(cls, where: str) -> str:
        """UPDATE with every column set, in values() order. Bind values()
        first, then whatever `where` needs."""
        assignments = ", ".join(f"{c} = ?" for c in cls.columns())
        return f"UPDATE {cls.table} SET {assignments} WHERE {where}"


class Crate(Table):
    """A registered ro-crate-metadata.json file."""

    table: ClassVar[str] = "crate"

    id: str                          # the crate root's @id
    path: str                        # absolute path to the metadata file
    context: Optional[str] = None    # verbatim @context, JSON text
    mtime: float                     # st_mtime at ingest
    size: int                        # st_size at ingest
    node_count: int                  # len(@graph) on disk
    ingested_at: str


class Entity(Table):
    """One globally-unique @id."""

    table: ClassVar[str] = "entity"
    generated: ClassVar[tuple[str, ...]] = ("pk",)

    pk: Optional[int] = None           # rowid alias; entity_fts joins on it
    id: str                            # the @id, verbatim
    ark_key: Optional[str] = None      # 'naan/postfix', dashes stripped
    fairscape_type: str                # Dataset, Computation, ROCrate, ...
    types: str                         # verbatim @type, JSON text
    name: Optional[str] = None
    description: Optional[str] = None
    keywords: Optional[str] = None     # verbatim, JSON text
    content_url: Optional[str] = None
    source_crate: str

    @property
    def type_list(self) -> Any:
        """@type as the crate wrote it -- string or list."""
        return json.loads(self.types)

    @property
    def keyword_list(self) -> Any:
        return json.loads(self.keywords) if self.keywords else []


class Edge(Table):
    """A link between two @ids. Objects need not be indexed."""

    table: ClassVar[str] = "edge"

    subject: str
    predicate: str
    object: str
    position: int = 0


class EntitySummary(Row):
    """What listings and search return: index columns only, no file read."""

    select: ClassVar[str] = (
        "entity.id, entity.fairscape_type AS type, entity.name, "
        "entity.description, entity.source_crate"
    )

    id: str
    type: str
    name: Optional[str] = None
    description: Optional[str] = None
    source_crate: str


class CrateSummary(Row):
    """What GET /rocrate returns."""

    select: ClassVar[str] = (
        "c.id, c.path, c.node_count, c.ingested_at, "
        "(SELECT COUNT(*) FROM entity WHERE source_crate = c.id) AS entities"
    )

    id: str
    path: str
    node_count: int
    ingested_at: str
    entities: int


class IngestStats(BaseModel):
    """What one ingest did. Returned straight out of POST /rocrate."""

    crate: Optional[str] = None
    path: Optional[str] = None
    skipped: bool = False
    nodes: int = 0                  # len(@graph) on disk
    entities_inserted: int = 0
    entities_refreshed: int = 0
    entities_kept: int = 0          # seen, but another crate owns them
    entities_dropped: int = 0       # gone from this crate since last ingest
    edges: int = 0
    error: Optional[str] = None     # why this file was not indexed (tree walks)

    def count(self, key: str, n: int = 1) -> None:
        setattr(self, key, getattr(self, key) + n)


class Identifier(BaseModel):
    """The resolver envelope, reduced.

    The old server's StoredIdentifier carried permissions, distribution,
    publication status, descriptive and split statistics, and a typed
    MetadataUnion over 23 model classes. Every one of those belonged to a
    feature this server does not have. What survives is the shape the web
    client actually destructures: an @id, the @type, and the metadata.
    `sourceCrate` is new, and is the honest answer to "where did this
    come from" now that nothing is copied into the database.
    """

    model_config = ConfigDict(populate_by_name=True)

    guid: str = Field(alias="@id")
    metadataType: Any = Field(alias="@type")   # verbatim: string or list
    metadata: dict
    sourceCrate: Optional[str] = None

    def dump(self) -> dict:
        return self.model_dump(by_alias=True)


def validate_crate(data: dict) -> None:
    """Raise pydantic ValidationError unless `data` is a valid RO-Crate.

    Validates a copy: ROCrateV1_2.model_validate mutates the dict it is
    given, and the caller goes on to index the original.
    """
    ROCrateV1_2.model_validate(deepcopy(data))
