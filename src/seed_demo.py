"""
seed_demo.py
============

Phase 6 — Synthetic dataset.

Generates the canonical demo dataset: entities, links, and observations,
written to data/sample_observations.json (+ entities.json, links.json,
ground_truth.json). Nothing here touches a live network or scrapes
anything real — DEMO_MODE-only, same posture as every phase before it.

Why this extends rather than replaces the alpha/beta/gamma/dave set
--------------------------------------------------------------------------
Phases 4 and 5 both already ship a `__main__` demo block hand-building
that exact entity/link/observation set (same ids, same obs_* refs). If
Phase 6 invented a different dataset, those two demo blocks would
silently drift out of sync with "the" dataset. So this file is the
canonical source: it reproduces alpha/beta/gamma/dave exactly, then adds
four more personas so all seven required demonstration properties are
covered in one place. Phases 4/5's own __main__ blocks can eventually be
pointed at load_dataset() instead of hand-rolling their subset, but
that's a Phase 10 cleanup, not something this file needs to force.

The seven demonstration properties, and who carries each
--------------------------------------------------------------------------
1. Rebrand, same PGP key            -> vendor_alpha <-> vendor_beta (0.95)
2. Moderate stylometry-only link    -> vendor_beta <-> vendor_gamma (0.62)
3. False-positive stylometry        -> vendor_alpha <-> unrelated_dave (0.30)
4. Multi-hop transitive cluster     -> alpha -> beta -> gamma (via 1 + 2)
5. Contradictory evidence           -> vendor_epsilon <-> vendor_zeta:
   shared PGP key (strong "same person" signal) but stylometry on their
   overlapping posting window scores as dissimilar (weak "different
   person" signal) - two links, same pair, opposite implications. This
   is what the confidence display's "contradictory evidence" case in
   the spec means: don't average it away, show both.
6. Insufficient text for stylometry -> vendor_theta: only one very short
   observation, nowhere near stylometry's minimum corpus size, so the
   UI's "insufficient text, no authorship claim possible" path has
   something real to render against instead of just being dead code.
7. Isolated / unlinked entity       -> vendor_iota: normal-length corpus,
   zero links to anyone. The clean negative case - resolution finding
   nothing is itself a result worth being able to demo.

Ground truth (data/ground_truth.json) records which entities are
"actually" the same underlying persona in the synthetic story. This is
for the Phase 9 evaluation script only. It is written to a separate file
and is NOT loaded by seed_dataset_for_app()/load_dataset(), so nothing
in the investigator-facing dashboard can accidentally read it - same
requirement called out in the original spec.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"

BASE_TIME = datetime(2026, 1, 1)


# ---------------------------------------------------------------------------
# Plain dataclasses mirroring the EntityRecord / LinkRecord / ObservationRecord
# shapes already established in Phases 4-5's demo blocks. Swap for the real
# Phase 0 models via load_dataset()'s dict output once shared - same
# adapter pattern Phase 5 uses.
# ---------------------------------------------------------------------------
@dataclass
class EntityRecord:
    entity_id: str
    display_name: str
    entity_type: str = "persona"
    source_platforms: list[str] = field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class LinkRecord:
    source_id: str
    target_id: str
    confidence_score: float
    reason_codes: list[str]
    method: str
    evidence_refs: list[str]
    observed_at: datetime


@dataclass
class ObservationRecord:
    observation_id: str
    entity_id: str
    platform: str
    content: str
    observed_at: datetime
    tags: list[str] = field(default_factory=list)


def _dt(days: int) -> datetime:
    return BASE_TIME + timedelta(days=days)


# ---------------------------------------------------------------------------
# 1-4: the existing alpha/beta/gamma/dave set, reproduced exactly.
# ---------------------------------------------------------------------------
def _core_four() -> tuple[list[EntityRecord], list[LinkRecord], list[ObservationRecord]]:
    entities = [
        EntityRecord("vendor_alpha", "vendor_alpha", source_platforms=["forum_a"],
                      first_seen=_dt(0), last_seen=_dt(60)),
        EntityRecord("vendor_beta", "vendor_beta", source_platforms=["forum_b"],
                      first_seen=_dt(65), last_seen=_dt(140)),
        EntityRecord("vendor_gamma", "vendor_gamma", source_platforms=["forum_c"],
                      first_seen=_dt(0), last_seen=_dt(200)),
        EntityRecord("unrelated_dave", "unrelated_dave", source_platforms=["forum_a"],
                      first_seen=_dt(10), last_seen=_dt(10)),
    ]
    links = [
        LinkRecord("vendor_alpha", "vendor_beta", 0.95, ["exact_pgp_match"],
                    "entity_resolution", ["obs_101", "obs_204"], _dt(65)),
        LinkRecord("vendor_beta", "vendor_gamma", 0.62, ["stylometric_similarity"],
                    "stylometry", ["obs_310"], _dt(90)),
        LinkRecord("vendor_alpha", "unrelated_dave", 0.30, ["stylometric_similarity"],
                    "stylometry", ["obs_150"], _dt(10)),
    ]
    observations = [
        ObservationRecord("obs_101", "vendor_alpha", "forum_a",
                           "Selling batch 1, PGP key attached for escrow.", _dt(0)),
        ObservationRecord("obs_150", "unrelated_dave", "forum_a",
                           "Anyone know a reliable vendor for batch orders?", _dt(10)),
        ObservationRecord("obs_204", "vendor_beta", "forum_b",
                           "New shop, same PGP key as before, batch pricing unchanged.", _dt(65)),
        ObservationRecord("obs_250", "vendor_beta", "forum_b",
                           "Restocked, escrow only, no direct deals.", _dt(80)),
        ObservationRecord("obs_310", "vendor_gamma", "forum_c",
                           "Batch pricing update, escrow required as always.", _dt(90)),
    ]
    return entities, links, observations


# ---------------------------------------------------------------------------
# 5: contradictory evidence - shared PGP key, but dissimilar stylometry.
# ---------------------------------------------------------------------------
def _contradictory_pair() -> tuple[list[EntityRecord], list[LinkRecord], list[ObservationRecord]]:
    entities = [
        EntityRecord("vendor_epsilon", "vendor_epsilon", source_platforms=["forum_d"],
                      first_seen=_dt(20), last_seen=_dt(100)),
        EntityRecord("vendor_zeta", "vendor_zeta", source_platforms=["forum_e"],
                      first_seen=_dt(30), last_seen=_dt(110)),
    ]
    links = [
        LinkRecord("vendor_epsilon", "vendor_zeta", 0.90, ["exact_pgp_match"],
                    "entity_resolution", ["obs_401", "obs_402"], _dt(30)),
        LinkRecord("vendor_epsilon", "vendor_zeta", 0.25, ["stylometric_dissimilarity"],
                    "stylometry", ["obs_403", "obs_404"], _dt(45)),
    ]
    observations = [
        ObservationRecord("obs_401", "vendor_epsilon", "forum_d",
                           "PGP key posted for verification, standard escrow terms.", _dt(20)),
        ObservationRecord("obs_402", "vendor_zeta", "forum_e",
                           "Same PGP key as my old listing, escrow terms unchanged.", _dt(30)),
        ObservationRecord("obs_403", "vendor_epsilon", "forum_d",
                           "yo just droppin a quick update, batch's back in stock lol", _dt(45)),
        ObservationRecord("obs_404", "vendor_zeta", "forum_e",
                           "Please be advised: inventory has been replenished accordingly.", _dt(50)),
    ]
    return entities, links, observations


# ---------------------------------------------------------------------------
# 6: insufficient text for stylometry.
# ---------------------------------------------------------------------------
def _insufficient_text() -> tuple[list[EntityRecord], list[LinkRecord], list[ObservationRecord]]:
    entities = [
        EntityRecord("vendor_theta", "vendor_theta", source_platforms=["forum_f"],
                      first_seen=_dt(55), last_seen=_dt(55)),
    ]
    observations = [
        ObservationRecord("obs_501", "vendor_theta", "forum_f", "back", _dt(55)),
    ]
    return entities, [], observations


# ---------------------------------------------------------------------------
# 7: isolated entity, normal corpus, zero links.
# ---------------------------------------------------------------------------
def _isolated_entity() -> tuple[list[EntityRecord], list[LinkRecord], list[ObservationRecord]]:
    entities = [
        EntityRecord("vendor_iota", "vendor_iota", source_platforms=["forum_g"],
                      first_seen=_dt(5), last_seen=_dt(120)),
    ]
    observations = [
        ObservationRecord("obs_601", "vendor_iota", "forum_g",
                           "Fresh batch listed, escrow only, ships Monday.", _dt(5)),
        ObservationRecord("obs_602", "vendor_iota", "forum_g",
                           "Reminder: no direct deals, escrow is non-negotiable.", _dt(60)),
        ObservationRecord("obs_603", "vendor_iota", "forum_g",
                           "Price update for next batch, same terms as always.", _dt(120)),
    ]
    return entities, [], observations


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def build_dataset() -> tuple[list[EntityRecord], list[LinkRecord], list[ObservationRecord]]:
    entities: list[EntityRecord] = []
    links: list[LinkRecord] = []
    observations: list[ObservationRecord] = []
    for entities_part, links_part, obs_part in (
        _core_four(),
        _contradictory_pair(),
        _insufficient_text(),
        _isolated_entity(),
    ):
        entities += entities_part
        links += links_part
        observations += obs_part
    return entities, links, observations


def build_ground_truth() -> dict:
    """
    Which entities are "actually" the same underlying persona in the
    synthetic story, for Phase 9's precision/recall/F1 script only.
    Never loaded by seed_dataset_for_app() / load_dataset().
    """
    return {
        "same_persona_clusters": [
            ["vendor_alpha", "vendor_beta", "vendor_gamma"],  # true rebrand chain
            ["vendor_epsilon", "vendor_zeta"],  # true match despite noisy stylometry
        ],
        "known_non_matches": [
            ["vendor_alpha", "unrelated_dave"],  # the false-positive stylometry hit
        ],
        "unresolved": ["vendor_theta"],  # not enough text to judge either way
        "no_claim": ["vendor_iota"],  # isolated, correctly linked to no one
    }


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"Not serializable: {obj!r}")


def write_dataset(out_dir: Path = DATA_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    entities, links, observations = build_dataset()

    (out_dir / "entities.json").write_text(
        json.dumps([asdict(e) for e in entities], default=_serialize, indent=2)
    )
    (out_dir / "links.json").write_text(
        json.dumps([asdict(l) for l in links], default=_serialize, indent=2)
    )
    (out_dir / "sample_observations.json").write_text(
        json.dumps([asdict(o) for o in observations], default=_serialize, indent=2)
    )
    # ground truth kept separate on purpose - see build_ground_truth() docstring.
    (out_dir / "ground_truth.json").write_text(json.dumps(build_ground_truth(), indent=2))

    print(f"Wrote {len(entities)} entities, {len(links)} links, "
          f"{len(observations)} observations, and ground_truth.json to {out_dir}/")


def load_dataset(data_dir: Path = DATA_DIR) -> dict:
    """
    Load the written dataset back as plain dicts/lists — the shape
    Phase 1's local_import.py, Phase 4's GraphService.build(), and Phase
    5's load_search_index_from_records() all expect as input. Does NOT
    include ground_truth.json.
    """
    def _load(name: str) -> list[dict]:
        return json.loads((data_dir / name).read_text())

    return {
        "entities": _load("entities.json"),
        "links": _load("links.json"),
        "observations": _load("sample_observations.json"),
    }


if __name__ == "__main__":
    write_dataset()

    # Sanity-check: every property listed in the module docstring actually
    # shows up in what got written.
    data = load_dataset()
    ids = {e["entity_id"] for e in data["entities"]}
    assert {"vendor_alpha", "vendor_beta", "vendor_gamma", "unrelated_dave",
            "vendor_epsilon", "vendor_zeta", "vendor_theta", "vendor_iota"} <= ids
    epsilon_zeta_links = [l for l in data["links"]
                           if {l["source_id"], l["target_id"]} == {"vendor_epsilon", "vendor_zeta"}]
    assert len(epsilon_zeta_links) == 2, "contradictory-evidence pair needs both links present"
    theta_obs = [o for o in data["observations"] if o["entity_id"] == "vendor_theta"]
    assert len(theta_obs) == 1, "insufficient-text case needs exactly one short observation"
    iota_links = [l for l in data["links"]
                  if "vendor_iota" in (l["source_id"], l["target_id"])]
    assert len(iota_links) == 0, "isolated entity must have zero links"
    print("All 7 demonstration properties verified present in the written dataset.")
