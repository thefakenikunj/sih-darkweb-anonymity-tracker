"""
schemas.py — Phase 0

Pydantic v2 schemas for the service boundary (Phase 1+ services, and later
the dashboard/CLI). Kept separate from models.py deliberately: ORM models
describe storage, these describe the shapes services accept and return, so
one can evolve without silently breaking the other.

Naming convention: <Thing>Create for input, <Thing>Read for output.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from config import ConfidenceLevel
from models import IdentifierType, LinkStatus, ObservationType, SourceType


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------

class SourceCreate(BaseModel):
    name: str
    source_type: SourceType = SourceType.SYNTHETIC
    legal_basis_or_authorization_note: str | None = None
    is_demo_data: bool = True


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_type: SourceType
    legal_basis_or_authorization_note: str | None
    is_demo_data: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------

class PersonaCreate(BaseModel):
    display_handle: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    notes: str | None = None


class PersonaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_handle: str
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    notes: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Identifier
# ---------------------------------------------------------------------------

class IdentifierCreate(BaseModel):
    persona_id: int
    identifier_type: IdentifierType
    value: str = Field(..., max_length=512)
    observation_id: int | None = None


class IdentifierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    identifier_type: IdentifierType
    value: str
    observation_id: int | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

class ObservationCreate(BaseModel):
    source_id: int
    persona_id: int | None = None
    observation_type: ObservationType
    raw_text: str
    observed_at: datetime | None = None
    # content_hash is deliberately NOT accepted from callers — normalization.py
    # computes it server-side so dedup can't be bypassed by a caller supplying
    # a mismatched hash.


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    persona_id: int | None
    observation_type: ObservationType
    raw_text: str
    content_hash: str
    observed_at: datetime | None
    ingested_at: datetime


# ---------------------------------------------------------------------------
# EntityLink
# ---------------------------------------------------------------------------

class EntityLinkCreate(BaseModel):
    persona_a_id: int
    persona_b_id: int
    score: float = Field(..., ge=-1.0, le=1.0)
    confidence: ConfidenceLevel
    reason_codes: list[str] = Field(default_factory=list)
    status: LinkStatus = LinkStatus.PROPOSED


class EntityLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_a_id: int
    persona_b_id: int
    score: float
    confidence: ConfidenceLevel
    reason_codes: list[str]
    status: LinkStatus
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# StyleProfile
# ---------------------------------------------------------------------------

class StyleProfileCreate(BaseModel):
    persona_id: int
    feature_vector: dict = Field(default_factory=dict)
    total_chars_analyzed: int = 0


class StyleProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    feature_vector: dict
    total_chars_analyzed: int
    updated_at: datetime


# ---------------------------------------------------------------------------
# BehaviorProfile
# ---------------------------------------------------------------------------

class BehaviorProfileCreate(BaseModel):
    persona_id: int
    posting_hour_histogram: dict = Field(default_factory=dict)
    inferred_timezone: str | None = None
    avg_post_length_chars: float | None = None


class BehaviorProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    persona_id: int
    posting_hour_histogram: dict
    inferred_timezone: str | None
    avg_post_length_chars: float | None
    updated_at: datetime


# ---------------------------------------------------------------------------
# GraphEdge
# ---------------------------------------------------------------------------

class GraphEdgeCreate(BaseModel):
    entity_link_id: int | None = None
    persona_a_id: int
    persona_b_id: int
    edge_type: str = "entity_link"
    confidence: ConfidenceLevel


class GraphEdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_link_id: int | None
    persona_a_id: int
    persona_b_id: int
    edge_type: str
    confidence: ConfidenceLevel
    created_at: datetime


# ---------------------------------------------------------------------------
# AuditLog
# ---------------------------------------------------------------------------

class AuditLogCreate(BaseModel):
    action: str
    actor: str = "system"
    detail: dict = Field(default_factory=dict)


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    actor: str
    detail: dict
    created_at: datetime
