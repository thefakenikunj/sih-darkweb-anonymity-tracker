"""
services/stylometry.py — Phase 3

Builds a StyleProfile per persona from the concatenated text of their
Observations. Deliberately uses simple, well-established, explainable
features rather than a black-box embedding model:

  - function-word frequency ratios (classic stylometric signal — these
    words are used subconsciously and are hard to deliberately vary)
  - a handful of coarse text statistics (avg word length, avg sentence
    length, punctuation ratio, vocabulary richness)

This is intentionally NOT a strong claim of authorship. Per the project's
own risk assessment, TF-IDF/cosine-style similarity on short text is a
weak signal — the point of computing total_chars_analyzed and gating on
config.STYLOMETRY_MIN_CHARS (enforced in entity_resolution.py, not here)
is so the rest of the system never treats a thin sample as a real match.

Feature values are each scaled into a roughly comparable [0, 1]-ish range
so that cosine similarity (computed generically in entity_resolution.py)
isn't dominated by whichever feature happens to have the largest raw
magnitude. This is a practical normalization, not a statistically
rigorous one — documented here so nobody mistakes it for more than it is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from models import Observation, Persona, StyleProfile

# A compact set of classic function words used in stylometry (closed-class
# words: articles, prepositions, conjunctions, common pronouns/auxiliaries).
# Kept short and generic-English rather than corpus-tuned, since this is a
# demo tool, not a production authorship-attribution system.
_FUNCTION_WORDS: tuple[str, ...] = (
    "the", "of", "and", "to", "a", "in", "that", "is", "was", "for",
    "it", "with", "as", "on", "be", "at", "by", "this", "had", "not",
    "are", "but", "from", "or", "have", "an", "they", "which", "one",
    "you", "were", "all", "there", "would", "we", "been", "has", "when",
    "who", "will", "if", "out", "so", "up", "its", "about", "into",
    "than", "them", "can", "only", "other", "could", "these", "may",
    "then", "do", "any", "my", "now", "like", "our", "even", "did",
    "just", "because", "each", "both",
)

_WORD_RE = re.compile(r"[A-Za-z']+")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_PUNCT_RE = re.compile(r"[^\w\s]")


@dataclass
class StyleFeatures:
    feature_vector: dict = field(default_factory=dict)
    total_chars: int = 0


def compute_style_features(text: str) -> StyleFeatures:
    """Pure function: text in, feature vector out. No I/O."""
    total_chars = len(text)
    if total_chars == 0:
        return StyleFeatures(feature_vector={}, total_chars=0)

    words = _WORD_RE.findall(text.lower())
    n_words = len(words)

    features: dict[str, float] = {}

    if n_words > 0:
        word_counts: dict[str, int] = {}
        for w in words:
            word_counts[w] = word_counts.get(w, 0) + 1

        for fw in _FUNCTION_WORDS:
            ratio = word_counts.get(fw, 0) / n_words
            if ratio > 0:
                features[f"fw:{fw}"] = ratio

        avg_word_len = sum(len(w) for w in words) / n_words
        features["avg_word_len"] = min(avg_word_len / 15.0, 1.0)

        type_token_ratio = len(word_counts) / n_words
        features["type_token_ratio"] = type_token_ratio

    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if sentences:
        avg_sentence_len_words = n_words / max(len(sentences), 1)
        features["avg_sentence_len"] = min(avg_sentence_len_words / 40.0, 1.0)

    punct_count = len(_PUNCT_RE.findall(text))
    features["punct_ratio"] = min(punct_count / total_chars, 1.0)

    return StyleFeatures(feature_vector=features, total_chars=total_chars)


def _persona_corpus(persona: Persona) -> list[str]:
    return [obs.raw_text for obs in persona.observations if obs.raw_text]


def build_style_profile(db: Session, persona: Persona) -> StyleProfile | None:
    """Create or update the StyleProfile for one persona from all of their
    Observations' text combined. Returns None (and does not create a row)
    if the persona has no observations at all — that's a distinct state
    from "analyzed but too little text", which entity_resolution.py relies
    on to tell "not processed yet" apart from "processed, low confidence."
    """
    texts = _persona_corpus(persona)
    if not texts:
        return None

    combined_text = "\n".join(texts)
    result = compute_style_features(combined_text)

    existing = db.query(StyleProfile).filter_by(persona_id=persona.id).first()
    if existing is not None:
        existing.feature_vector = result.feature_vector
        existing.total_chars_analyzed = result.total_chars
        db.flush()
        return existing

    profile = StyleProfile(
        persona_id=persona.id,
        feature_vector=result.feature_vector,
        total_chars_analyzed=result.total_chars,
    )
    db.add(profile)
    db.flush()
    return profile


@dataclass
class StylometryStats:
    profiles_built: int = 0
    personas_skipped_no_text: int = 0


def build_all_style_profiles(db: Session) -> StylometryStats:
    stats = StylometryStats()
    for persona in db.query(Persona).all():
        profile = build_style_profile(db, persona)
        if profile is None:
            stats.personas_skipped_no_text += 1
        else:
            stats.profiles_built += 1
    return stats
