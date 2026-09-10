"""
services/behavior.py — Phase 3

Builds a BehaviorProfile per persona from the observed_at timestamps and
lengths of their Observations:

  - posting_hour_histogram: how many observations fall in each UTC hour
    bucket (0-23), used by entity_resolution.py's cosine-overlap check
  - inferred_timezone: a coarse, heuristic guess based on a "quiet hours"
    gap in posting activity (people tend not to post much while asleep).
    This is a real, published OSINT technique, not a precise instrument —
    it is deliberately gated behind BEHAVIOR_MIN_OBSERVATIONS below and
    returns None rather than guessing on thin data, for the same reason
    stylometry.py refuses to trust short text.
  - avg_post_length_chars: mean raw_text length, a weak secondary signal

None of this is treated as strong evidence anywhere downstream —
config.SCORING_WEIGHTS gives behavioral_timing_overlap one of the lowest
weights in the table (0.10), reflecting how weak a signal posting-time
overlap actually is on its own.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from models import BehaviorProfile, Observation, Persona

# Below this many timestamped observations, any "quiet hours" pattern is
# more likely noise than signal — refuse to infer a timezone rather than
# guess. Chosen conservatively for a demo-scale synthetic dataset.
BEHAVIOR_MIN_OBSERVATIONS = 10

# Length of the assumed nightly "quiet" window, in hours, used to look for
# a sleep gap in the posting-hour histogram.
_QUIET_WINDOW_HOURS = 8
# Assumed local clock hour at the midpoint of a typical person's quietest
# stretch (the middle of a night's sleep) — used only to convert a detected
# quiet-window midpoint into an offset guess, not asserted as literally true
# for any individual.
_ASSUMED_LOCAL_QUIET_MIDPOINT_HOUR = 3


@dataclass
class BehaviorFeatures:
    posting_hour_histogram: dict[str, int]
    inferred_timezone: str | None
    avg_post_length_chars: float | None


def compute_behavior_features(observations: list[Observation]) -> BehaviorFeatures:
    """Pure function: list of Observations (already loaded) in, features
    out. No DB access."""
    timestamped = [o for o in observations if o.observed_at is not None]

    histogram_counter: Counter[int] = Counter()
    for obs in timestamped:
        histogram_counter[obs.observed_at.hour] += 1
    histogram = {str(h): histogram_counter.get(h, 0) for h in range(24)}

    inferred_timezone = None
    if len(timestamped) >= BEHAVIOR_MIN_OBSERVATIONS:
        inferred_timezone = _infer_timezone_from_histogram(histogram_counter)

    lengths = [len(o.raw_text) for o in observations if o.raw_text]
    avg_post_length_chars = sum(lengths) / len(lengths) if lengths else None

    return BehaviorFeatures(
        posting_hour_histogram=histogram,
        inferred_timezone=inferred_timezone,
        avg_post_length_chars=avg_post_length_chars,
    )


def _infer_timezone_from_histogram(histogram_counter: Counter[int]) -> str | None:
    """Find the 8-hour contiguous (wraparound) UTC window with the fewest
    posts, treat its midpoint as the person's likely local sleep midpoint,
    and back out an offset from _ASSUMED_LOCAL_QUIET_MIDPOINT_HOUR.

    This is a coarse heuristic on synthetic demo data, not a claim of
    precision — callers should treat the result as a weak corroborating/
    contradicting signal only (see SCORING_WEIGHTS), never as proof.
    """
    total = sum(histogram_counter.values())
    if total == 0:
        return None

    best_start, best_sum = 0, None
    for start in range(24):
        window_sum = sum(
            histogram_counter.get((start + i) % 24, 0) for i in range(_QUIET_WINDOW_HOURS)
        )
        if best_sum is None or window_sum < best_sum:
            best_sum = window_sum
            best_start = start

    quiet_midpoint_utc = (best_start + _QUIET_WINDOW_HOURS // 2) % 24
    offset = (_ASSUMED_LOCAL_QUIET_MIDPOINT_HOUR - quiet_midpoint_utc) % 24
    if offset > 12:
        offset -= 24  # express as e.g. -5 instead of +19

    sign = "+" if offset >= 0 else "-"
    return f"UTC{sign}{abs(offset)}"


def build_behavior_profile(db: Session, persona: Persona) -> BehaviorProfile | None:
    """Create or update the BehaviorProfile for one persona. Returns None
    (creates no row) if the persona has no observations at all — mirrors
    stylometry.py's "not processed" vs "processed but thin" distinction
    that entity_resolution.py relies on."""
    observations = list(persona.observations)
    if not observations:
        return None

    features = compute_behavior_features(observations)

    existing = db.query(BehaviorProfile).filter_by(persona_id=persona.id).first()
    if existing is not None:
        existing.posting_hour_histogram = features.posting_hour_histogram
        existing.inferred_timezone = features.inferred_timezone
        existing.avg_post_length_chars = features.avg_post_length_chars
        db.flush()
        return existing

    profile = BehaviorProfile(
        persona_id=persona.id,
        posting_hour_histogram=features.posting_hour_histogram,
        inferred_timezone=features.inferred_timezone,
        avg_post_length_chars=features.avg_post_length_chars,
    )
    db.add(profile)
    db.flush()
    return profile


@dataclass
class BehaviorStats:
    profiles_built: int = 0
    personas_skipped_no_observations: int = 0


def build_all_behavior_profiles(db: Session) -> BehaviorStats:
    stats = BehaviorStats()
    for persona in db.query(Persona).all():
        profile = build_behavior_profile(db, persona)
        if profile is None:
            stats.personas_skipped_no_observations += 1
        else:
            stats.profiles_built += 1
    return stats
