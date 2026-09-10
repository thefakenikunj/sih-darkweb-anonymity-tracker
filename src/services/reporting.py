"""
services/reporting.py — Phase 8

Turns the Entity/Link/Observation dataset (Phase 6's shape — the same
dataclasses seed_demo.py, phase_4's graph, phase_5's search, and phase_7's
dashboard all already use) into an investigator-facing PDF report.

Reconciliation status
--------------------------------------------------------------------------
This still targets the Phase 6 dict/dataclass dataset (EntityRecord /
LinkRecord / ObservationRecord — entity_id, source_id/target_id,
confidence_score, reason_codes, evidence_refs), not the live SQLAlchemy
EntityLink/Persona models from entity_resolution.py, because that's what's
actually flowing through Phases 4-7 today (phase_7.py's own docstring
says the same: it doesn't have real Phase 0 models.py wired in either).
`linkage_from_entitylink()` at the bottom is the adapter to swap in once
the DB pipeline is the source of truth — same "one place to change"
pattern phase_7.py uses for its own load_data().

What this reuses from config.py rather than reinventing
--------------------------------------------------------------------------
- config.ConfidenceLevel / config.score_to_confidence() — the real
  thresholds (High >= 0.85, Moderate >= 0.60, Low >= 0.30), not
  phase_7.py's local 0.80/0.50 copy. Note for whoever does the Phase 10
  cleanup: phase_7.py's confidence_level() currently disagrees with this
  file about where High/Moderate start. Same underlying issue the phase_7
  docstring already flagged about itself.
- config.BANNED_REPORT_PHRASES — the ground truth for the check below,
  not a separate list that could drift from Phase 9's tests over the same
  wording.
- config.REQUIRED_REPORT_DISCLAIMER — printed verbatim on every report's
  cover page.
- config.AUDIT_ACTION_REPORT_EXPORTED — used if an AuditLog-capable `db`
  session is passed in; omitted (not faked) if it isn't, since this module
  doesn't have real models.AuditLog to import yet.

Report-wording risk (from the original plan)
--------------------------------------------------------------------------
The banned-phrase list is enforced against the *rendered* paragraph text
(after ReportLab markup is stripped), not the template source, so a future
template edit can't silently reintroduce banned wording without a test
catching it. See tests/test_reporting.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Iterable, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import config
from config import ConfidenceLevel

# ---------------------------------------------------------------------------
# Human-readable descriptions for reason codes. Looked up against
# config.SCORING_WEIGHTS first (the Phase 0 contract); reason codes that
# show up in data but aren't in that table (e.g. Phase 6's synthetic
# dataset currently emits "exact_pgp_match" / "stylometric_similarity" /
# "stylometric_dissimilarity", which don't match config's
# "exact_pgp_fingerprint_match" etc.) still render sensibly instead of
# raising, since a report generator is the wrong place to fail loudly over
# an upstream naming drift — but see the assertion in tests/test_reporting.py
# that flags this drift so it doesn't go unnoticed forever.
# ---------------------------------------------------------------------------

_REASON_CODE_LABELS: dict[str, str] = {
    "exact_pgp_fingerprint_match": "Exact PGP fingerprint match",
    "exact_pgp_match": "Exact PGP fingerprint match",
    "exact_crypto_address_reuse": "Reused cryptocurrency address",
    "exact_email_match": "Exact email match",
    "exact_jabber_xmpp_match": "Exact Jabber/XMPP address match",
    "shared_unique_username_token": "Shared distinctive username token",
    "stylometric_similarity": "Stylometric similarity",
    "stylometric_similarity_high": "High stylometric similarity",
    "stylometric_similarity_moderate": "Moderate stylometric similarity",
    "stylometric_dissimilarity": "Stylometric dissimilarity (contradicting signal)",
    "behavioral_timing_overlap": "Overlapping posting-time behavior",
    "shared_forum_signature_phrase": "Shared forum signature phrase",
    "conflicting_pgp_fingerprint": "Conflicting PGP fingerprints (contradicting)",
    "conflicting_stated_timezone": "Conflicting stated timezone (contradicting)",
    "conflicting_writing_language": "Conflicting writing language (contradicting)",
    "insufficient_text_for_stylometry": "Insufficient text for stylometric analysis",
}


def _reason_label(code: str) -> str:
    if code in _REASON_CODE_LABELS:
        return _REASON_CODE_LABELS[code]
    return code.replace("_", " ").capitalize()


def _reason_weight(code: str) -> Optional[float]:
    return config.SCORING_WEIGHTS.get(code)


# ---------------------------------------------------------------------------
# Confidence -> permitted vocabulary. Every sentence describing a linkage
# is generated from this table rather than hand-phrased per call site, so
# no code path can accidentally reach for stronger language than the
# confidence level supports.
# ---------------------------------------------------------------------------

_CONFIDENCE_VERB: dict[ConfidenceLevel, str] = {
    ConfidenceLevel.HIGH: "strong, multiply-corroborated evidence is consistent with",
    ConfidenceLevel.MODERATE: "moderate evidence is consistent with",
    ConfidenceLevel.LOW: "weak, inconclusive evidence is consistent with",
    ConfidenceLevel.UNRESOLVED: "the available evidence does not support",
}

_CONFIDENCE_DISPLAY_COLOR: dict[ConfidenceLevel, colors.Color] = {
    ConfidenceLevel.HIGH: colors.HexColor("#B00020"),
    ConfidenceLevel.MODERATE: colors.HexColor("#B8860B"),
    ConfidenceLevel.LOW: colors.HexColor("#555555"),
    ConfidenceLevel.UNRESOLVED: colors.HexColor("#999999"),
}


class BannedPhraseError(ValueError):
    """Raised when banned wording (config.BANNED_REPORT_PHRASES) makes it
    into rendered report text. A hard fail, not a silent strip — a
    template producing banned language is a bug that should surface
    immediately."""


def _strip_markup(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def check_banned_phrases(text: str) -> list[str]:
    plain = _strip_markup(text).lower()
    return [p for p in config.BANNED_REPORT_PHRASES if p.lower() in plain]


def _linkage_sentence(display_a: str, display_b: str, confidence: ConfidenceLevel, score: float) -> str:
    verb = _CONFIDENCE_VERB[confidence]
    if confidence == ConfidenceLevel.UNRESOLVED:
        return f"{display_a} \u2194 {display_b}: {verb} a relationship between these personas."
    return (
        f"{display_a} \u2194 {display_b}: {verb} a relationship between these personas "
        f"(confidence: {confidence.value}, score: {score:.2f})."
    )


@dataclass
class ReportBuildResult:
    pdf_bytes: bytes
    rejected_phrases: list[str]


def build_pdf_report(
    entities: Iterable[Any],
    links: Iterable[Any],
    observations: Iterable[Any] = (),
    *,
    title: str = "Entity Resolution & Linkage Report",
    demo_mode: bool = config.DEMO_MODE,
    prepared_for: Optional[str] = None,
    enforce_banned_phrases: bool = True,
    db: Any = None,
    exported_by: Optional[str] = None,
) -> ReportBuildResult:
    """
    entities / links / observations: iterables of the Phase 6 dataclass
    shape (entity_id/display_name; source_id/target_id/confidence_score/
    reason_codes/evidence_refs; observation_id/entity_id/platform/content).
    Plain dicts with the same keys also work.

    If `db` is passed (a SQLAlchemy Session with real models.AuditLog
    available), a config.AUDIT_ACTION_REPORT_EXPORTED entry is written.
    Left untouched — not faked — when `db` is None, since this module
    doesn't import models.AuditLog directly (see module docstring).
    """
    entities = list(entities)
    links = list(links)
    observations = list(observations)

    entity_by_id = {_get(e, "entity_id"): e for e in entities}
    obs_by_id = {_get(o, "observation_id"): o for o in observations}

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Disclaimer", parent=styles["Normal"],
                               textColor=colors.HexColor("#555555"), fontSize=8.5, leading=11))

    story: list = []
    rendered: list[str] = []

    def add(flowable):
        story.append(flowable)

    def add_para(text: str, style_name: str = "Normal"):
        rendered.append(text)
        add(Paragraph(text, styles[style_name]))

    # ---- Cover page ----
    add_para(f"<b>{title}</b>", "Title")
    add(Spacer(1, 0.15 * inch))
    add_para(f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}", "Normal")
    if prepared_for:
        add_para(f"Prepared for: {prepared_for}", "Normal")
    if exported_by:
        add_para(f"Exported by: {exported_by}", "Normal")
    add_para(f"Mode: {'SYNTHETIC / DEMO DATA' if demo_mode else 'LIVE DATA'}", "Normal")
    add(Spacer(1, 0.2 * inch))

    if demo_mode:
        add_para(
            "This report was generated while config.DEMO_MODE is enabled, against "
            "synthetic data only. No real individuals are represented.",
            "Disclaimer",
        )
    else:
        add_para(
            "<b>Non-demo report.</b> config.ENFORCE_LEGAL_BASIS governs whether "
            "underlying records without a legal_basis_or_authorization_note were "
            "even ingested; this export does not re-verify that here.",
            "Disclaimer",
        )

    add_para(config.REQUIRED_REPORT_DISCLAIMER, "Disclaimer")
    add(PageBreak())

    # ---- Linkage findings ----
    add_para("<b>Linkage Findings</b>", "Heading1")
    if not links:
        add_para("No links in the current dataset.", "Normal")

    for link in sorted(links, key=lambda l: _get(l, "confidence_score"), reverse=True):
        score = float(_get(link, "confidence_score"))
        confidence = config.score_to_confidence(score)
        src_id, tgt_id = _get(link, "source_id"), _get(link, "target_id")
        src = entity_by_id.get(src_id)
        tgt = entity_by_id.get(tgt_id)
        display_a = _get(src, "display_name") if src else src_id
        display_b = _get(tgt, "display_name") if tgt else tgt_id

        add(Spacer(1, 0.12 * inch))
        badge_color = _CONFIDENCE_DISPLAY_COLOR[confidence]
        add_para(
            f'<font color="{badge_color.hexval()}"><b>[{confidence.value.upper()}]</b></font> '
            f"{display_a} \u2194 {display_b}",
            "Heading3",
        )
        add_para(_linkage_sentence(display_a, display_b, confidence, score), "Normal")
        add_para(f"Method: {_get(link, 'method', 'n/a')}", "Normal")

        reason_codes = _get(link, "reason_codes", [])
        if reason_codes:
            rows = [["Reason code", "Description", "Weight"]]
            for code in reason_codes:
                label = _reason_label(code)
                weight = _reason_weight(code)
                rows.append([code, label, f"{weight:+.2f}" if weight is not None else "n/a"])
                rendered.append(label)
            t = Table(rows, colWidths=[1.9 * inch, 3.1 * inch, 0.8 * inch])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            add(t)

        evidence_refs = _get(link, "evidence_refs", [])
        if evidence_refs:
            add_para("Supporting observations:", "Normal")
            for ref in evidence_refs:
                obs = obs_by_id.get(ref)
                if obs:
                    line = f"&bull; <i>{ref}</i> ({_get(obs, 'entity_id')}, {_get(obs, 'platform')}): {_get(obs, 'content')}"
                else:
                    line = f"&bull; <i>{ref}</i> (observation not found in current dataset)"
                add_para(line, "Normal")

    # ---- Unlinked / isolated entities (worth showing — a clean negative
    # result is itself a finding, per the plan's "isolated entity" case) ----
    linked_ids = {_get(l, "source_id") for l in links} | {_get(l, "target_id") for l in links}
    isolated = [e for e in entities if _get(e, "entity_id") not in linked_ids]
    if isolated:
        add(PageBreak())
        add_para("<b>Entities With No Linkages Found</b>", "Heading1")
        add_para(
            "The following entities returned no corroborating or contradicting "
            "evidence against any other entity in this dataset. Absence of a "
            "linkage is a result, not a gap in analysis.",
            "Disclaimer",
        )
        for e in isolated:
            add_para(f"&bull; {_get(e, 'display_name')} ({_get(e, 'entity_id')})", "Normal")

    # ---- Banned-phrase enforcement on everything actually rendered ----
    rejected = sorted({p for para in rendered for p in check_banned_phrases(para)})
    if rejected and enforce_banned_phrases:
        raise BannedPhraseError(
            f"Report generation blocked \u2014 banned phrase(s) found in rendered text: {rejected}"
        )

    doc.build(story)
    pdf_bytes = buf.getvalue()

    if db is not None:
        _write_audit_log(db, exported_by=exported_by, link_count=len(links), demo_mode=demo_mode)

    return ReportBuildResult(pdf_bytes=pdf_bytes, rejected_phrases=rejected)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Works against both the Phase 6 dataclasses and plain dicts (e.g.
    the JSON round-tripped through seed_demo's load_dataset())."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _write_audit_log(db: Any, *, exported_by: Optional[str], link_count: int, demo_mode: bool) -> None:
    """Best-effort audit logging. Deliberately does not import
    models.AuditLog directly (not available in this session) — if `db`
    doesn't expose what's needed, this no-ops rather than crashing report
    generation over a logging concern."""
    try:
        from models import AuditLog  # local import: optional dependency
    except ImportError:
        return
    db.add(AuditLog(
        action=config.AUDIT_ACTION_REPORT_EXPORTED,
        actor=exported_by or "reporting",
        detail={"link_count": link_count, "demo_mode": demo_mode},
    ))
    db.flush()


# ---------------------------------------------------------------------------
# Adapter for the real DB pipeline (entity_resolution.py's EntityLink /
# Persona), once that's the source of truth instead of the Phase 6 dataset.
# Produces the same plain-dict shape build_pdf_report() already accepts,
# so nothing above needs to change when this gets wired up.
# ---------------------------------------------------------------------------

def linkage_from_entitylink(link: Any, persona_a: Any, persona_b: Any) -> dict:
    return {
        "source_id": str(persona_a.id),
        "target_id": str(persona_b.id),
        "confidence_score": float(link.score),
        "reason_codes": list(link.reason_codes),
        "method": "entity_resolution",
        "evidence_refs": [],
        "observed_at": None,
    }


def entity_from_persona(persona: Any) -> dict:
    return {
        "entity_id": str(persona.id),
        "display_name": getattr(persona, "handle", None) or getattr(persona, "display_name", str(persona.id)),
        "entity_type": "persona",
        "source_platforms": [],
        "first_seen": None,
        "last_seen": None,
    }
