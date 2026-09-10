"""
collectors/base.py — Phase 1

Every collector (synthetic, local_import, and any future live collector)
goes through this base class. This is deliberately where the governance
checks from the scoping doc live — in code, at construction/collect time —
rather than being something a caller could bypass by calling a lower-level
function directly.

Two independent gates, both enforced here:
  1. DEMO_MODE gate: if config.DEMO_MODE is True, any collector instance
     that isn't marked is_demo_data=True refuses to run at all.
  2. Legal-basis gate: if config.ENFORCE_LEGAL_BASIS is True, any collector
     instance that isn't demo data must be constructed with a non-empty
     legal_basis_or_authorization_note, or it refuses to run.

A collector's job is only to produce RawRecord objects. It does not touch
the database directly — services/normalization.py owns writes, dedup, and
identifier extraction. This keeps "can this collector even run" separate
from "how do we store what it returns."
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator

from sqlalchemy.orm import Session

import config
from models import ObservationType, Source, SourceType


class CollectorError(Exception):
    """Raised when a collector is misconfigured or refuses to run for a
    governance reason. Never caught-and-ignored by normalization — an
    ingestion run that hits this should stop and surface the reason."""


@dataclass
class RawRecord:
    """What a collector yields. Intentionally minimal and inert: raw_text is
    plain text only, never treated as markup/code by anything downstream."""

    persona_handle: str | None
    observation_type: ObservationType
    raw_text: str
    observed_at: datetime | None = None
    extra: dict = field(default_factory=dict)


class BaseCollector(ABC):
    source_type: SourceType = SourceType.SYNTHETIC

    def __init__(
        self,
        source_name: str,
        *,
        is_demo_data: bool = True,
        legal_basis_or_authorization_note: str | None = None,
    ) -> None:
        self.source_name = source_name
        self.is_demo_data = is_demo_data
        self.legal_basis_or_authorization_note = legal_basis_or_authorization_note
        self._check_governance_gates()

    # -- governance -----------------------------------------------------

    def _check_governance_gates(self) -> None:
        if config.DEMO_MODE and not self.is_demo_data:
            raise CollectorError(
                f"{type(self).__name__} refused: config.DEMO_MODE is True but "
                f"this collector instance is marked is_demo_data=False. "
                f"Non-synthetic collection is not permitted while the "
                f"application is running in demo mode."
            )
        if (
            config.ENFORCE_LEGAL_BASIS
            and not self.is_demo_data
            and not (self.legal_basis_or_authorization_note or "").strip()
        ):
            raise CollectorError(
                f"{type(self).__name__} refused: config.ENFORCE_LEGAL_BASIS is "
                f"True and this is non-demo data, but no "
                f"legal_basis_or_authorization_note was provided. Supply a "
                f"specific, reviewed justification before collecting "
                f"non-synthetic data."
            )

    # -- interface --------------------------------------------------------

    @abstractmethod
    def collect(self) -> Iterator[RawRecord]:
        """Yield RawRecord instances. Must not perform any writes."""
        raise NotImplementedError

    def get_or_create_source(self, db: Session) -> Source:
        """Idempotent: reuses an existing Source row with the same name +
        type rather than creating a duplicate on every run."""
        existing = (
            db.query(Source)
            .filter_by(name=self.source_name, source_type=self.source_type)
            .first()
        )
        if existing is not None:
            return existing

        source = Source(
            name=self.source_name,
            source_type=self.source_type,
            legal_basis_or_authorization_note=self.legal_basis_or_authorization_note,
            is_demo_data=self.is_demo_data,
        )
        db.add(source)
        db.flush()
        return source
