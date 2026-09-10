"""
services/search.py
===================

Phase 5 — Search & timeline.

A read-layer over what earlier phases already produced:
  - Phase 1 (collectors/normalization/extraction): the observation corpus —
    one row per post/message, normalized and tagged with the entity/persona
    it was attributed to at ingestion time.
  - Phase 4 (services/graph.py): the confidence-scored relationship graph,
    via GraphService.

This module doesn't resolve entities, score links, or compute anything new.
It only searches and orders evidence Phases 1-4 already produced — same
reasoning as Phase 4's own docstring: keeps "is this evidence-backed?"
logic living in exactly one place instead of a second, possibly-drifting
copy showing up here.

INTERFACE NOTE — please read before wiring this into the rest of the app
--------------------------------------------------------------------------
Still don't have your real Phase 0 models.py or Phase 1's normalization.py
output shape, so — same approach as Phase 4 — this defines its own
`ObservationRecord` dataclass as the expected input contract for the text
corpus. `load_search_index_from_records()` at the bottom is the one place
to edit once you share the real shape; nothing else here needs to change.

Unlike EntityRecord/LinkRecord, though, this file does NOT redefine any
confidence-related type. GraphService (imported directly from Phase 4,
which is now real code, not a placeholder) already owns every confidence
decision this module needs — which entities are "close enough" to expand a
timeline into (`clusters()`), and what the connecting evidence chain looks
like (`path_between()`). This file only ever touches `min_confidence` as a
plain float threshold, so it can never quietly disagree with Phase 4 about
what "High" means.

Design choices worth flagging for your review
--------------------------------------------------------------------------
- Content search is plain case-insensitive term counting, not a real search
  engine — fine for a synthetic demo corpus, not what you'd run against
  real ingestion volume. `_score_text_match()` is the one function to swap
  for Postgres full-text search / Whoosh / Elasticsearch later; everything
  else here is agnostic to how the scoring works internally.
- `timeline()` never silently blends personas together. With no
  `expand_min_confidence` you get exactly one entity's own observations —
  full stop. Pass a threshold and it reuses Phase 4's `clusters()` (the
  same transitive-closure logic the graph view already exercises, not a
  second reimplementation of it) to decide which *other* personas are
  evidence-backed enough to fold in — and every non-root row still carries
  its own `linked_via` hop-by-hop chain from `path_between()`, rather than
  one blended "same person" assertion. On Phase 4's demo dataset, a
  timeline built at min_confidence=0.6 pulls vendor_beta AND (transitively,
  via beta) vendor_gamma into vendor_alpha's timeline, while the
  false-positive vendor_alpha<->unrelated_dave link (0.30) stays excluded —
  the same distinction `clusters()` demonstrates in Phase 4, carried
  through here instead of silently re-blurring at this layer.
- `search()` returns entities and observations as two separate lists rather
  than one merged/ranked list. A persona match and a post match aren't
  comparable "relevance" units, and collapsing them into one ranking would
  hide that from whoever builds Phase 7's search page on top of this.
- No ground truth, no live network calls, nothing beyond read/filter/sort
  of data the caller hands in — same DEMO_MODE-friendly posture as Phase 4.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Optional

try:  # normal case: this file lives alongside graph.py in services/
    from .graph import GraphService
except ImportError:  # running this file directly, e.g. `python3 search.py`
    from graph import GraphService  # type: ignore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------
# TODO(reconcile): replace with the real Phase 1 observation shape once
# shared — load_search_index_from_records() below is the one place to edit.
@dataclass
class ObservationRecord:
    """One normalized post/message, as produced by Phase 1."""

    observation_id: str
    entity_id: str  # persona this was attributed to at ingestion time
    platform: str
    content: str
    observed_at: datetime
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Search service
# ---------------------------------------------------------------------------
class SearchService:
    """
    Search and timeline queries over an observation corpus, optionally
    joined against a Phase 4 GraphService for confidence-aware timeline
    expansion across linked personas.
    """

    def __init__(
        self,
        observations: Iterable[ObservationRecord],
        graph: Optional[GraphService] = None,
    ) -> None:
        self.observations: list[ObservationRecord] = list(observations)
        self.graph_service: GraphService = graph if graph is not None else GraphService()
        self._by_entity: dict[str, list[ObservationRecord]] = defaultdict(list)
        for obs in self.observations:
            self._by_entity[obs.entity_id].append(obs)

    # -- entity/persona search ------------------------------------------------
    def search_entities(self, query: str, *, limit: int = 50) -> list[dict]:
        """
        Match personas/entities by display name, entity id, entity type, or
        source platform. Plain substring match — this is a lookup over at
        most a few hundred nodes, not a corpus that needs relevance ranking.
        """
        q = query.strip().lower()
        if not q:
            return []
        results = []
        for node_id, data in self.graph_service.graph.nodes(data=True):
            haystacks = [
                node_id,
                data.get("display_name", ""),
                data.get("entity_type", ""),
                *data.get("source_platforms", []),
            ]
            if any(q in str(h).lower() for h in haystacks):
                results.append(
                    {
                        "entity_id": node_id,
                        "display_name": data.get("display_name", node_id),
                        "entity_type": data.get("entity_type"),
                        "source_platforms": list(data.get("source_platforms", [])),
                        "first_seen": data.get("first_seen"),
                        "last_seen": data.get("last_seen"),
                    }
                )
        results.sort(key=lambda r: r["last_seen"] or datetime.min, reverse=True)
        return results[:limit]

    # -- content search ---------------------------------------------------
    def search_content(
        self,
        query: str,
        *,
        entity_id: Optional[str] = None,
        platform: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Keyword search over observation content (and tags). Scored by
        term-occurrence count — see the module note on why this isn't a
        real search engine — ties broken by recency.
        """
        terms = [t for t in query.strip().lower().split() if t]
        if not terms:
            return []

        candidates = self._by_entity.get(entity_id, []) if entity_id is not None else self.observations

        out = []
        for obs in candidates:
            if platform is not None and obs.platform != platform:
                continue
            if start is not None and obs.observed_at < start:
                continue
            if end is not None and obs.observed_at > end:
                continue
            score = _score_text_match(obs.content, terms) + _score_text_match(" ".join(obs.tags), terms)
            if score == 0:
                continue
            out.append(
                {
                    "observation_id": obs.observation_id,
                    "entity_id": obs.entity_id,
                    "display_name": self._display_name(obs.entity_id),
                    "platform": obs.platform,
                    "observed_at": obs.observed_at,
                    "snippet": _snippet(obs.content, terms),
                    "match_score": score,
                    "tags": list(obs.tags),
                }
            )
        out.sort(key=lambda r: (r["match_score"], r["observed_at"]), reverse=True)
        return out[:limit]

    def search(self, query: str, *, limit: int = 20) -> dict:
        """Convenience wrapper for a single search box: entities + content."""
        return {
            "entities": self.search_entities(query, limit=limit),
            "observations": self.search_content(query, limit=limit),
        }

    # -- timeline -----------------------------------------------------------
    def timeline(
        self,
        entity_id: str,
        *,
        expand_min_confidence: Optional[float] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[dict]:
        """
        Chronological observations for `entity_id`.

        `expand_min_confidence=None` (default): only entity_id's own
        observations, no cross-persona blending at all.

        With a threshold set: also includes observations from any other
        persona in entity_id's confidence-`>=` cluster (Phase 4's
        `clusters()`), each tagged with `is_root=False` and its own
        `linked_via` hop-by-hop chain from `path_between()` — never a
        single blended verdict. An entity with no qualifying links at that
        threshold just falls back to its own observations; expansion never
        errors, it just has nothing to add.
        """
        include_ids = {entity_id}
        if expand_min_confidence is not None:
            for cluster in self.graph_service.clusters(min_confidence=expand_min_confidence):
                if entity_id in cluster:
                    include_ids = cluster
                    break

        rows = []
        for eid in include_ids:
            for obs in self._by_entity.get(eid, []):
                if start is not None and obs.observed_at < start:
                    continue
                if end is not None and obs.observed_at > end:
                    continue
                is_root = eid == entity_id
                rows.append(
                    {
                        "observation_id": obs.observation_id,
                        "entity_id": eid,
                        "display_name": self._display_name(eid),
                        "platform": obs.platform,
                        "content": obs.content,
                        "observed_at": obs.observed_at,
                        "is_root": is_root,
                        "linked_via": None if is_root else self.graph_service.path_between(entity_id, eid),
                    }
                )
        rows.sort(key=lambda r: r["observed_at"])
        return rows

    def global_timeline(
        self,
        *,
        entity_ids: Optional[set[str]] = None,
        platform: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 200,
    ) -> list[dict]:
        """
        Investigation-wide timeline (e.g. Phase 7's activity feed) — no
        notion of a "root" entity; every row is reported under whichever
        persona it was actually observed as. `entity_ids` lets a caller
        restrict this to one already-chosen cluster instead of everything.
        """
        rows = []
        for obs in self.observations:
            if entity_ids is not None and obs.entity_id not in entity_ids:
                continue
            if platform is not None and obs.platform != platform:
                continue
            if start is not None and obs.observed_at < start:
                continue
            if end is not None and obs.observed_at > end:
                continue
            rows.append(
                {
                    "observation_id": obs.observation_id,
                    "entity_id": obs.entity_id,
                    "display_name": self._display_name(obs.entity_id),
                    "platform": obs.platform,
                    "content": obs.content,
                    "observed_at": obs.observed_at,
                }
            )
        rows.sort(key=lambda r: r["observed_at"], reverse=True)
        return rows[:limit]

    # -- internals ------------------------------------------------------------
    def _display_name(self, entity_id: str) -> str:
        if entity_id in self.graph_service.graph:
            return self.graph_service.graph.nodes[entity_id].get("display_name", entity_id)
        return entity_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _score_text_match(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(term) for term in terms)


def _snippet(text: str, terms: list[str], *, radius: int = 40) -> str:
    """Context window around the first matching term, for a result preview."""
    lowered = text.lower()
    for term in terms:
        idx = lowered.find(term)
        if idx != -1:
            start = max(0, idx - radius)
            end = min(len(text), idx + len(term) + radius)
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(text) else ""
            return f"{prefix}{text[start:end]}{suffix}"
    return text[: radius * 2]


# ---------------------------------------------------------------------------
# Adapter — wire this up once Phase 0/1's real shapes are shared
# ---------------------------------------------------------------------------
def load_search_index_from_records(
    observation_rows: list[dict],
    graph: Optional[GraphService] = None,
) -> SearchService:
    """
    Build a SearchService from plain dicts (ORM rows / Pydantic dumps). The
    one place to edit once you share Phase 1's real field names.
    """
    observations = [
        ObservationRecord(
            observation_id=row["observation_id"],
            entity_id=row["entity_id"],
            platform=row.get("platform", "unknown"),
            content=row.get("content", ""),
            observed_at=row["observed_at"],
            tags=row.get("tags", []),
        )
        for row in observation_rows
    ]
    return SearchService(observations, graph=graph)


# ---------------------------------------------------------------------------
# Demo — reuses Phase 4's exact vendor_alpha/beta/gamma/dave dataset (same
# entity ids and obs_* evidence refs) so the two phases stay checkable
# against each other, plus two extra posts so timeline/search have more
# than one row per persona to work with. Run via `python -m services.search`
# from the project root (needs graph.py alongside this file).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta

    try:
        from .graph import EntityRecord, LinkRecord
    except ImportError:
        from graph import EntityRecord, LinkRecord  # type: ignore

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    now = datetime(2026, 1, 1)

    entities = [
        EntityRecord("vendor_alpha", "vendor_alpha", first_seen=now, last_seen=now + timedelta(days=60)),
        EntityRecord(
            "vendor_beta", "vendor_beta", first_seen=now + timedelta(days=65), last_seen=now + timedelta(days=140)
        ),
        EntityRecord("vendor_gamma", "vendor_gamma", first_seen=now, last_seen=now + timedelta(days=200)),
        EntityRecord("unrelated_dave", "unrelated_dave"),
    ]
    links = [
        # Same PGP key reused after vendor_alpha was banned -> rebrand as vendor_beta.
        LinkRecord(
            "vendor_alpha",
            "vendor_beta",
            confidence_score=0.95,
            reason_codes=["exact_pgp_match"],
            method="entity_resolution",
            evidence_refs=["obs_101", "obs_204"],
            observed_at=now + timedelta(days=65),
        ),
        # Moderate stylometric similarity between beta and gamma.
        LinkRecord(
            "vendor_beta",
            "vendor_gamma",
            confidence_score=0.62,
            reason_codes=["stylometric_similarity"],
            method="stylometry",
            evidence_refs=["obs_310"],
            observed_at=now + timedelta(days=90),
        ),
        # Weak/false-positive stylometry hit that shouldn't read as a cluster.
        LinkRecord(
            "vendor_alpha",
            "unrelated_dave",
            confidence_score=0.30,
            reason_codes=["stylometric_similarity"],
            method="stylometry",
            evidence_refs=["obs_150"],
            observed_at=now + timedelta(days=10),
        ),
    ]
    graph = GraphService.build(entities, links)

    observations = [
        ObservationRecord(
            "obs_101", "vendor_alpha", "forum_a",
            "Selling batch 1, PGP key attached for escrow.", now,
        ),
        ObservationRecord(
            "obs_150", "unrelated_dave", "forum_a",
            "Anyone know a reliable vendor for batch orders?", now + timedelta(days=10),
        ),
        ObservationRecord(
            "obs_204", "vendor_beta", "forum_b",
            "New shop, same PGP key as before, batch pricing unchanged.", now + timedelta(days=65),
        ),
        ObservationRecord(
            "obs_250", "vendor_beta", "forum_b",
            "Restocked, escrow only, no direct deals.", now + timedelta(days=80),
        ),
        ObservationRecord(
            "obs_310", "vendor_gamma", "forum_c",
            "Batch pricing update, escrow required as always.", now + timedelta(days=90),
        ),
    ]
    svc = SearchService(observations, graph=graph)

    print("search_entities('vendor'):")
    for e in svc.search_entities("vendor"):
        print(" ", e["entity_id"])

    print("\nsearch_content('escrow'):")
    for r in svc.search_content("escrow"):
        print(" ", r["entity_id"], "-", r["snippet"])

    print("\ntimeline('vendor_alpha') — no expansion:")
    for row in svc.timeline("vendor_alpha"):
        print(" ", row["observed_at"].date(), row["entity_id"], "root" if row["is_root"] else "SHOULD NOT APPEAR")

    print("\ntimeline('vendor_alpha', expand_min_confidence=0.6):")
    print("  (expect vendor_beta + vendor_gamma folded in transitively; unrelated_dave excluded)")
    for row in svc.timeline("vendor_alpha", expand_min_confidence=0.6):
        if row["is_root"]:
            tag = "root"
        else:
            last_hop = row["linked_via"][-1]
            tag = f"linked, {last_hop['confidence_level']} confidence (last hop: {last_hop['reason_codes']})"
        print(" ", row["observed_at"].date(), row["entity_id"], f"[{tag}]")

    print("\nglobal_timeline(platform='forum_b'):")
    for row in svc.global_timeline(platform="forum_b"):
        print(" ", row["observed_at"].date(), row["entity_id"])
