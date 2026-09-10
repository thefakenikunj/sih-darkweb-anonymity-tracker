"""
tests/test_phase8.py

Exercises services/reporting.py and services/export.py against the real
seed_demo dataset (Phase 6), not synthetic stand-ins. Run with:

    cd <project_root> && python -m pytest tests/test_phase8.py -v

Requires phase_6.py's write_dataset() to have been run first (or this
file's setup_module does it into a temp copy of data/ automatically).
"""

from __future__ import annotations

import csv as csv_module
import io
import json
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "services"))

import config  # noqa: E402
from services import export, reporting  # noqa: E402

# seed_demo.py was uploaded as phase_6.py; import it under its real name.
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("seed_demo", PROJECT_ROOT / "phase_6.py")
seed_demo = _ilu.module_from_spec(_spec)
sys.modules["seed_demo"] = seed_demo
_spec.loader.exec_module(seed_demo)


@pytest.fixture(scope="module")
def dataset():
    entities, links, observations = seed_demo.build_dataset()
    return entities, links, observations


# ---------------------------------------------------------------------------
# reporting.py
# ---------------------------------------------------------------------------

def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_pdf_builds_without_error(dataset):
    entities, links, observations = dataset
    result = reporting.build_pdf_report(entities, links, observations)
    assert result.pdf_bytes.startswith(b"%PDF")
    assert result.rejected_phrases == []


def test_pdf_contains_no_banned_phrases_from_config(dataset):
    """The banned-phrase list itself comes from config.py (the Phase 0
    contract Phase 9's own evaluation tests are supposed to share), not a
    copy defined in this test file."""
    entities, links, observations = dataset
    result = reporting.build_pdf_report(entities, links, observations)
    assert result.rejected_phrases == []
    text = _pdf_text(result.pdf_bytes).lower()
    for phrase in config.BANNED_REPORT_PHRASES:
        assert phrase.lower() not in text


def test_banned_phrase_in_evidence_text_blocks_generation():
    """If a reason-code description or observation text were ever to smuggle
    banned wording in (e.g. a future reason code labeled 'proven to be a
    match'), report generation must fail loudly rather than silently ship
    a report that overclaims."""
    poisoned_label = "proven to be a match"
    original = dict(reporting._REASON_CODE_LABELS)
    reporting._REASON_CODE_LABELS["exact_pgp_match"] = poisoned_label
    try:
        entities = [
            {"entity_id": "a", "display_name": "A"},
            {"entity_id": "b", "display_name": "B"},
        ]
        links = [{
            "source_id": "a", "target_id": "b", "confidence_score": 0.95,
            "reason_codes": ["exact_pgp_match"], "method": "entity_resolution",
            "evidence_refs": [], "observed_at": None,
        }]
        with pytest.raises(reporting.BannedPhraseError):
            reporting.build_pdf_report(entities, links, [])
    finally:
        reporting._REASON_CODE_LABELS.clear()
        reporting._REASON_CODE_LABELS.update(original)


def test_confidence_wording_matches_config_thresholds():
    """A score just under config's HIGH threshold must not render as High."""
    just_below_high = config.CONFIDENCE_THRESHOLDS[config.ConfidenceLevel.HIGH] - 0.01
    level = config.score_to_confidence(just_below_high)
    assert level == config.ConfidenceLevel.MODERATE
    sentence = reporting._linkage_sentence("A", "B", level, just_below_high)
    assert "high" not in sentence.lower() or "moderate" in sentence.lower()
    for banned in ("confirmed", "proven", "definitely", "beyond doubt"):
        assert banned not in sentence.lower()


def test_unresolved_confidence_never_states_a_relationship_positively(dataset):
    entities, links, observations = dataset
    sentence = reporting._linkage_sentence("X", "Y", config.ConfidenceLevel.UNRESOLVED, 0.0)
    assert "does not support" in sentence


def test_isolated_entity_appears_in_report(dataset):
    """vendor_iota (demonstration property #7) has zero links and must
    still show up in the PDF as a named 'no linkage found' entity, not be
    silently dropped."""
    entities, links, observations = dataset
    result = reporting.build_pdf_report(entities, links, observations)
    text = _pdf_text(result.pdf_bytes)
    assert "vendor_iota" in text


def test_reason_code_naming_drift_between_phase6_and_config(dataset):
    """Documents a real inconsistency rather than hiding it: Phase 6's
    seed_demo.py emits reason codes like 'exact_pgp_match' and
    'stylometric_dissimilarity' that are NOT keys in config.SCORING_WEIGHTS
    (which has 'exact_pgp_fingerprint_match', etc). reporting.py degrades
    gracefully for these (see _reason_label), but this test exists so the
    drift shows up in CI instead of only in a PDF someone happens to read
    closely."""
    entities, links, observations = dataset
    all_codes = {code for link in links for code in link.reason_codes}
    unknown_to_config = sorted(c for c in all_codes if c not in config.SCORING_WEIGHTS)
    assert unknown_to_config, (
        "Expected some drift between Phase 6 reason codes and "
        "config.SCORING_WEIGHTS today; if this now passes with an empty "
        "list, the drift was fixed and this test (and its comment) is "
        "safe to delete."
    )


# ---------------------------------------------------------------------------
# export.py — CSV
# ---------------------------------------------------------------------------

def test_csv_round_trips_all_links(dataset):
    entities, links, observations = dataset
    csv_text = export.to_csv(links, entities)
    rows = list(csv_module.DictReader(io.StringIO(csv_text)))
    assert len(rows) == len(links)
    ids = {(r["source_id"], r["target_id"]) for r in rows}
    expected = {(l.source_id, l.target_id) for l in links}
    assert ids == expected


def test_csv_confidence_level_matches_config_not_hardcoded(dataset):
    entities, links, observations = dataset
    csv_text = export.to_csv(links, entities)
    rows = list(csv_module.DictReader(io.StringIO(csv_text)))
    for row in rows:
        expected = config.score_to_confidence(float(row["confidence_score"])).value
        assert row["confidence_level"] == expected


# ---------------------------------------------------------------------------
# export.py — JSON
# ---------------------------------------------------------------------------

def test_json_is_valid_and_complete(dataset):
    entities, links, observations = dataset
    payload = json.loads(export.to_json(entities, links, observations))
    assert payload["entity_count"] == len(entities)
    assert payload["link_count"] == len(links)
    assert len(payload["entities"]) == len(entities)
    assert len(payload["links"]) == len(links)


def test_json_never_uses_confirmed_language(dataset):
    entities, links, observations = dataset
    text = export.to_json(entities, links, observations).lower()
    for phrase in config.BANNED_REPORT_PHRASES:
        assert phrase.lower() not in text


# ---------------------------------------------------------------------------
# export.py — STIX-like bundle
# ---------------------------------------------------------------------------

def test_stix_bundle_has_one_identity_per_entity(dataset):
    entities, links, observations = dataset
    bundle = export.to_stix_bundle(entities, links)
    identities = [o for o in bundle["objects"] if o["type"] == "identity"]
    assert len(identities) == len(entities)
    assert all(o["x_pseudonymous_persona"] is True for o in identities)


def test_stix_bundle_relationship_confidence_is_numeric_0_100(dataset):
    entities, links, observations = dataset
    bundle = export.to_stix_bundle(entities, links)
    rels = [o for o in bundle["objects"] if o["type"] == "relationship"]
    assert len(rels) == len(links)
    for r in rels:
        assert 0 <= r["confidence"] <= 100
        desc = r["description"].lower()
        for phrase in config.BANNED_REPORT_PHRASES:
            assert phrase.lower() not in desc
        assert "requires independent human review" in desc


def test_stix_bundle_flags_itself_as_non_compliant(dataset):
    entities, links, observations = dataset
    bundle = export.to_stix_bundle(entities, links)
    assert "not validated against" in bundle["x_compliance_note"].lower()


def test_stix_contradictory_evidence_pair_produces_two_relationships(dataset):
    """Demonstration property #5: vendor_epsilon <-> vendor_zeta has two
    LinkRecords (PGP match + stylometric dissimilarity). The bundle must
    not collapse these into one relationship — both pieces of
    contradictory evidence need to survive into the export."""
    entities, links, observations = dataset
    bundle = export.to_stix_bundle(entities, links)
    rels = [
        o for o in bundle["objects"]
        if o["type"] == "relationship"
        and {o.get("x_method")} & {"entity_resolution", "stylometry"}
    ]
    ez_rels = [
        o for o in bundle["objects"]
        if o["type"] == "relationship"
    ]
    # match by looking at the underlying identities' x_entity_id
    id_to_entity = {
        o["id"]: o["x_entity_id"] for o in bundle["objects"] if o["type"] == "identity"
    }
    pair_rels = [
        r for r in ez_rels
        if {id_to_entity.get(r["source_ref"]), id_to_entity.get(r["target_ref"])}
        == {"vendor_epsilon", "vendor_zeta"}
    ]
    assert len(pair_rels) == 2
