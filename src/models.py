"""
models.py — Phase 0

The 9-table data model. This is the contract every later phase builds on:
  1. Source            — where an observation came from (collector run)
  2. Persona            — an observed handle/alias, not a real-world person
  3. Identifier          — a fact tied to a persona (PGP key, wallet, email...)
  4. Observation          — a single raw ingested record (post/message/listing)
  5. EntityLink           — a scored, explainable link between two personas
  6. StyleProfile         — per-persona stylometric fingerprint
  7. BehaviorProfile       — per-persona behavioral signals (timing, etc.)
  8. GraphEdge            — materialized relationship-graph edge (Phase 4)
  9. AuditLog             — who/what/when for every write that matters

Governance notes baked in at the schema level (per the dual-use risk called
out in scoping):
  - Source.legal_basis_or_authorization_note: nullable in the schema (so
    migrations don't break), but Phase 1's ingestion code refuses to insert
    an Observation whose Source lacks this note when
    config.ENFORCE_LEGAL_BASIS is True. The refusal lives in code
    (services/normalization.py), this field just carries the data.
  - Observation.content_hash: unique, used for dedup and to make "did we
    already ingest this" a DB-level guarantee rather than an app-level hope.
  - Nothing in this file executes or renders imported content. Raw content
    is stored as plain text columns only.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import ConfidenceLevel
from db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Shared enums (kept here, alongside the columns that use them, rather than
# scattered into service files where they could drift)
# ---------------------------------------------------------------------------

class SourceType(str, enum.Enum):
    SYNTHETIC = "synthetic"
    LOCAL_IMPORT = "local_import"


class IdentifierType(str, enum.Enum):
    USERNAME = "username"
    EMAIL = "email"
    PGP_FINGERPRINT = "pgp_fingerprint"
    CRYPTO_ADDRESS = "crypto_address"
    JABBER_XMPP = "jabber_xmpp"
    SIGNATURE_PHRASE = "signature_phrase"
    OTHER = "other"


class ObservationType(str, enum.Enum):
    FORUM_POST = "forum_post"
    MARKETPLACE_LISTING = "marketplace_listing"
    PRIVATE_MESSAGE = "private_message"
    PROFILE_METADATA = "profile_metadata"


class LinkStatus(str, enum.Enum):
    PROPOSED = "proposed"          # produced by scoring.py, not yet reviewed
    CONFIRMED_BY_ANALYST = "confirmed_by_analyst"
    REJECTED_BY_ANALYST = "rejected_by_analyst"


# ---------------------------------------------------------------------------
# 1. Source
# ---------------------------------------------------------------------------

class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        String(32), nullable=False, default=SourceType.SYNTHETIC
    )
    # Governance field — see module docstring. Nullable at the schema level;
    # enforced (non-null, non-empty) in code by normalization.py whenever
    # config.ENFORCE_LEGAL_BASIS is True.
    legal_basis_or_authorization_note: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    is_demo_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    observations: Mapped[list["Observation"]] = relationship(back_populates="source")


# ---------------------------------------------------------------------------
# 2. Persona
# ---------------------------------------------------------------------------

class Persona(Base):
    """An observed handle/alias. Deliberately NOT a real-world identity —
    that's what EntityLink + analyst review is for."""

    __tablename__ = "personas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_handle: Mapped[str] = mapped_column(String(255), nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    identifiers: Mapped[list["Identifier"]] = relationship(back_populates="persona")
    observations: Mapped[list["Observation"]] = relationship(back_populates="persona")
    style_profile: Mapped["StyleProfile | None"] = relationship(
        back_populates="persona", uselist=False
    )
    behavior_profile: Mapped["BehaviorProfile | None"] = relationship(
        back_populates="persona", uselist=False
    )


# ---------------------------------------------------------------------------
# 3. Identifier
# ---------------------------------------------------------------------------

class Identifier(Base):
    """A discrete fact tied to a persona — PGP key, wallet address, email,
    reused username, etc. The atomic unit entity_resolution.py compares."""

    __tablename__ = "identifiers"
    __table_args__ = (
        UniqueConstraint(
            "persona_id", "identifier_type", "value", name="uq_persona_identifier"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    persona_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), nullable=False)
    identifier_type: Mapped[IdentifierType] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    observation_id: Mapped[int | None] = mapped_column(
        ForeignKey("observations.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    persona: Mapped["Persona"] = relationship(back_populates="identifiers")


# ---------------------------------------------------------------------------
# 4. Observation
# ---------------------------------------------------------------------------

class Observation(Base):
    """A single raw ingested record. Stored as inert text — never executed,
    parsed as code, or rendered as HTML/markup by any downstream service."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    persona_id: Mapped[int | None] = mapped_column(ForeignKey("personas.id"), nullable=True)
    observation_type: Mapped[ObservationType] = mapped_column(String(32), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    # SHA-256 of raw_text, enforced unique at the DB level for dedup — see
    # services/normalization.py in Phase 1 for how this is computed.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    source: Mapped["Source"] = relationship(back_populates="observations")
    persona: Mapped["Persona | None"] = relationship(back_populates="observations")


# ---------------------------------------------------------------------------
# 5. EntityLink
# ---------------------------------------------------------------------------

class EntityLink(Base):
    """A scored, explainable link between two personas. reason_codes stores
    the ordered list of SCORING_WEIGHTS keys that produced `score`, so the
    UI can render the exact same explanation that drove the number —
    never a re-derived or approximated one."""

    __tablename__ = "entity_links"
    __table_args__ = (
        UniqueConstraint("persona_a_id", "persona_b_id", name="uq_entity_link_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    persona_a_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), nullable=False)
    persona_b_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[ConfidenceLevel] = mapped_column(String(16), nullable=False)
    # List[str] of config.SCORING_WEIGHTS keys, in the order they were applied.
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[LinkStatus] = mapped_column(
        String(32), nullable=False, default=LinkStatus.PROPOSED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ---------------------------------------------------------------------------
# 6. StyleProfile
# ---------------------------------------------------------------------------

class StyleProfile(Base):
    """Per-persona stylometric fingerprint (Phase 3). `total_chars_analyzed`
    is what scoring.py checks against config.STYLOMETRY_MIN_CHARS before
    allowing this profile to contribute a positive weight."""

    __tablename__ = "style_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    persona_id: Mapped[int] = mapped_column(
        ForeignKey("personas.id"), nullable=False, unique=True
    )
    feature_vector: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    total_chars_analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    persona: Mapped["Persona"] = relationship(back_populates="style_profile")


# ---------------------------------------------------------------------------
# 7. BehaviorProfile
# ---------------------------------------------------------------------------

class BehaviorProfile(Base):
    """Per-persona behavioral signals (Phase 3) — posting-time histograms,
    inferred timezone, average post length, etc. Weak/corroborating signal
    only, per SCORING_WEIGHTS['behavioral_timing_overlap']."""

    __tablename__ = "behavior_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    persona_id: Mapped[int] = mapped_column(
        ForeignKey("personas.id"), nullable=False, unique=True
    )
    posting_hour_histogram: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    inferred_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avg_post_length_chars: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    persona: Mapped["Persona"] = relationship(back_populates="behavior_profile")


# ---------------------------------------------------------------------------
# 8. GraphEdge
# ---------------------------------------------------------------------------

class GraphEdge(Base):
    """Materialized relationship-graph edge (Phase 4). Denormalized from
    EntityLink on purpose — graph.py needs fast reads for NetworkX without
    re-joining EntityLink + reason codes on every render, and materializing
    lets Phase 4 add edge types EntityLink doesn't model (e.g. co-mentions)
    without touching the resolution table."""

    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_link_id: Mapped[int | None] = mapped_column(
        ForeignKey("entity_links.id"), nullable=True
    )
    persona_a_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), nullable=False)
    persona_b_id: Mapped[int] = mapped_column(ForeignKey("personas.id"), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False, default="entity_link")
    confidence: Mapped[ConfidenceLevel] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# 9. AuditLog
# ---------------------------------------------------------------------------

class AuditLog(Base):
    """Who/what/when for every write that matters (ingestion, link
    confirmation/override, report export, DEMO_MODE changes). Append-only
    by convention — no service should ever UPDATE or DELETE a row here."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    detail: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
