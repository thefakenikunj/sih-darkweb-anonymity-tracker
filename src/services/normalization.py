"""
services/normalization.py — Phase 1

Owns the write path from a collector's RawRecords into the database:
  - computes content_hash and enforces DB-level dedup
  - re-checks the DEMO_MODE / legal-basis gates at the Source level (defense
    in depth — a collector could in principle be misused directly without
    going through its own __init__ checks, e.g. by mutating attributes
    after construction, so this is the second and authoritative gate)
  - resolves/creates the Persona a record belongs to
  - calls services/extraction.py to pull identifiers out of the text and
    attaches them to the persona
  - writes an AuditLog row for every successful ingest

Nothing in this module executes, evaluates, or renders raw_text. It is
read with hashlib/regex only and stored as a plain Text column.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

import config
from collectors.base import BaseCollector, RawRecord
from models import AuditLog, Identifier, Observation, Persona, Source
from services.extraction import extract_identifiers


class NormalizationError(Exception):
    """Raised when a Source fails governance checks at write time, or a
    record is malformed. Ingestion stops rather than skipping silently —
    a silently-skipped governance violation is worse than a loud one."""


@dataclass
class IngestStats:
    ingested: int = 0
    deduped: int = 0
    errors: list[str] = field(default_factory=list)


def compute_content_hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _enforce_source_governance(source: Source) -> None:
    """Authoritative, second check of the same gates BaseCollector applies
    at construction time. This is what actually protects the database,
    independent of how the caller obtained the Source object."""
    if config.DEMO_MODE and not source.is_demo_data:
        raise NormalizationError(
            f"Refusing to ingest into Source '{source.name}': config.DEMO_MODE "
            f"is True but this source is not marked is_demo_data."
        )
    if (
        config.ENFORCE_LEGAL_BASIS
        and not source.is_demo_data
        and not (source.legal_basis_or_authorization_note or "").strip()
    ):
        raise NormalizationError(
            f"Refusing to ingest into Source '{source.name}': "
            f"ENFORCE_LEGAL_BASIS is True, this is non-demo data, and no "
            f"legal_basis_or_authorization_note is recorded."
        )


def get_or_create_persona(db: Session, handle: str) -> Persona:
    existing = db.query(Persona).filter_by(display_handle=handle).first()
    if existing is not None:
        return existing
    persona = Persona(display_handle=handle)
    db.add(persona)
    db.flush()
    return persona


def ingest_record(db: Session, source: Source, record: RawRecord) -> Observation | None:
    """Ingest a single RawRecord. Returns the created Observation, or None
    if the record was a duplicate (by content hash) of one already stored.

    Raises NormalizationError on a governance violation or malformed record;
    callers (ingest_from_collector) should let this propagate rather than
    catching and continuing.
    """
    _enforce_source_governance(source)

    if not record.raw_text or not record.raw_text.strip():
        raise NormalizationError("Refusing to ingest an empty raw_text record.")

    content_hash = compute_content_hash(record.raw_text)
    existing = db.query(Observation).filter_by(content_hash=content_hash).first()
    if existing is not None:
        return None  # dedup — identical content already stored

    persona: Persona | None = None
    if record.persona_handle:
        persona = get_or_create_persona(db, record.persona_handle)

    observation = Observation(
        source_id=source.id,
        persona_id=persona.id if persona else None,
        observation_type=record.observation_type,
        raw_text=record.raw_text,
        content_hash=content_hash,
        observed_at=record.observed_at,
    )
    db.add(observation)
    db.flush()

    if persona is not None:
        for identifier_type, value in extract_identifiers(record.raw_text):
            already = (
                db.query(Identifier)
                .filter_by(persona_id=persona.id, identifier_type=identifier_type, value=value)
                .first()
            )
            if already is None:
                db.add(
                    Identifier(
                        persona_id=persona.id,
                        identifier_type=identifier_type,
                        value=value,
                        observation_id=observation.id,
                    )
                )

    db.add(
        AuditLog(
            action=config.AUDIT_ACTION_INGEST,
            actor="normalization",
            detail={
                "source_id": source.id,
                "observation_id": observation.id,
                "persona_id": persona.id if persona else None,
                "content_hash": content_hash,
            },
        )
    )

    return observation


def ingest_from_collector(db: Session, collector: BaseCollector) -> IngestStats:
    """Run a collector end-to-end: resolve/create its Source, then ingest
    every record it yields. Continues past individual malformed records
    (recording them in stats.errors) but re-raises immediately on a
    NormalizationError caused by a governance violation, since that means
    something is wrong with the Source itself, not one bad record."""
    source = collector.get_or_create_source(db)
    _enforce_source_governance(source)

    stats = IngestStats()
    for record in collector.collect():
        try:
            result = ingest_record(db, source, record)
        except NormalizationError as exc:
            # Governance-level failures apply to the whole source, not just
            # one record — stop immediately rather than partially ingesting.
            raise
        except Exception as exc:  # malformed individual record
            stats.errors.append(str(exc))
            continue

        if result is None:
            stats.deduped += 1
        else:
            stats.ingested += 1

    return stats
