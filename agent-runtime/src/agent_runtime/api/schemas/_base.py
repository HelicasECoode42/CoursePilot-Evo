"""Base wire types shared by every CoursePilot DTO.

These mirror ``contracts/schemas/domain.schema.json`` ``$defs``. Field names,
enums and constraints are kept identical so Pydantic validation matches the
JSON Schema contract. ``tests/test_schema_contract.py`` proves the mapping by
validating the repository's positive/negative examples through these models.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# ``contracts`` restricts identifiers to a leading alnum character followed by up
# to 119 of ``[A-Za-z0-9._:-]``. Reused by every id-like field.
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$"

Id = Annotated[str, StringConstraints(pattern=ID_PATTERN, max_length=120)]

# Credits are BigDecimal / SQL DECIMAL on the Java side; keep them as Decimal
# here instead of float (docs/04-infrastructure-workflow.md section 4).
Credits = Annotated[Decimal, Field(ge=0, le=1000, multiple_of=Decimal("0.01"))]


class DomainModel(BaseModel):
    """Base for wire DTOs: reject any field that is not in the contract."""

    model_config = ConfigDict(extra="forbid")


class SourceRef(DomainModel):
    kind: Literal["CURRICULUM", "OFFERING", "REVIEW", "CURATED_TAG", "SYNTHETIC"]
    refId: Id
    snapshotId: Id | None
    locator: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    capturedAt: datetime | None


class Issue(DomainModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    message: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    field: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None
    retryable: bool


EnvelopeStatus = Literal[
    "OK",
    "UNKNOWN",
    "INVALID_INPUT",
    "UNAUTHORIZED",
    "FORBIDDEN",
    "NOT_FOUND",
    "CONFLICT",
    "ERROR",
]

T = TypeVar("T")


class Envelope(DomainModel, Generic[T]):
    schemaVersion: Literal["1.0"]
    requestId: Id
    traceId: Id | None
    status: EnvelopeStatus
    data: T
    provenance: list[SourceRef] = Field(max_length=200)
    issues: list[Issue] = Field(max_length=200)
