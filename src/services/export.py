"""
services/export.py — Phase 8

Machine-readable exports: CSV, JSON, and a STIX-2.1-*style* bundle
(subset — enough for a downstream SIEM/analyst tool that expects that
object shape; not validated against the full spec, see
NOT_STIX_COMPLIANT_NOTE). Same Phase 6 Entity/Link/Observation shape as
reporting.py — see that module's docstring for the reconciliation note
about the real DB models.

Replaces phase_7.py's page_reports() placeholder, which explicitly says
"Phase 8 (services/export.py, reporting.py) owns the real ... generation
... This page is a placeholder." app.py should now call into this module
instead of building JSON/CSV inline.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

import config
from config import ConfidenceLevel

# STIX confidence is 0-100 numeric; map our qualitative enum onto the
# midpoint of a conservative band rather than implying false precision.
_STIX_CONFIDENCE_MAP: dict[ConfidenceLevel, int] = {
    ConfidenceLevel.HIGH: 75,
    ConfidenceLevel.MODERATE: 50,
    ConfidenceLevel.LOW: 25,
    ConfidenceLevel.UNRESOLVED: 0,
}

NOT_STIX_COMPLIANT_NOTE = (
    "This bundle uses STIX 2.1-style object shapes (type, id, "
    "created/modified, relationship objects) for interoperability with "
    "tooling that expects that structure, but is not validated against "
    "the full STIX 2.1 specification. Treat as STIX-like, not "
    "STIX-compliant."
)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    return str(value)  # already-serialized strings pass through as-is


def _stix_id(obj_type: str, seed: str) -> str:
    # Deterministic UUIDv5 so re-exporting the same entity_id/link pair is
    # stable across runs (idempotent ingestion / easy diffing over time).
    ns = uuid.uuid5(uuid.NAMESPACE_URL, "urn:phase8-export")
    return f"{obj_type}--{uuid.uuid5(ns, seed)}"


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def to_csv(links: Iterable[Any], entities: Iterable[Any] = ()) -> str:
    """One row per link. Includes both entities' display names alongside
    their ids so the CSV is readable without a join against entities.json."""
    entity_by_id = {_get(e, "entity_id"): e for e in entities}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "source_id", "source_display_name", "target_id", "target_display_name",
        "confidence_score", "confidence_level", "method", "reason_codes", "observed_at",
    ])
    for link in links:
        score = float(_get(link, "confidence_score"))
        confidence = config.score_to_confidence(score)
        src_id, tgt_id = _get(link, "source_id"), _get(link, "target_id")
        src, tgt = entity_by_id.get(src_id), entity_by_id.get(tgt_id)
        writer.writerow([
            src_id,
            _get(src, "display_name", "") if src else "",
            tgt_id,
            _get(tgt, "display_name", "") if tgt else "",
            f"{score:.4f}",
            confidence.value,
            _get(link, "method", ""),
            ";".join(_get(link, "reason_codes", [])),
            _iso(_get(link, "observed_at")),
        ])
    return buf.getvalue()


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def to_json(
    entities: Iterable[Any],
    links: Iterable[Any],
    observations: Iterable[Any] = (),
    *,
    pretty: bool = True,
    demo_mode: bool = config.DEMO_MODE,
) -> str:
    entities = list(entities)
    links = list(links)
    payload = {
        "export_type": "linkage_results",
        "exported_at": _iso(datetime.now(timezone.utc)),
        "demo_mode": demo_mode,
        "wording_note": "Confidence-scored only; not presented as a confirmed match.",
        "entity_count": len(entities),
        "link_count": len(links),
        "entities": [
            {
                "entity_id": _get(e, "entity_id"),
                "display_name": _get(e, "display_name"),
                "entity_type": _get(e, "entity_type"),
                "source_platforms": _get(e, "source_platforms", []),
                "first_seen": _iso(_get(e, "first_seen")),
                "last_seen": _iso(_get(e, "last_seen")),
            }
            for e in entities
        ],
        "links": [
            {
                "source_id": _get(l, "source_id"),
                "target_id": _get(l, "target_id"),
                "confidence_score": float(_get(l, "confidence_score")),
                "confidence_level": config.score_to_confidence(float(_get(l, "confidence_score"))).value,
                "reason_codes": _get(l, "reason_codes", []),
                "method": _get(l, "method"),
                "evidence_refs": _get(l, "evidence_refs", []),
                "observed_at": _iso(_get(l, "observed_at")),
            }
            for l in links
        ],
    }
    return json.dumps(payload, indent=2 if pretty else None, default=str)


# ---------------------------------------------------------------------------
# STIX-like bundle
# ---------------------------------------------------------------------------

def to_stix_bundle(entities: Iterable[Any], links: Iterable[Any]) -> dict:
    """
    - one `identity` object per entity (identity_class "individual",
      tagged x_pseudonymous_persona=True since STIX's identity object has
      no native "pseudonymous online persona" semantics)
    - one `relationship` object per link, relationship_type "related-to",
      confidence mapped from ConfidenceLevel via config.score_to_confidence
    - one `note` object per link carrying the reason-code breakdown, since
      STIX relationships have no native evidence-list field
    """
    entities = list(entities)
    links = list(links)
    now = _iso(datetime.now(timezone.utc))
    objects: list[dict] = []
    entity_stix_id: dict[str, str] = {}

    for e in entities:
        eid = _get(e, "entity_id")
        sid = _stix_id("identity", eid)
        entity_stix_id[eid] = sid
        objects.append({
            "type": "identity",
            "spec_version": "2.1",
            "id": sid,
            "created": now,
            "modified": now,
            "name": _get(e, "display_name"),
            "identity_class": "individual",
            "x_pseudonymous_persona": True,
            "x_entity_id": eid,
            "x_source_platforms": _get(e, "source_platforms", []),
            "x_first_seen": _iso(_get(e, "first_seen")),
            "x_last_seen": _iso(_get(e, "last_seen")),
        })

    for link in links:
        src_id, tgt_id = _get(link, "source_id"), _get(link, "target_id")
        if src_id not in entity_stix_id or tgt_id not in entity_stix_id:
            continue  # skip links referencing entities not in this export
        score = float(_get(link, "confidence_score"))
        confidence = config.score_to_confidence(score)
        stix_confidence = _STIX_CONFIDENCE_MAP[confidence]

        rel_id = _stix_id("relationship", f"{src_id}:{tgt_id}:{_get(link, 'method')}")
        objects.append({
            "type": "relationship",
            "spec_version": "2.1",
            "id": rel_id,
            "created": now,
            "modified": now,
            "relationship_type": "related-to",
            "source_ref": entity_stix_id[src_id],
            "target_ref": entity_stix_id[tgt_id],
            "confidence": stix_confidence,
            "description": (
                f"Automated linkage ({confidence.value} confidence, score={score:.2f}). "
                f"Not presented as a confirmed match; requires independent human review."
            ),
            "x_confidence_level": confidence.value,
            "x_method": _get(link, "method"),
        })

        reason_codes = _get(link, "reason_codes", [])
        if reason_codes:
            note_id = _stix_id("note", f"{src_id}:{tgt_id}:evidence")
            objects.append({
                "type": "note",
                "spec_version": "2.1",
                "id": note_id,
                "created": now,
                "modified": now,
                "abstract": f"Evidence for {src_id} \u2194 {tgt_id}",
                "content": json.dumps(reason_codes),
                "object_refs": [entity_stix_id[src_id], entity_stix_id[tgt_id], rel_id],
            })

    return {
        "type": "bundle",
        "id": _stix_id("bundle", "+".join(sorted(entity_stix_id)) or "empty"),
        "objects": objects,
        "x_compliance_note": NOT_STIX_COMPLIANT_NOTE,
    }
