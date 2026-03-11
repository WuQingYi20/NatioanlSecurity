"""
Synthetic Knowledge Graph generator for Sentinel-KG RL training.

Generates a parameterised multi-agency graph with:
  - Persons (personnummer), companies (org_nr), addresses, transactions
  - Four agency data sources
  - Embedded threat patterns (money laundering, shell companies, benefit fraud,
    VAT carousel, suspicious transactions)
  - Ambiguous-but-legitimate entities
  - Entity-resolution confidence scores on cross-agency links
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import networkx as nx
import numpy as np


# ── Enums (mirrors trustlayer_mvp but standalone) ──────────────────────────

class NodeType(str, Enum):
    PERSON = "person"
    COMPANY = "company"
    ADDRESS = "address"
    TRANSACTION = "transaction"


class EdgeType(str, Enum):
    OWNS = "owns"
    DIRECTS = "directs"
    BOARD_MEMBER = "board_member"
    EMPLOYED_BY = "employed_by"
    FILED = "filed"
    REGISTERED_AT = "registered_at"
    TRANSACTED = "transacted"
    CLAIMS_BENEFIT = "claims_benefit"
    CO_OWNER = "co_owner"


class RelCat(str, Enum):
    """Relationship category — controls semantic window visibility."""
    FINANCIAL = "financial"
    CORPORATE = "corporate"
    PERSONAL = "personal"


EDGE_TO_RELCAT: dict[EdgeType, RelCat] = {
    EdgeType.OWNS: RelCat.FINANCIAL,
    EdgeType.DIRECTS: RelCat.CORPORATE,
    EdgeType.BOARD_MEMBER: RelCat.CORPORATE,
    EdgeType.FILED: RelCat.FINANCIAL,
    EdgeType.TRANSACTED: RelCat.FINANCIAL,
    EdgeType.CO_OWNER: RelCat.FINANCIAL,
    EdgeType.EMPLOYED_BY: RelCat.PERSONAL,
    EdgeType.REGISTERED_AT: RelCat.PERSONAL,
    EdgeType.CLAIMS_BENEFIT: RelCat.PERSONAL,
}


class DataSource(str, Enum):
    SKATTEVERKET = "Skatteverket"
    FORSAKRINGSKASSAN = "Försäkringskassan"
    ARBETSFORMEDLINGEN = "Arbetsförmedlingen"
    BOLAGSVERKET = "Bolagsverket"


# ── Config ─────────────────────────────────────────────────────────────────

@dataclass
class GraphConfig:
    num_persons: int = 80
    num_companies: int = 50
    num_addresses: int = 25
    num_transactions: int = 150
    num_threat_patterns: int = 5
    num_ambiguous: int = 3
    er_noise_frac: float = 0.15       # fraction of cross-agency links with low ER confidence
    seed: int = 42


# ── Generator ──────────────────────────────────────────────────────────────

class SyntheticGraphGenerator:
    """Build a synthetic Swedish multi-agency knowledge graph."""

    def __init__(self, config: GraphConfig | None = None):
        self.cfg = config or GraphConfig()
        self.rng = np.random.default_rng(self.cfg.seed)
        self.G = nx.MultiDiGraph()
        # bookkeeping
        self._persons: list[str] = []
        self._companies: list[str] = []
        self._addresses: list[str] = []
        self._transactions: list[str] = []
        self._threat_clusters: dict[int, set[str]] = {}
        self._threat_seeds: list[str] = []

    # ── public API ─────────────────────────────────────────────────────

    def generate(self) -> nx.MultiDiGraph:
        self._add_base_entities()
        self._add_benign_edges()
        self._inject_threat_money_laundering(cluster_id=0)
        self._inject_threat_shell_network(cluster_id=1)
        self._inject_threat_benefit_fraud(cluster_id=2)
        self._inject_threat_vat_carousel(cluster_id=3)
        self._inject_threat_burst_transactions(cluster_id=4)
        self._inject_ambiguous_entities()
        self._add_er_noise()
        return self.G

    def get_threat_seed_nodes(self) -> list[str]:
        return [str(s) for s in self._threat_seeds]

    def get_all_threat_node_clusters(self) -> dict[int, set[str]]:
        return dict(self._threat_clusters)

    # ── base entities ──────────────────────────────────────────────────

    def _add_base_entities(self):
        sources = list(DataSource)
        for i in range(self.cfg.num_persons):
            nid = f"P-{i:04d}"
            self.G.add_node(nid,
                            node_type=NodeType.PERSON,
                            source=self.rng.choice(sources[:3]),
                            personnummer=f"19{self.rng.integers(50,99)}{self.rng.integers(1,13):02d}{self.rng.integers(1,29):02d}-{self.rng.integers(1000,9999)}",
                            _ground_truth="benign",
                            _threat_cluster=-1)
            self._persons.append(nid)

        for i in range(self.cfg.num_companies):
            nid = f"C-{i:04d}"
            self.G.add_node(nid,
                            node_type=NodeType.COMPANY,
                            source=DataSource.BOLAGSVERKET,
                            org_nr=f"55{self.rng.integers(1000,9999)}-{self.rng.integers(1000,9999)}",
                            _ground_truth="benign",
                            _threat_cluster=-1)
            self._companies.append(nid)

        for i in range(self.cfg.num_addresses):
            nid = f"A-{i:04d}"
            cities = ["Stockholm", "Göteborg", "Malmö", "Uppsala", "Linköping"]
            self.G.add_node(nid,
                            node_type=NodeType.ADDRESS,
                            source=DataSource.SKATTEVERKET,
                            city=self.rng.choice(cities),
                            _ground_truth="benign",
                            _threat_cluster=-1)
            self._addresses.append(nid)

        for i in range(self.cfg.num_transactions):
            nid = f"T-{i:04d}"
            amount = float(self.rng.exponential(50_000))
            self.G.add_node(nid,
                            node_type=NodeType.TRANSACTION,
                            source=DataSource.SKATTEVERKET,
                            amount=round(amount, 2),
                            _ground_truth="benign",
                            _threat_cluster=-1)
            self._transactions.append(nid)

    def _add_benign_edges(self):
        # person -> company (employed_by)
        for p in self._persons:
            if self.rng.random() < 0.6:
                c = self.rng.choice(self._companies)
                self._edge(p, c, EdgeType.EMPLOYED_BY, DataSource.ARBETSFORMEDLINGEN)

        # person -> address (registered_at)
        for p in self._persons:
            a = self.rng.choice(self._addresses)
            self._edge(p, a, EdgeType.REGISTERED_AT, DataSource.SKATTEVERKET)

        # company -> address (registered_at)
        for c in self._companies:
            a = self.rng.choice(self._addresses)
            self._edge(c, a, EdgeType.REGISTERED_AT, DataSource.BOLAGSVERKET)

        # some persons direct companies
        directors = self.rng.choice(self._persons, size=min(30, len(self._persons)), replace=False)
        for d in directors:
            c = self.rng.choice(self._companies)
            self._edge(d, c, EdgeType.DIRECTS, DataSource.BOLAGSVERKET)

        # transactions between companies
        for t in self._transactions:
            src = self.rng.choice(self._companies)
            dst = self.rng.choice(self._companies)
            if src != dst:
                self._edge(src, t, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)
                self._edge(t, dst, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)

        # some persons claim benefits
        claimants = self.rng.choice(self._persons, size=min(20, len(self._persons)), replace=False)
        for p in claimants:
            self._edge(p, p, EdgeType.CLAIMS_BENEFIT, DataSource.FORSAKRINGSKASSAN)

    # ── threat patterns ────────────────────────────────────────────────

    def _inject_threat_money_laundering(self, cluster_id: int):
        """Chain: PersonA -> CompanyX -> Tx1 -> CompanyY -> Tx2 -> CompanyZ, shared address."""
        nodes = []
        pa = self._mark_threat(self.rng.choice(self._persons), cluster_id)
        nodes.append(pa)

        prev_company = None
        shared_addr = self._mark_threat(self.rng.choice(self._addresses), cluster_id)
        nodes.append(shared_addr)

        for step in range(3):
            co = self._new_threat_company(cluster_id)
            nodes.append(co)
            self._edge(co, shared_addr, EdgeType.REGISTERED_AT, DataSource.BOLAGSVERKET)

            if step == 0:
                self._edge(pa, co, EdgeType.DIRECTS, DataSource.BOLAGSVERKET)
            else:
                tx = self._new_threat_transaction(cluster_id, amount=500_000 - step * 20_000)
                nodes.append(tx)
                self._edge(prev_company, tx, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)
                self._edge(tx, co, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)

            prev_company = co

        self._threat_clusters[cluster_id] = set(nodes)
        self._threat_seeds.append(pa)

    def _inject_threat_shell_network(self, cluster_id: int):
        """One director, 4 shell companies, same address."""
        director = self._mark_threat(self.rng.choice(self._persons), cluster_id)
        addr = self._mark_threat(self.rng.choice(self._addresses), cluster_id)
        nodes = [director, addr]

        for _ in range(4):
            co = self._new_threat_company(cluster_id)
            nodes.append(co)
            self._edge(director, co, EdgeType.DIRECTS, DataSource.BOLAGSVERKET)
            self._edge(co, addr, EdgeType.REGISTERED_AT, DataSource.BOLAGSVERKET)
            # inter-company transactions
            if len(nodes) > 4:
                other = self.rng.choice([n for n in nodes if n.startswith("C-")])
                if other != co:
                    tx = self._new_threat_transaction(cluster_id, amount=200_000)
                    nodes.append(tx)
                    self._edge(co, tx, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)
                    self._edge(tx, other, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)

        self._threat_clusters[cluster_id] = set(nodes)
        self._threat_seeds.append(director)

    def _inject_threat_benefit_fraud(self, cluster_id: int):
        """Person claims benefits while directing a profitable company."""
        person = self._mark_threat(self.rng.choice(self._persons), cluster_id)
        co = self._new_threat_company(cluster_id)
        self._edge(person, co, EdgeType.DIRECTS, DataSource.BOLAGSVERKET)
        self._edge(person, person, EdgeType.CLAIMS_BENEFIT, DataSource.FORSAKRINGSKASSAN)

        tx = self._new_threat_transaction(cluster_id, amount=300_000)
        self._edge(co, tx, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)

        nodes = {person, co, tx}
        self._threat_clusters[cluster_id] = nodes
        self._threat_seeds.append(person)

    def _inject_threat_vat_carousel(self, cluster_id: int):
        """Circular transaction chain across 4 companies."""
        companies = [self._new_threat_company(cluster_id) for _ in range(4)]
        nodes = set(companies)

        for i in range(4):
            src, dst = companies[i], companies[(i + 1) % 4]
            tx = self._new_threat_transaction(cluster_id, amount=400_000 + i * 10_000)
            nodes.add(tx)
            self._edge(src, tx, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)
            self._edge(tx, dst, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)

        self._threat_clusters[cluster_id] = nodes
        self._threat_seeds.append(companies[0])

    def _inject_threat_burst_transactions(self, cluster_id: int):
        """One company with a burst of high-value transactions in a short period."""
        co = self._mark_threat(self.rng.choice(self._companies), cluster_id)
        nodes = {co}

        for _ in range(6):
            tx = self._new_threat_transaction(cluster_id, amount=self.rng.uniform(800_000, 2_000_000))
            nodes.add(tx)
            self._edge(co, tx, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)
            target = self.rng.choice(self._companies)
            self._edge(tx, target, EdgeType.TRANSACTED, DataSource.SKATTEVERKET)

        self._threat_clusters[cluster_id] = nodes
        self._threat_seeds.append(co)

    def _inject_ambiguous_entities(self):
        """Legitimate-but-suspicious patterns."""
        # 1: consultant with multiple directorships
        consultant = self.rng.choice(self._persons)
        self.G.nodes[consultant]["_ground_truth"] = "ambiguous"
        for _ in range(4):
            c = self.rng.choice(self._companies)
            self._edge(consultant, c, EdgeType.BOARD_MEMBER, DataSource.BOLAGSVERKET)

        # 2: seasonal worker alternating employment and benefits
        seasonal = self.rng.choice([p for p in self._persons if p != consultant])
        self.G.nodes[seasonal]["_ground_truth"] = "ambiguous"
        for _ in range(3):
            c = self.rng.choice(self._companies)
            self._edge(seasonal, c, EdgeType.EMPLOYED_BY, DataSource.ARBETSFORMEDLINGEN)
        self._edge(seasonal, seasonal, EdgeType.CLAIMS_BENEFIT, DataSource.FORSAKRINGSKASSAN)

        # 3: holding company with many subsidiaries
        holding = self.rng.choice(self._companies)
        self.G.nodes[holding]["_ground_truth"] = "ambiguous"
        for _ in range(5):
            sub = self.rng.choice(self._companies)
            if sub != holding:
                self._edge(holding, sub, EdgeType.OWNS, DataSource.BOLAGSVERKET)

    def _add_er_noise(self):
        """Lower entity_resolution_confidence on a fraction of cross-agency edges."""
        edges = list(self.G.edges(keys=True, data=True))
        cross_agency = [(u, v, k, d) for u, v, k, d in edges
                        if self.G.nodes[u].get("source") != self.G.nodes[v].get("source")]
        n_noisy = int(len(cross_agency) * self.cfg.er_noise_frac)
        if n_noisy == 0:
            return
        chosen = self.rng.choice(len(cross_agency), size=n_noisy, replace=False)
        for idx in chosen:
            u, v, k, _ = cross_agency[idx]
            self.G.edges[u, v, k]["entity_resolution_confidence"] = round(
                float(self.rng.uniform(0.4, 0.75)), 2
            )

    # ── helpers ────────────────────────────────────────────────────────

    def _edge(self, src: str, dst: str, etype: EdgeType, source: DataSource,
              er_conf: float = 1.0):
        self.G.add_edge(src, dst,
                        edge_type=etype,
                        relationship_category=EDGE_TO_RELCAT[etype],
                        source=source,
                        entity_resolution_confidence=er_conf)

    def _mark_threat(self, nid: str, cluster_id: int) -> str:
        self.G.nodes[nid]["_ground_truth"] = "threat"
        self.G.nodes[nid]["_threat_cluster"] = cluster_id
        return nid

    def _new_threat_company(self, cluster_id: int) -> str:
        nid = f"C-T{cluster_id}-{self.rng.integers(1000, 9999)}"
        self.G.add_node(nid,
                        node_type=NodeType.COMPANY,
                        source=DataSource.BOLAGSVERKET,
                        org_nr=f"55{self.rng.integers(1000,9999)}-{self.rng.integers(1000,9999)}",
                        _ground_truth="threat",
                        _threat_cluster=cluster_id)
        self._companies.append(nid)
        return nid

    def _new_threat_transaction(self, cluster_id: int, amount: float) -> str:
        nid = f"T-T{cluster_id}-{self.rng.integers(1000, 9999)}"
        self.G.add_node(nid,
                        node_type=NodeType.TRANSACTION,
                        source=DataSource.SKATTEVERKET,
                        amount=round(amount, 2),
                        _ground_truth="threat",
                        _threat_cluster=cluster_id)
        self._transactions.append(nid)
        return nid
