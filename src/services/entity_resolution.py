"""
services/entity_resolution.py — Phase 2

Compares personas pairwise, gathers evidence from three independent
sources (shared identifiers, behavioral-profile overlap, stylometric
similarity), and hands the resulting reason codes to services/scoring.py
to produce an explainable EntityLink.

Design notes:
  - Evidence-gathering is split into three small functions
    (_identifier_evidence / _behavior_evidence / _stylometry_evidence) that
    each degrade gracefully when their inputs don't exist yet (e.g.
    stylometry evidence is simply skipped for a persona Phase 3 hasn't
    processed — it does NOT get penalized as "insufficient text", which is
    reserved for personas that were analyzed but had too little text).
  - This module never invents a weight inline. Every reason code it emits
    is a key from config.SCORING_WEIGHTS; scoring.py will raise if that
    ever stops being true.
  - An EntityLink that an analyst has already reviewed (CONFIRMED_BY_ANALYST
    or REJECTED_BY_ANALYST) is never silently overwritten by a re-run of
    resolve_all() — only PROPOSED links get recomputed.
  - Pair generation is a simple O(n^2) sweep, appropriate for a synthetic
    demo dataset. See MAX_PERSONAS_WITHOUT_BLOCKING below for the guardrail
    and what production hardening (Phase 10) should replace this with.
"""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

import config
from models import AuditLog, EntityLink, IdentifierType, LinkStatus, Persona
from services import scoring

# Above this many personas, naive O(n^2) pairwise comparison stops being
# reasonable. Phase 10 hardening notes should point here: replace
# generate_pairs() with a blocking/canopy step (e.g. only compare personas
# that already share at least one identifier or a coarse stylometric
# cluster) before this ceiling is ever hit in practice.
MAX_PERSONAS_WITHOUT_BLOCKING = 2000


class EntityResolutionError(Exception):
    pass


@dataclass
class ResolutionStats:
    pairs_considered: int = 0
    links_created: int = 0
    links_updated: int = 0
    links_skipped_reviewed: int = 0
    errors: list[str] = field(default_factory=list)


_IDENTIFIER_TYPE_TO_WEIGHT_KEY: dict[IdentifierType, str] = {
    IdentifierType.PGP_FINGERPRINT: "exact_pgp_fingerprint_match",
    IdentifierType.CRYPTO_ADDRESS: "exact_crypto_address_reuse",
    IdentifierType.EMAIL: "exact_email_match",
    IdentifierType.JABBER_XMPP: "exact_jabber_xmpp_match",
    IdentifierType.USERNAME: "shared_unique_username_token",
    IdentifierType.SIGNATURE_PHRASE: "shared_forum_signature_phrase",
}


# ---------------------------------------------------------------------------
# Evidence gathering
# ---------------------------------------------------------------------------

def _identifier_evidence(persona_a: Persona, persona_b: Persona) -> list[str]:
    a_by_type: dict[IdentifierType, set[str]] = defaultdict(set)
    for ident in persona_a.identifiers:
        a_by_type[ident.identifier_type].add(ident.value)

    b_by_type: dict[IdentifierType, set[str]] = defaultdict(set)
    for ident in persona_b.identifiers:
        b_by_type[ident.identifier_type].add(ident.value)

    evidence: list[str] = []
    for id_type, weight_key in _IDENTIFIER_TYPE_TO_WEIGHT_KEY.items():
        a_vals, b_vals = a_by_type.get(id_type, set()), b_by_type.get(id_type, set())
        if a_vals & b_vals:
            evidence.append(weight_key)
        elif a_vals and b_vals and id_type == IdentifierType.PGP_FINGERPRINT:
            # Both personas have a claimed PGP fingerprint but they don't
            # match each other — treated as active contradicting evidence
            # only for high-trust identifier types like PGP, not for every
            # identifier type (two personas simply having *different*
            # usernames isn't evidence of anything).
            evidence.append("conflicting_pgp_fingerprint")

    return evidence


def _histogram_cosine(hist_a: dict, hist_b: dict) -> float | None:
    if not hist_a or not hist_b:
        return None
    keys = set(hist_a) | set(hist_b)
    dot = sum(float(hist_a.get(k, 0)) * float(hist_b.get(k, 0)) for k in keys)
    norm_a = math.sqrt(sum(float(v) ** 2 for v in hist_a.values()))
    norm_b = math.sqrt(sum(float(v) ** 2 for v in hist_b.values()))
    if norm_a == 0 or norm_b == 0:
        return None
    return dot / (norm_a * norm_b)


def _behavior_evidence(persona_a: Persona, persona_b: Persona) -> list[str]:
    bp_a, bp_b = persona_a.behavior_profile, persona_b.behavior_profile
    if bp_a is None or bp_b is None:
        return []  # Phase 3 behavioral profiling hasn't run for one/both yet

    evidence: list[str] = []

    if (
        bp_a.inferred_timezone
        and bp_b.inferred_timezone
        and bp_a.inferred_timezone != bp_b.inferred_timezone
    ):
        evidence.append("conflicting_stated_timezone")

    overlap = _histogram_cosine(bp_a.posting_hour_histogram, bp_b.posting_hour_histogram)
    if overlap is not None and overlap >= 0.6:
        evidence.append("behavioral_timing_overlap")

    return evidence


def _vector_cosine(vec_a: dict, vec_b: dict) -> float:
    if not vec_a or not vec_b:
        return 0.0
    common = set(vec_a) & set(vec_b)
    dot = sum(float(vec_a[k]) * float(vec_b[k]) for k in common)
    norm_a = math.sqrt(sum(float(v) ** 2 for v in vec_a.values()))
    norm_b = math.sqrt(sum(float(v) ** 2 for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _stylometry_evidence(persona_a: Persona, persona_b: Persona) -> list[str]:
    sp_a, sp_b = persona_a.style_profile, persona_b.style_profile
    if sp_a is None or sp_b is None:
        return []  # Phase 3 stylometry hasn't run for one/both personas yet

    if (
        sp_a.total_chars_analyzed < config.STYLOMETRY_MIN_CHARS
        or sp_b.total_chars_analyzed < config.STYLOMETRY_MIN_CHARS
    ):
        # Analyzed, but too little text to trust — this is the disclaimed
        # "insufficient text" case from the spec, distinct from "not
        # analyzed yet" above. Must surface in the UI, not just here.
        return ["insufficient_text_for_stylometry"]

    evidence: list[str] = []
    similarity = _vector_cosine(sp_a.feature_vector, sp_b.feature_vector)
    if similarity >= 0.75:
        evidence.append("stylometric_similarity_high")
    elif similarity >= 0.5:
        evidence.append("stylometric_similarity_moderate")

    lang_a = (sp_a.feature_vector or {}).get("language")
    lang_b = (sp_b.feature_vector or {}).get("language")
    if lang_a and lang_b and lang_a != lang_b:
        evidence.append("conflicting_writing_language")

    return evidence


def gather_evidence(persona_a: Persona, persona_b: Persona) -> list[str]:
    """All reason codes for this pair, from every available source.
    Exposed separately from resolve_pair() so the Phase 7 UI or Phase 9
    evaluation script can preview evidence without writing an EntityLink."""
    return (
        _identifier_evidence(persona_a, persona_b)
        + _behavior_evidence(persona_a, persona_b)
        + _stylometry_evidence(persona_a, persona_b)
    )


# ---------------------------------------------------------------------------
# Resolution / persistence
# ---------------------------------------------------------------------------

def resolve_pair(db: Session, persona_a: Persona, persona_b: Persona) -> EntityLink | None:
    """Score one persona pair and create/update its EntityLink. Returns None
    if there is no evidence at all for the pair (no row is written — an
    empty EntityLink for every unrelated pair would be pure noise) or if an
    analyst has already reviewed this pair (their status is preserved and
    the existing link is returned unmodified)."""
    if persona_a.id == persona_b.id:
        return None

    a_id, b_id = sorted((persona_a.id, persona_b.id))
    ordered_a, ordered_b = (
        (persona_a, persona_b) if persona_a.id == a_id else (persona_b, persona_a)
    )

    existing = (
        db.query(EntityLink).filter_by(persona_a_id=a_id, persona_b_id=b_id).first()
    )
    if existing is not None and existing.status != LinkStatus.PROPOSED:
        return existing  # analyst-reviewed — never silently recomputed

    reason_codes = gather_evidence(ordered_a, ordered_b)
    if not reason_codes:
        return None

    score, confidence = scoring.compute_pairwise_score(reason_codes)

    if existing is not None:
        existing.score = score
        existing.confidence = confidence
        existing.reason_codes = reason_codes
        db.flush()
        link = existing
        action_detail_note = "updated"
    else:
        link = EntityLink(
            persona_a_id=a_id,
            persona_b_id=b_id,
            score=score,
            confidence=confidence,
            reason_codes=reason_codes,
            status=LinkStatus.PROPOSED,
        )
        db.add(link)
        db.flush()
        action_detail_note = "created"

    db.add(
        AuditLog(
            action=config.AUDIT_ACTION_ENTITY_LINK_CREATED,
            actor="entity_resolution",
            detail={
                "entity_link_id": link.id,
                "persona_a_id": a_id,
                "persona_b_id": b_id,
                "score": score,
                "confidence": confidence.value,
                "reason_codes": reason_codes,
                "action": action_detail_note,
            },
        )
    )
    return link


def resolve_all(db: Session) -> ResolutionStats:
    """Recompute EntityLinks for every persona pair with any evidence.
    Analyst-reviewed links are left untouched (see resolve_pair)."""
    personas = db.query(Persona).all()
    if len(personas) > MAX_PERSONAS_WITHOUT_BLOCKING:
        raise EntityResolutionError(
            f"{len(personas)} personas exceeds MAX_PERSONAS_WITHOUT_BLOCKING "
            f"({MAX_PERSONAS_WITHOUT_BLOCKING}). Naive O(n^2) comparison is "
            f"no longer appropriate at this scale — implement a blocking "
            f"step (e.g. only compare personas sharing an identifier or a "
            f"coarse stylometric cluster) before raising this ceiling."
        )

    stats = ResolutionStats()
    for persona_a, persona_b in itertools.combinations(personas, 2):
        stats.pairs_considered += 1
        try:
            a_id, b_id = sorted((persona_a.id, persona_b.id))
            existing = (
                db.query(EntityLink).filter_by(persona_a_id=a_id, persona_b_id=b_id).first()
            )
            was_reviewed = existing is not None and existing.status != LinkStatus.PROPOSED

            link = resolve_pair(db, persona_a, persona_b)

            if link is None:
                continue
            elif was_reviewed:
                stats.links_skipped_reviewed += 1
            elif existing is None:
                stats.links_created += 1
            else:
                stats.links_updated += 1
        except Exception as exc:
            stats.errors.append(f"{persona_a.id}-{persona_b.id}: {exc}")

    return stats


def set_analyst_status(
    db: Session, entity_link: EntityLink, status: LinkStatus, actor: str
) -> EntityLink:
    """Record an analyst's confirm/reject decision. This is the ONLY
    supported way to move a link out of PROPOSED — resolve_all() will
    never touch it again afterward."""
    previous_status = entity_link.status
    entity_link.status = status
    db.add(
        AuditLog(
            action=config.AUDIT_ACTION_ENTITY_LINK_OVERRIDDEN,
            actor=actor,
            detail={
                "entity_link_id": entity_link.id,
                "previous_status": previous_status.value
                if hasattr(previous_status, "value")
                else previous_status,
                "new_status": status.value if hasattr(status, "value") else status,
            },
        )
    )
    db.flush()
    return entity_link
