"""
services/graph.py
==================

Phase 4 — Relationship graph.

Builds and queries the cross-entity relationship graph from the confidence-
scored links produced upstream by:
  - Phase 2: services/entity_resolution.py, services/scoring.py
  - Phase 3: services/stylometry.py, services/behavior.py

This module does NOT compute confidence scores itself — it only assembles
and queries a graph out of scores/reason codes that already exist. That
keeps "is this evidence-backed?" logic in one place (Phase 2/3) instead of
duplicating it here.

INTERFACE NOTE — please read before wiring this into the rest of the app
--------------------------------------------------------------------------
I don't have your actual Phase 0 models.py/schemas.py, or the real output
shapes of entity_resolution.py / scoring.py / stylometry.py / behavior.py,
so this module defines its own small `EntityRecord` / `LinkRecord`
dataclasses as the expected input contract (field names matching what the
plan doc implies: a numeric confidence score, reason codes, the
Low/Moderate/High/Unresolved enum, etc).

Two ways to reconcile once you share the real code:
  1. If your real objects already look like this (same field names),
     you're done — just import EntityRecord/LinkRecord's real equivalents
     instead of these.
  2. Otherwise, adapt `load_graph_from_records()` at the bottom — the ONE
     place raw dicts/ORM rows get converted into EntityRecord/LinkRecord.
     Nothing else in this file needs to change.

Design choices worth flagging for your review
--------------------------------------------------------------------------
- Undirected multigraph (`networkx.MultiGraph`). Every link type described
  in the plan (shared PGP key, stylometric similarity, behavioral pattern
  match) is a symmetric "these two might be the same actor" signal, not a
  directed social relationship (e.g. "replied to"). MultiGraph lets two
  entities keep *both* an entity-resolution edge and a stylometry edge
  between them instead of collapsing them, so no evidence gets lost. If a
  later phase produces genuinely directional edges, this will need to
  become a MultiDiGraph — flagging now since that's a bigger refactor
  later than earlier.
- Ground truth never enters this module. The plan doc is explicit that
  ground-truth mappings must stay out of anything the investigator
  dashboard reads from — this module only ever sees the same
  confidence-scored links the dashboard sees.
- `describe_link()` deliberately avoids "confirmed" / "proven" / "same
  person" language, in the spirit of the report-wording risk flagged
  earlier — so it's safe to reuse this phrasing directly in Phase 8's
  report templates rather than re-deriving it there.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional

import networkx as nx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------
# TODO(reconcile): the plan doc says this enum should be defined once in
# config.py/models.py and used everywhere (entity resolution, graph edge
# coloring, UI badges, PDF wording). It's redefined here ONLY so this file
# runs standalone. Delete this and import the real one
# (e.g. `from ..config import ConfidenceLevel`) once you share Phase 0.
class ConfidenceLevel(str, Enum):
    UNRESOLVED = "Unresolved"
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"


# Used to filter/sort by confidence (Unresolved sorts lowest — filtering to
# "at least Low" excludes it, which is what you want for a "usable links
# only" view; querying Unresolved links explicitly is still possible via
# min_confidence=0.0 on the raw score).
_LEVEL_RANK: dict[ConfidenceLevel, int] = {
    ConfidenceLevel.UNRESOLVED: 0,
    ConfidenceLevel.LOW: 1,
    ConfidenceLevel.MODERATE: 2,
    ConfidenceLevel.HIGH: 3,
}

# Graph edge coloring / UI badges, per the plan doc's "confidence enum used
# everywhere" note.
CONFIDENCE_COLORS: dict[ConfidenceLevel, str] = {
    ConfidenceLevel.HIGH: "#1a7f37",  # green
    ConfidenceLevel.MODERATE: "#9a6700",  # amber
    ConfidenceLevel.LOW: "#cf222e",  # red
    ConfidenceLevel.UNRESOLVED: "#6e7781",  # grey
}


def score_to_level(score: Optional[float]) -> ConfidenceLevel:
    """
    Map a numeric confidence score to the enum. Placeholder cut points —
    replace with Phase 2's actual thresholds from config.py once shared, so
    the graph and the scorer never disagree about what "High" means.
    """
    if score is None:
        return ConfidenceLevel.UNRESOLVED
    if score >= 0.85:
        return ConfidenceLevel.HIGH
    if score >= 0.60:
        return ConfidenceLevel.MODERATE
    if score >= 0.0:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.UNRESOLVED


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------
@dataclass
class EntityRecord:
    """One resolved entity/persona node. Adapt to your real Entity/Persona model."""

    entity_id: str
    display_name: str
    entity_type: str = "persona"  # e.g. "persona", "identifier", "wallet"
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    source_platforms: list[str] = field(default_factory=list)


@dataclass
class LinkRecord:
    """One confidence-scored link between two entities, from Phase 2 or 3."""

    source_entity_id: str
    target_entity_id: str
    confidence_score: float  # 0.0-1.0, from scoring.py
    reason_codes: list[str]  # e.g. ["exact_pgp_match"]
    method: str  # "entity_resolution" | "stylometry" | "behavior"
    evidence_refs: list[str] = field(default_factory=list)  # observation/post ids
    observed_at: Optional[datetime] = None  # timestamp of the underlying evidence
    confidence_level: Optional[ConfidenceLevel] = None

    def __post_init__(self) -> None:
        if self.confidence_level is None:
            self.confidence_level = score_to_level(self.confidence_score)


# ---------------------------------------------------------------------------
# Graph service
# ---------------------------------------------------------------------------
class GraphService:
    """
    Wraps a networkx.MultiGraph of entities and their scored links, plus the
    query operations the dashboard (Phase 7) and reporting (Phase 8) need.
    """

    def __init__(self) -> None:
        self.graph: nx.MultiGraph = nx.MultiGraph()

    # -- building -----------------------------------------------------------
    def add_entity(self, entity: EntityRecord) -> None:
        self.graph.add_node(
            entity.entity_id,
            display_name=entity.display_name,
            entity_type=entity.entity_type,
            first_seen=entity.first_seen,
            last_seen=entity.last_seen,
            source_platforms=list(entity.source_platforms),
        )

    def add_link(self, link: LinkRecord) -> None:
        for eid in (link.source_entity_id, link.target_entity_id):
            if eid not in self.graph:
                logger.warning("Link references unknown entity %r; adding stub node", eid)
                self.graph.add_node(eid, display_name=eid, entity_type="unknown")

        self.graph.add_edge(
            link.source_entity_id,
            link.target_entity_id,
            confidence_score=link.confidence_score,
            confidence_level=link.confidence_level.value,
            reason_codes=list(link.reason_codes),
            method=link.method,
            evidence_refs=list(link.evidence_refs),
            observed_at=link.observed_at,
            color=CONFIDENCE_COLORS[link.confidence_level],
        )

    @classmethod
    def build(cls, entities: Iterable[EntityRecord], links: Iterable[LinkRecord]) -> "GraphService":
        svc = cls()
        for e in entities:
            svc.add_entity(e)
        for l in links:
            svc.add_link(l)
        return svc

    # -- queries --------------------------------------------------------------
    def neighbors(self, entity_id: str, min_confidence: float = 0.0) -> list[dict]:
        """
        All entities linked to `entity_id`, richest evidence first. If two
        entities are linked by more than one independent signal (e.g. a PGP
        match AND a stylometry match), each appears as its own row rather
        than being merged into one blended score.
        """
        if entity_id not in self.graph:
            return []
        out = []
        for _, neighbor_id, data in self.graph.edges(entity_id, data=True):
            if data["confidence_score"] < min_confidence:
                continue
            out.append(
                {
                    "entity_id": neighbor_id,
                    "display_name": self.graph.nodes[neighbor_id].get("display_name", neighbor_id),
                    "confidence_score": data["confidence_score"],
                    "confidence_level": data["confidence_level"],
                    "reason_codes": data["reason_codes"],
                    "method": data["method"],
                }
            )
        return sorted(out, key=lambda x: x["confidence_score"], reverse=True)

    def ego_network(self, entity_id: str, depth: int = 1, min_confidence: float = 0.0) -> "GraphService":
        """Subgraph of everything within `depth` hops of `entity_id`."""
        if entity_id not in self.graph:
            return GraphService()
        filtered = self._filtered_graph(min_confidence)
        svc = GraphService()
        svc.graph = nx.ego_graph(filtered, entity_id, radius=depth).copy()
        return svc

    def clusters(self, min_confidence: float = 0.0) -> list[set[str]]:
        """
        Connected components at or above `min_confidence` — each is a group
        of entities that plausibly represent the same underlying actor.
        """
        filtered = self._filtered_graph(min_confidence)
        return [set(c) for c in nx.connected_components(filtered)]

    def path_between(self, entity_a: str, entity_b: str) -> Optional[list[dict]]:
        """
        The strongest-evidence path connecting two entities, if any —
        weighted so the path prefers higher-confidence edges. Useful for an
        "explain the connection" view: each hop names its own evidence
        instead of asserting one blended verdict across the whole path.
        """
        if entity_a not in self.graph or entity_b not in self.graph:
            return None

        # Collapse to a simple weighted graph for pathfinding, keeping only
        # the strongest (lowest-weight) edge per pair — full multi-edge
        # detail isn't needed here, just "what's the best route".
        weighted = nx.Graph()
        weighted.add_nodes_from(self.graph.nodes)
        for u, v, data in self.graph.edges(data=True):
            w = 1.0 - data["confidence_score"]
            if weighted.has_edge(u, v):
                if w < weighted[u][v]["weight"]:
                    weighted[u][v].update(weight=w, **data)
            else:
                weighted.add_edge(u, v, weight=w, **data)

        try:
            path_nodes = nx.shortest_path(weighted, entity_a, entity_b, weight="weight")
        except nx.NetworkXNoPath:
            return None

        hops = []
        for u, v in zip(path_nodes, path_nodes[1:]):
            edge_data = weighted[u][v]
            hops.append(
                {
                    "from": u,
                    "to": v,
                    "confidence_score": edge_data["confidence_score"],
                    "confidence_level": edge_data["confidence_level"],
                    "reason_codes": edge_data["reason_codes"],
                }
            )
        return hops

    def alias_chains(
        self,
        reason_code_prefixes: tuple[str, ...] = ("exact_pgp_match", "shared_identifier", "shared_crypto_address"),
        min_confidence: float = 0.0,
    ) -> list[list[dict]]:
        """
        Groups of entities plausibly representing one actor rebranding over
        time (the "same PGP key, new vendor name" pattern from the spec) —
        entities connected only via strong-identifier reason codes, ordered
        by first_seen so the chain reads chronologically. Deliberately
        excludes stylometry-only links: identifier reuse is a much stronger
        rebrand signal than writing-style similarity, and mixing them in
        here would blur exactly the distinction the spec wants preserved.
        """
        strong = nx.Graph()
        strong.add_nodes_from(self.graph.nodes(data=True))
        for u, v, data in self.graph.edges(data=True):
            if data["confidence_score"] < min_confidence:
                continue
            if any(rc.startswith(reason_code_prefixes) for rc in data["reason_codes"]):
                strong.add_edge(u, v, **data)

        chains = []
        for component in nx.connected_components(strong):
            if len(component) < 2:
                continue
            entities = sorted(
                (
                    {
                        "entity_id": n,
                        "display_name": strong.nodes[n].get("display_name", n),
                        "first_seen": strong.nodes[n].get("first_seen"),
                        "last_seen": strong.nodes[n].get("last_seen"),
                    }
                    for n in component
                ),
                key=lambda x: x["first_seen"] or datetime.max,
            )
            chains.append(entities)
        return chains

    def describe_link(self, entity_a: str, entity_b: str) -> str:
        """
        Human-readable, non-overclaiming summary of the link(s) between two
        entities — deliberately avoids "confirmed" / "proven" / "same
        person" per the report-wording risk called out earlier.
        """
        if not self.graph.has_edge(entity_a, entity_b):
            return f"No linking evidence found between {entity_a} and {entity_b}."
        parts = []
        for data in self.graph.get_edge_data(entity_a, entity_b).values():
            reasons = ", ".join(data["reason_codes"])
            parts.append(f"{data['confidence_level']} confidence ({data['method']}: {reasons})")
        return f"{entity_a} is linked to {entity_b} — " + "; ".join(parts) + "."

    def to_visualization_payload(self) -> dict:
        """
        JSON-serializable {"nodes": [...], "edges": [...]} for the Phase 7
        dashboard's graph view — plain dicts so it doesn't matter whether
        that page ends up using vis.js, cytoscape.js, or something else.
        """
        return _json_safe(nx.node_link_data(self.graph))

    # -- internals ------------------------------------------------------------
    def _filtered_graph(self, min_confidence: float) -> nx.MultiGraph:
        if min_confidence <= 0.0:
            return self.graph
        g = nx.MultiGraph()
        g.add_nodes_from(self.graph.nodes(data=True))
        for u, v, data in self.graph.edges(data=True):
            if data["confidence_score"] >= min_confidence:
                g.add_edge(u, v, **data)
        return g


def _json_safe(obj):
    """Recursively convert datetimes/enums into JSON-friendly values."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    return obj


# ---------------------------------------------------------------------------
# Adapter — wire this up once Phase 0/2/3's real shapes are shared
# ---------------------------------------------------------------------------
def load_graph_from_records(entity_rows: list[dict], link_rows: list[dict]) -> GraphService:
    """
    Build a GraphService from plain dicts (e.g. ORM rows via `.__dict__`, or
    Pydantic `.model_dump()`). This is the ONE place to edit once you share
    the real models.py / scoring.py field names — everything else in this
    file works against EntityRecord/LinkRecord regardless of where they
    came from.
    """
    entities = [
        EntityRecord(
            entity_id=row["entity_id"],
            display_name=row.get("display_name", row["entity_id"]),
            entity_type=row.get("entity_type", "persona"),
            first_seen=row.get("first_seen"),
            last_seen=row.get("last_seen"),
            source_platforms=row.get("source_platforms", []),
        )
        for row in entity_rows
    ]
    links = [
        LinkRecord(
            source_entity_id=row["source_entity_id"],
            target_entity_id=row["target_entity_id"],
            confidence_score=row["confidence_score"],
            reason_codes=row.get("reason_codes", []),
            method=row.get("method", "unknown"),
            evidence_refs=row.get("evidence_refs", []),
            observed_at=row.get("observed_at"),
        )
        for row in link_rows
    ]
    return GraphService.build(entities, links)


# ---------------------------------------------------------------------------
# Demo — run `python3 services/graph.py` to sanity-check before Phase 0/2/3
# are wired in. Exercises two of the plan's required demo-dataset
# properties: a rebrand-via-shared-PGP chain, and a low-confidence
# stylometry false positive that should NOT show up as a cluster.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from datetime import timedelta

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    now = datetime(2026, 1, 1)

    entities = [
        EntityRecord("vendor_alpha", "vendor_alpha", first_seen=now, last_seen=now + timedelta(days=60)),
        EntityRecord(
            "vendor_beta", "vendor_beta", first_seen=now + timedelta(days=65), last_seen=now + timedelta(days=140)
        ),
        EntityRecord("vendor_gamma", "vendor_gamma", first_seen=now, last_seen=now + timedelta(days=200)),
        EntityRecord("unrelated_dave", "unrelated_dave"),  # no first_seen on purpose, tests the sort-key edge case
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

    svc = GraphService.build(entities, links)

    print("Neighbors of vendor_alpha:")
    for n in svc.neighbors("vendor_alpha"):
        print(" ", n)

    print("\nClusters at min_confidence=0.6 (false positive should be excluded):")
    for c in svc.clusters(min_confidence=0.6):
        print(" ", c)

    print("\nAlias/rebrand chains (identifier-based only):")
    for chain in svc.alias_chains():
        print(" ", [e["entity_id"] for e in chain])

    print("\nPath explanation, vendor_alpha -> vendor_gamma:")
    for hop in svc.path_between("vendor_alpha", "vendor_gamma") or []:
        print(" ", hop)

    print("\ndescribe_link(vendor_alpha, vendor_beta):")
    print(" ", svc.describe_link("vendor_alpha", "vendor_beta"))

    print("\nVisualization payload (truncated):")
    payload = svc.to_visualization_payload()
    print(" ", json.dumps(payload, indent=2)[:400], "...")
