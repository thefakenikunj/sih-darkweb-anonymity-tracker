"""
config.py — Phase 0

Single source of truth for everything that Phase 2 (scoring), Phase 7 (UI),
Phase 8 (reporting), and Phase 9 (evaluation) all need to agree on.

Nothing here is secret. Actual secrets (DB URLs, API keys) come from the
environment / .env file, never hardcoded.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# .env loading (no hard dependency on python-dotenv if it isn't installed)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Core mode flags
# ---------------------------------------------------------------------------

# DEMO_MODE gates the entire application to synthetic data only. When True:
#   - collectors/local_import.py and any live-network collector paths are
#     refused at the collector layer (see Phase 1), not just hidden in the UI.
#   - the dashboard displays a persistent "SYNTHETIC DATA — DEMO MODE" banner.
# This is a safety-relevant flag, not cosmetic: flipping it to False is a
# deliberate, logged action (see AUDIT_ACTION_MODE_CHANGE below), and doing so
# does NOT by itself enable ingestion of unauthorized real-world data — that
# is gated separately by ENFORCE_LEGAL_BASIS.
DEMO_MODE: bool = _env_bool("DEMO_MODE", True)

# When True (recommended always, and non-negotiable while DEMO_MODE is False),
# the ingestion layer (Phase 1) MUST reject any Source/Observation record that
# does not carry a non-empty legal_basis_or_authorization_note. This is
# enforced in code in models.py / normalization.py, not left as a schema
# field someone could leave blank.
ENFORCE_LEGAL_BASIS: bool = _env_bool("ENFORCE_LEGAL_BASIS", True)

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'demo.db'}"
)

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")


# ---------------------------------------------------------------------------
# Confidence enum — used by models, graph edge coloring, UI badges, and
# the PDF report's wording rules. Defined exactly once.
# ---------------------------------------------------------------------------

class ConfidenceLevel(str, Enum):
    UNRESOLVED = "unresolved"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"

    @property
    def color(self) -> str:
        """UI / graph-edge color hint. Kept here so Phase 7 never invents
        its own mapping that could drift from this one."""
        return {
            ConfidenceLevel.UNRESOLVED: "#9CA3AF",  # gray
            ConfidenceLevel.LOW: "#F59E0B",         # amber
            ConfidenceLevel.MODERATE: "#3B82F6",    # blue
            ConfidenceLevel.HIGH: "#DC2626",        # red
        }[self]


# Numeric score -> ConfidenceLevel. A single function so scoring.py and the
# evaluation script (Phase 9) can never disagree on the cutoffs.
CONFIDENCE_THRESHOLDS: dict[ConfidenceLevel, float] = {
    ConfidenceLevel.HIGH: 0.85,
    ConfidenceLevel.MODERATE: 0.60,
    ConfidenceLevel.LOW: 0.30,
    # anything below LOW's threshold is UNRESOLVED
}


def score_to_confidence(score: float) -> ConfidenceLevel:
    if score >= CONFIDENCE_THRESHOLDS[ConfidenceLevel.HIGH]:
        return ConfidenceLevel.HIGH
    if score >= CONFIDENCE_THRESHOLDS[ConfidenceLevel.MODERATE]:
        return ConfidenceLevel.MODERATE
    if score >= CONFIDENCE_THRESHOLDS[ConfidenceLevel.LOW]:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.UNRESOLVED


# ---------------------------------------------------------------------------
# Scoring weights — the shared contract between entity_resolution.py,
# the UI's score-explanation display, and the evaluation script.
#
# Each entry is (weight, human-readable reason code template). Positive
# weights are corroborating evidence; negative weights are contradicting
# evidence. Entity resolution should never invent a weight inline — it
# should always pull from this table so the number shown in the UI and the
# number that actually drove the decision are provably the same value.
# ---------------------------------------------------------------------------

SCORING_WEIGHTS: dict[str, float] = {
    "exact_pgp_fingerprint_match": 0.95,
    "exact_crypto_address_reuse": 0.90,
    "exact_email_match": 0.85,
    "exact_jabber_xmpp_match": 0.80,
    "shared_unique_username_token": 0.55,
    "stylometric_similarity_high": 0.35,
    "stylometric_similarity_moderate": 0.15,
    "behavioral_timing_overlap": 0.10,
    "shared_forum_signature_phrase": 0.20,
    # Contradicting evidence pulls the score down.
    "conflicting_pgp_fingerprint": -0.95,
    "conflicting_stated_timezone": -0.20,
    "conflicting_writing_language": -0.30,
    "insufficient_text_for_stylometry": -0.05,  # small penalty, not a match
}

# Minimum combined text length (characters) before stylometry is allowed to
# contribute a positive weight at all. Below this, scoring.py must record
# "insufficient_text_for_stylometry" instead of a similarity score, and the
# UI must show the same "insufficient text" disclaimer — not a hidden
# assumption inside the model.
STYLOMETRY_MIN_CHARS: int = 500


# ---------------------------------------------------------------------------
# Report-wording safety net (Phase 8). Enforced with actual string-matching
# tests over generated PDFs in Phase 9 — this list is the ground truth for
# those tests, not just a style suggestion for whoever writes the template.
# ---------------------------------------------------------------------------

BANNED_REPORT_PHRASES: tuple[str, ...] = (
    "definitively deanonymized",
    "confirmed identity",
    "proven to be",
    "is definitely",
    "beyond doubt",
    "100% match",
    "conclusively identified",
    "irrefutably linked",
)

REQUIRED_REPORT_DISCLAIMER = (
    "This report presents probabilistic, evidence-linked assessments only. "
    "No finding in this report should be treated as definitive proof of "
    "identity. All confidence levels reflect the scoring methodology in "
    "config.SCORING_WEIGHTS and are subject to revision as new evidence "
    "is ingested."
)


# ---------------------------------------------------------------------------
# Audit log action constants (Phase 1 / AuditLog model) — centralized so
# every writer uses the same vocabulary instead of ad-hoc strings.
# ---------------------------------------------------------------------------

AUDIT_ACTION_INGEST = "ingest"
AUDIT_ACTION_ENTITY_LINK_CREATED = "entity_link_created"
AUDIT_ACTION_ENTITY_LINK_OVERRIDDEN = "entity_link_overridden"
AUDIT_ACTION_REPORT_EXPORTED = "report_exported"
AUDIT_ACTION_MODE_CHANGE = "mode_change"
