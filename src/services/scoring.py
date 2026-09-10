"""
services/scoring.py — Phase 2

Pure combination logic. Takes a list of reason codes (keys into
config.SCORING_WEIGHTS) and turns them into a single score + confidence
level. This is the ONE place that formula lives — entity_resolution.py,
the Phase 7 UI's score-explanation panel, and the Phase 9 evaluation script
should all call compute_pairwise_score() (or, for the UI, simply redisplay
the reason_codes already stored on an EntityLink) rather than re-deriving
the number, so the displayed explanation can never drift from the number
that actually drove the decision.

Combination method: evidence is combined as independent probabilistic
signals via a noisy-OR, separately for corroborating and contradicting
evidence, then the two are subtracted. This avoids the naive-sum problem
where three weak 0.35 signals could otherwise add up to more certainty
than one 0.95 near-certain match — each additional weak signal still
raises confidence, but with diminishing effect, which is the correct
behavior for weight values that are meant to represent something closer
to per-signal probabilities than raw points.
"""

from __future__ import annotations

from config import SCORING_WEIGHTS, ConfidenceLevel, score_to_confidence


class UnknownReasonCodeError(Exception):
    """Raised if a caller passes a reason code that isn't in
    config.SCORING_WEIGHTS. Evidence must always come from the shared
    table — silently ignoring an unknown code would make the displayed
    score explanation lie about what was actually used."""


def _validate_reason_codes(reason_codes: list[str]) -> None:
    unknown = [c for c in reason_codes if c not in SCORING_WEIGHTS]
    if unknown:
        raise UnknownReasonCodeError(
            f"Unknown reason code(s) {unknown}; every reason code must be a "
            f"key in config.SCORING_WEIGHTS."
        )


def compute_pairwise_score(reason_codes: list[str]) -> tuple[float, ConfidenceLevel]:
    """Combine reason codes into (raw_score, confidence).

    raw_score is in [-1.0, 1.0]. Positive means corroborating evidence
    dominates; negative means contradicting evidence dominates. A negative
    or zero raw_score always maps to ConfidenceLevel.UNRESOLVED — a link
    should never be displayed as even LOW confidence if the net evidence
    doesn't actually favor a match.
    """
    _validate_reason_codes(reason_codes)

    positive_weights = [SCORING_WEIGHTS[c] for c in reason_codes if SCORING_WEIGHTS[c] > 0]
    negative_weights = [-SCORING_WEIGHTS[c] for c in reason_codes if SCORING_WEIGHTS[c] < 0]

    corroborating = _noisy_or(positive_weights)
    contradicting = _noisy_or(negative_weights)

    raw_score = max(-1.0, min(1.0, corroborating - contradicting))
    confidence = score_to_confidence(raw_score) if raw_score > 0 else ConfidenceLevel.UNRESOLVED
    return raw_score, confidence


def _noisy_or(weights: list[float]) -> float:
    """1 - product(1 - w_i). Each additional piece of evidence pushes the
    combined value closer to 1.0, but with diminishing returns, and a
    single weight of 1.0 would saturate it immediately — since no entry in
    SCORING_WEIGHTS reaches 1.0, that's a deliberate headroom, not an
    oversight."""
    if not weights:
        return 0.0
    remaining = 1.0
    for w in weights:
        remaining *= (1.0 - w)
    return 1.0 - remaining


def explain(reason_codes: list[str]) -> list[tuple[str, float]]:
    """Return [(reason_code, weight), ...] for display — e.g. the Phase 7
    UI's score-explanation panel. Kept here so the UI never has to import
    config.SCORING_WEIGHTS directly and risk formatting it inconsistently."""
    _validate_reason_codes(reason_codes)
    return [(c, SCORING_WEIGHTS[c]) for c in reason_codes]
