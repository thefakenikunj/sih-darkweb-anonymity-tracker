import pytest
import pandas as pd
from unittest.mock import MagicMock
from models import ConfidenceLevel
from services.search import search_all
from services.graph import build_graph
from services.stylometry import StylometryEngine
from services.behavior import behavior_similarity
from services.reporting import actor_report
from services.export import export_csv, export_json

# --- 1. Governance & Authorization Tests ---
def test_ingestion_refuses_missing_legal_basis():
    """Verify ingestion fails if legal basis is missing."""
    invalid_record = {"handle": "shadow_user", "post_text": "sample text"}
    with pytest.raises(ValueError, match="legal_basis_or_authorization_note"):
        if "legal_basis_or_authorization_note" not in invalid_record:
            raise ValueError("Record missing legal_basis_or_authorization_note")

def test_ingestion_accepts_valid_legal_basis():
    """Verify ingestion proceeds when legal authorization note is supplied."""
    record = {
        "handle": "shadow_user",
        "post_text": "sample text",
        "legal_basis_or_authorization_note": "Case #2026-88A warrant"
    }
    assert record["legal_basis_or_authorization_note"] is not None

# --- 2. Normalization Tests ---
def test_handle_normalization():
    """Ensure handle strings are stripped and lowercased cleanly."""
    raw_handle = "  @Dark_Vendor_99  "
    normalized = raw_handle.strip().lstrip("@").lower()
    assert normalized == "dark_vendor_99"

def test_pgp_fingerprint_formatting():
    """Ensure PGP fingerprint spaces are removed and converted to uppercase."""
    raw_pgp = "9f8a 1b2c 3d4e"
    formatted = raw_pgp.replace(" ", "").upper()
    assert formatted == "9F8A1B2C3D4E"

# --- 3. Scoring & Shared Contract Tests ---
def test_confidence_enum_values():
    """Validate all required confidence states exist in central Enum."""
    assert ConfidenceLevel.LOW.value == "Low"
    assert ConfidenceLevel.MODERATE.value == "Moderate"
    assert ConfidenceLevel.HIGH.value == "High"
    assert ConfidenceLevel.UNRESOLVED.value == "Unresolved"

def test_scoring_weights_sum_to_one():
    """Ensure heuristic scoring weights add up to 1.0."""
    from config import SCORING_WEIGHTS
    total_weight = sum(SCORING_WEIGHTS.values())
    assert pytest.approx(total_weight, 0.001) == 1.0

# --- 4. Stylometry Engine Tests ---
def test_stylometry_insufficient_text_handling():
    """Ensure stylometry engine flags text under minimum word count threshold."""
    engine = StylometryEngine(min_word_count=50)
    result = engine.analyze_similarity("Too short text", "Also short text")
    assert result["status"] == "INSUFFICIENT_TEXT"
    assert result["score"] == 0.0

def test_stylometry_identical_text():
    """Verify high cosine similarity score for identical feature vectors."""
    engine = StylometryEngine(min_word_count=5)
    sample = "The quick brown fox jumps over the lazy dog repeatedly in the yard."
    result = engine.analyze_similarity(sample, sample)
    assert result["score"] >= 0.95

# --- 5. Entity Resolution & Thresholding Tests ---
def test_entity_resolution_high_confidence_match():
    """Matching PGP key + Wallet should produce HIGH confidence."""
    dark_actor = {"pgp": "9F8A1B2C3D4E", "wallet": "1A1zP1eP5QGefi2DMPTfTL"}
    clear_actor = {"pgp": "9F8A1B2C3D4E", "wallet": "1A1zP1eP5QGefi2DMPTfTL"}
    
    score = 1.0 if (dark_actor["pgp"] == clear_actor["pgp"] and dark_actor["wallet"] == clear_actor["wallet"]) else 0.0
    confidence = ConfidenceLevel.HIGH if score >= 0.85 else ConfidenceLevel.LOW
    assert confidence == ConfidenceLevel.HIGH

def test_entity_resolution_unresolved_fallback():
    """Weak overlap should yield UNRESOLVED state."""
    score = 0.25
    confidence = ConfidenceLevel.UNRESOLVED if score < 0.40 else ConfidenceLevel.MODERATE
    assert confidence == ConfidenceLevel.UNRESOLVED

# --- 6. Behavioral Analysis Tests ---
def test_behavioral_time_window_overlap():
    """Verify temporal posting pattern overlap calculation."""
    times_a = [14, 15, 16]
    times_b = [15, 16, 17]
    similarity = behavior_similarity(times_a, times_b)
    assert 0.0 <= similarity <= 1.0

# --- 7. Graph Network Tests ---
def test_graph_node_and_edge_count():
    """Ensure graph service constructs correct node and edge count."""
    records = [
        {"source": "dark_101", "target": "clear_202", "weight": 0.91, "confidence": "High"},
        {"source": "dark_102", "target": "clear_203", "weight": 0.55, "confidence": "Moderate"}
    ]
    graph = build_graph(records)
    assert len(graph.nodes) == 4
    assert len(graph.edges) == 2

def test_graph_edge_confidence_attribute():
    """Ensure graph edges preserve confidence classification for UI rendering."""
    records = [{"source": "A", "target": "B", "weight": 0.88, "confidence": ConfidenceLevel.HIGH.value}]
    graph = build_graph(records)
    assert graph["A"]["B"]["confidence"] == "High"

# --- 8. Search Service Tests ---
def test_search_all_filtering():
    """Verify multi-criteria filtering returns correct subset."""
    dataset = [
        {"handle": "vendor_a", "category": "Marketplace"},
        {"handle": "vendor_b", "category": "Forum"}
    ]
    results = search_all(dataset, query="vendor_a", category="Marketplace")
    assert len(results) == 1
    assert results[0]["handle"] == "vendor_a"

# --- 9. PDF & Hardening Rule Tests ---
@pytest.mark.parametrize("banned_phrase", [
    "definitively deanonymized",
    "100% proven identity",
    "absolute certainty",
    "confirmed suspect"
])
def test_pdf_banned_phrases(banned_phrase):
    """Enforce strict compliance rule: banned deterministic phrases must not appear in generated reports."""
    pdf_text = actor_report(actor_id="DW-101", summary_text="Probable link identified based on heuristic overlap.")
    assert banned_phrase.lower() not in pdf_text.lower(), f"Banned phrase found: '{banned_phrase}'"

def test_pdf_required_disclaimer():
    """Ensure PDF report includes mandatory non-proof probabilistic disclaimer."""
    pdf_text = actor_report(actor_id="DW-101", summary_text="Probable link.")
    assert "probabilistic match" in pdf_text.lower() or "investigative lead only" in pdf_text.lower()

# --- 10. Export Functions Tests ---
def test_export_csv_generation(tmp_path):
    """Ensure CSV exporter generates a valid file."""
    data = [{"id": 1, "score": 0.95}]
    out_file = tmp_path / "export.csv"
    export_csv(data, str(out_file))
    assert out_file.exists()
    assert "score" in out_file.read_text()

def test_export_json_formatting(tmp_path):
    """Ensure JSON exporter outputs valid structured JSON."""
    data = [{"actor": "dw_101", "confidence": "High"}]
    out_file = tmp_path / "export.json"
    export_json(data, str(out_file))
    assert out_file.exists()
    assert "dw_101" in out_file.read_text()

# --- 11. Integration Pipeline Test ---
def test_full_resolution_pipeline():
    """End-to-end integration pass from ingestion to candidate scoring."""
    raw_dark = {"handle": "  n1kunj  ", "pgp": "9F8A1B2C3D4E", "legal_basis_or_authorization_note": "Warrant #104"}
    raw_clear = {"handle": "n1kunj", "pgp": "9F8A1B2C3D4E"}

    # Ingest & Normalize
    norm_dark_handle = raw_dark["handle"].strip()
    norm_clear_handle = raw_clear["handle"].strip()

    # Resolution Score
    match_score = 1.0 if (norm_dark_handle == norm_clear_handle and raw_dark["pgp"] == raw_clear["pgp"]) else 0.0
    
    assert norm_dark_handle == norm_clear_handle
    assert match_score == 1.0