"""
Synthetic Knowledge Graph for TrustLayer MVP Demo.

Models Swedish multi-agency OSINT data across 5 government data sources.
The graph encodes entities (persons, companies, properties, filings, etc.)
and their relationships. AI agent traversal of this graph produces the
AgentOutput objects that feed into the governance pipeline.

Data sources modelled:
  - Skatteverket (Tax Authority): tax filings, employer reports
  - Bolagsverket (Companies Registration Office): company registry, directors
  - Försäkringskassan (Social Insurance Agency): benefit claims, medical certs
  - Lantmäteriet (Land Registry): property ownership, valuations
  - OSINT: social media posts, public intelligence bulletins

Usage:
    kg = SyntheticKnowledgeGraph()
    scenario = kg.query_vat_carousel()       # AgentOutput from graph traversal
    html = kg.to_vis_html()                  # Interactive visualisation
    subgraph = kg.get_scenario_subgraph(...)  # Highlight a traversal path
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import networkx as nx

from .models import (
    AgentOutput, Claim, EvidenceItem, Fragment, ActionType, new_id,
)


# =============================================================================
# § ENUMS — Node types, edge types, data sources
# =============================================================================

class NodeType(Enum):
    PERSON = "person"
    COMPANY = "company"
    PROPERTY = "property"
    TAX_FILING = "tax_filing"
    BENEFIT_CLAIM = "benefit_claim"
    SOCIAL_POST = "social_post"
    INTEL_BULLETIN = "intel_bulletin"
    ADDRESS = "address"
    MEDICAL_CERT = "medical_cert"
    EMPLOYMENT_RECORD = "employment_record"


class EdgeType(Enum):
    DIRECTS = "directs"
    OWNS = "owns"
    BOARD_MEMBER = "board_member"
    EMPLOYED_BY = "employed_by"
    FILED = "filed"
    OWNS_PROPERTY = "owns_property"
    RENTS_TO = "rents_to"
    CLAIMS_BENEFIT = "claims_benefit"
    POSTED = "posted"
    MENTIONED_IN = "mentioned_in"
    REGISTERED_AT = "registered_at"
    TAGS = "tags"
    CERTIFIED_BY = "certified_by"
    CONTRADICTS = "contradicts"
    LINKED_TO = "linked_to"
    HAS_RECORD = "has_record"


class DataSource(Enum):
    SKATTEVERKET_TAX = "Skatteverket-TaxDB"
    SKATTEVERKET_EMP = "Skatteverket-EmployerDB"
    BOLAGSVERKET = "Bolagsverket-Registry"
    FORSAKRINGSKASSAN = "Försäkringskassan-DB"
    LANTMATERIET = "Lantmäteriet-PropertyDB"
    OSINT_SOCIAL = "OSINT-SocialMedia"
    OSINT_PUBLIC = "OSINT-PublicRegistry"


SOURCE_RELIABILITY: dict[DataSource, float] = {
    DataSource.SKATTEVERKET_TAX: 0.9,
    DataSource.SKATTEVERKET_EMP: 0.9,
    DataSource.BOLAGSVERKET: 0.95,
    DataSource.FORSAKRINGSKASSAN: 0.92,
    DataSource.LANTMATERIET: 0.93,
    DataSource.OSINT_SOCIAL: 0.4,
    DataSource.OSINT_PUBLIC: 0.6,
}

LEGAL_BASIS: dict[DataSource, str] = {
    DataSource.SKATTEVERKET_TAX: "Skatteförfarandelagen (2011:1244) §42",
    DataSource.SKATTEVERKET_EMP: "Skatteförfarandelagen (2011:1244) §15",
    DataSource.BOLAGSVERKET: "Offentlighetsprincipen (public records)",
    DataSource.FORSAKRINGSKASSAN: "Socialförsäkringsbalken (2010:110) §27",
    DataSource.LANTMATERIET: "Offentlighetsprincipen (public records)",
    DataSource.OSINT_SOCIAL: "Publicly available social media post",
    DataSource.OSINT_PUBLIC: "Publicly available information; no special access required",
}

# Visual style per node type
_NODE_COLORS: dict[str, str] = {
    NodeType.PERSON.value: "#6366f1",
    NodeType.COMPANY.value: "#22c55e",
    NodeType.PROPERTY.value: "#eab308",
    NodeType.TAX_FILING.value: "#f97316",
    NodeType.BENEFIT_CLAIM.value: "#ec4899",
    NodeType.SOCIAL_POST.value: "#06b6d4",
    NodeType.INTEL_BULLETIN.value: "#ef4444",
    NodeType.ADDRESS.value: "#94a3b8",
    NodeType.MEDICAL_CERT.value: "#a855f7",
    NodeType.EMPLOYMENT_RECORD.value: "#f59e0b",
}

_NODE_SHAPES: dict[str, str] = {
    NodeType.PERSON.value: "dot",
    NodeType.COMPANY.value: "diamond",
    NodeType.PROPERTY.value: "square",
    NodeType.TAX_FILING.value: "triangle",
    NodeType.BENEFIT_CLAIM.value: "star",
    NodeType.SOCIAL_POST.value: "triangleDown",
    NodeType.INTEL_BULLETIN.value: "hexagon",
    NodeType.ADDRESS.value: "box",
    NodeType.MEDICAL_CERT.value: "ellipse",
    NodeType.EMPLOYMENT_RECORD.value: "triangle",
}


# =============================================================================
# § HELPERS
# =============================================================================

def _subject_ref(name: str) -> str:
    return hashlib.sha256(f"agency-secret:{name}".encode()).hexdigest()[:16]


def _content_hash(tag: str) -> str:
    return hashlib.sha256(tag.encode()).hexdigest()


def _make_evidence(source: DataSource, summary: str, hash_tag: str,
                   collected_delta_days: int = 5) -> EvidenceItem:
    return EvidenceItem(
        item_id=new_id(),
        source_id=source.value,
        source_reliability=SOURCE_RELIABILITY[source],
        collected_at=datetime.now(timezone.utc) - timedelta(days=collected_delta_days),
        content_summary=summary,
        content_hash=_content_hash(hash_tag),
        legal_basis=LEGAL_BASIS[source],
    )


# =============================================================================
# § KNOWLEDGE GRAPH
# =============================================================================

class SyntheticKnowledgeGraph:
    """Multi-agency knowledge graph for Swedish government OSINT scenarios.

    The graph is a directed multigraph (NetworkX MultiDiGraph) where:
      - Nodes represent entities (persons, companies, filings, etc.)
      - Edges represent relationships discovered from government data sources
      - Each edge is annotated with the data source it came from

    Six scenario clusters are pre-built, connected by cross-agency links.
    """

    def __init__(self):
        self.G = nx.MultiDiGraph()
        self._build()

    # -------------------------------------------------------------------------
    # Graph construction
    # -------------------------------------------------------------------------

    def _add_node(self, node_id: str, node_type: NodeType, source: DataSource,
                  label: str = "", **attrs):
        self.G.add_node(node_id,
                        node_type=node_type.value,
                        source=source.value,
                        label=label or node_id,
                        **attrs)

    def _add_edge(self, src: str, dst: str, edge_type: EdgeType,
                  source: DataSource, **attrs):
        self.G.add_edge(src, dst,
                        edge_type=edge_type.value,
                        source=source.value,
                        label=edge_type.value.upper(),
                        **attrs)

    def _build(self):
        self._build_vat_carousel()
        self._build_social_media_cluster()
        self._build_insurance_fraud()
        self._build_address_changes()
        self._build_related_party()
        self._build_routine_filing()
        self._build_cross_links()

    # -- Cluster 1: VAT Carousel Fraud Network --------------------------------

    def _build_vat_carousel(self):
        S = DataSource
        N = NodeType
        E = EdgeType

        # Persons
        self._add_node("person:erik_lindqvist", N.PERSON, S.BOLAGSVERKET,
                        label="Erik Lindqvist", role="director",
                        cluster="vat_carousel")

        # Companies
        companies = [
            ("company:nordic_consulting", "Nordic Consulting AB", "2024-01-15"),
            ("company:baltic_import", "Baltic Import AB", "2024-02-01"),
            ("company:scandia_trading", "Scandia Trading AB", "2024-03-10"),
            ("company:north_commerce", "North Commerce AB", "2024-04-05"),
            ("company:euro_logistics", "Euro Logistics AB", "2024-05-20"),
        ]
        for cid, name, reg_date in companies:
            self._add_node(cid, N.COMPANY, S.BOLAGSVERKET,
                            label=name, registration_date=reg_date,
                            cluster="vat_carousel")
            self._add_edge("person:erik_lindqvist", cid, E.DIRECTS, S.BOLAGSVERKET,
                            since=reg_date)

        # Shared address
        self._add_node("addr:box_1234_stockholm", N.ADDRESS, S.BOLAGSVERKET,
                        label="Box 1234, Stockholm", cluster="vat_carousel")
        for cid, _, _ in companies:
            self._add_edge(cid, "addr:box_1234_stockholm", E.REGISTERED_AT,
                            S.BOLAGSVERKET)

        # Tax filings showing carousel pattern
        for i, (cid, name, _) in enumerate(companies):
            fid = f"tax_filing:vat_{i}"
            intra_eu = f"€{1.8 + i * 0.3:.1f}M"
            self._add_node(fid, N.TAX_FILING, S.SKATTEVERKET_TAX,
                            label=f"VAT Filing\n{intra_eu} intra-EU\n€0 domestic",
                            intra_eu_amount=intra_eu,
                            domestic_sales="€0",
                            period="18 months",
                            cluster="vat_carousel")
            self._add_edge(cid, fid, E.FILED, S.SKATTEVERKET_TAX)

        # OSINT: LinkedIn + intel bulletin
        self._add_node("post:linkedin_erik", N.SOCIAL_POST, S.OSINT_SOCIAL,
                        label="LinkedIn: employed at\nBaltic Trade Group, Tallinn",
                        platform="LinkedIn",
                        cluster="vat_carousel")
        self._add_edge("person:erik_lindqvist", "post:linkedin_erik", E.POSTED,
                        S.OSINT_SOCIAL)

        self._add_node("company:baltic_trade_group", N.COMPANY, S.OSINT_PUBLIC,
                        label="Baltic Trade Group\n(Tallinn, Estonia)",
                        foreign=True,
                        cluster="vat_carousel")
        self._add_edge("post:linkedin_erik", "company:baltic_trade_group",
                        E.LINKED_TO, S.OSINT_PUBLIC)

        self._add_node("intel:eu_carousel_bulletin", N.INTEL_BULLETIN, S.OSINT_PUBLIC,
                        label="EU Carousel Fraud\nBulletin 2024-Q3",
                        cluster="vat_carousel")
        self._add_edge("company:baltic_trade_group", "intel:eu_carousel_bulletin",
                        E.MENTIONED_IN, S.OSINT_PUBLIC)

    # -- Cluster 2: Social Media False Positive --------------------------------

    def _build_social_media_cluster(self):
        S = DataSource
        N = NodeType
        E = EdgeType

        self._add_node("person:anna_svensson", N.PERSON, S.OSINT_SOCIAL,
                        label="Anna Svensson", cluster="social_media_fp")

        self._add_node("post:tweet_crypto", N.SOCIAL_POST, S.OSINT_SOCIAL,
                        label="Tweet: 'new business\nopportunities in cryptocurrency'",
                        platform="Twitter", handle="@svensson_trade",
                        cluster="social_media_fp")
        self._add_edge("person:anna_svensson", "post:tweet_crypto", E.POSTED,
                        S.OSINT_SOCIAL)

        self._add_node("post:nordic_invest", N.SOCIAL_POST, S.OSINT_SOCIAL,
                        label="@nordic_invest\n(tagged account)",
                        platform="Twitter", handle="@nordic_invest",
                        cluster="social_media_fp")
        self._add_edge("post:tweet_crypto", "post:nordic_invest", E.TAGS,
                        S.OSINT_SOCIAL)

        self._add_node("intel:scam_flagged_accounts", N.INTEL_BULLETIN, S.OSINT_SOCIAL,
                        label="Investment Scam\nFlagged Accounts DB",
                        cluster="social_media_fp")
        self._add_edge("post:nordic_invest", "intel:scam_flagged_accounts",
                        E.LINKED_TO, S.OSINT_SOCIAL,
                        link_type="follower_overlap",
                        note="Follower overlap — not direct connection")

    # -- Cluster 3: Insurance Fraud (multi-agency) ----------------------------

    def _build_insurance_fraud(self):
        S = DataSource
        N = NodeType
        E = EdgeType

        self._add_node("person:johan_berg", N.PERSON, S.FORSAKRINGSKASSAN,
                        label="Johan Berg", cluster="insurance_fraud")

        # Benefit claim
        self._add_node("benefit:sjukpenning_berg", N.BENEFIT_CLAIM,
                        S.FORSAKRINGSKASSAN,
                        label="Sjukpenning\nsince 2024-03-01\n(continuous)",
                        benefit_type="sjukpenning",
                        start_date="2024-03-01",
                        cluster="insurance_fraud")
        self._add_edge("person:johan_berg", "benefit:sjukpenning_berg",
                        E.CLAIMS_BENEFIT, S.FORSAKRINGSKASSAN)

        # Medical certificate
        self._add_node("cert:dr_nilsson", N.MEDICAL_CERT, S.FORSAKRINGSKASSAN,
                        label="Medical Cert:\n'unable to perform\nany work duties'",
                        doctor="Dr. K. Nilsson",
                        clinic="Vårdcentralen Södermalm",
                        cluster="insurance_fraud")
        self._add_edge("benefit:sjukpenning_berg", "cert:dr_nilsson",
                        E.CERTIFIED_BY, S.FORSAKRINGSKASSAN)

        # Company
        self._add_node("company:berg_bygg", N.COMPANY, S.BOLAGSVERKET,
                        label="Berg & Partners\nBygg AB",
                        registration_date="2023-06-01",
                        cluster="insurance_fraud")
        self._add_edge("person:johan_berg", "company:berg_bygg",
                        E.DIRECTS, S.BOLAGSVERKET, role="sole owner and director")
        self._add_edge("person:johan_berg", "company:berg_bygg",
                        E.OWNS, S.BOLAGSVERKET, share_pct=100)

        # Employment record — contradiction!
        self._add_node("emp:berg_hours", N.EMPLOYMENT_RECORD, S.SKATTEVERKET_EMP,
                        label="160 billable hours\nApril 2024",
                        hours=160, period="April 2024",
                        cluster="insurance_fraud")
        self._add_edge("company:berg_bygg", "emp:berg_hours",
                        E.HAS_RECORD, S.SKATTEVERKET_EMP)
        self._add_edge("person:johan_berg", "emp:berg_hours",
                        E.EMPLOYED_BY, S.SKATTEVERKET_EMP)

        # Contradiction edge
        self._add_edge("emp:berg_hours", "cert:dr_nilsson",
                        E.CONTRADICTS, S.SKATTEVERKET_EMP,
                        note="Working 160h while certified 'unable to work'")

        # Social media confirmation
        self._add_node("post:instagram_berg", N.SOCIAL_POST, S.OSINT_SOCIAL,
                        label="Instagram @berg_bygg:\n'Another project delivered!'\nApr 15, 2024",
                        platform="Instagram", handle="@berg_bygg",
                        cluster="insurance_fraud")
        self._add_edge("person:johan_berg", "post:instagram_berg",
                        E.POSTED, S.OSINT_SOCIAL)

    # -- Cluster 4: Address Changes (low confidence) --------------------------

    def _build_address_changes(self):
        S = DataSource
        N = NodeType
        E = EdgeType

        self._add_node("company:malmo_import", N.COMPANY, S.BOLAGSVERKET,
                        label="Malmö Import\nExport AB",
                        cluster="address_changes")

        addresses = [
            ("addr:malmo_1", "Storgatan 12, Malmö", "2024-01"),
            ("addr:malmo_2", "Industrivägen 8, Malmö", "2024-04"),
            ("addr:malmo_3", "Hamngatan 3, Malmö", "2024-07"),
        ]
        for aid, label, date in addresses:
            self._add_node(aid, N.ADDRESS, S.BOLAGSVERKET,
                            label=label, cluster="address_changes")
            self._add_edge("company:malmo_import", aid, E.REGISTERED_AT,
                            S.BOLAGSVERKET, changed_date=date)

    # -- Cluster 5: Related-Party Tax Underreporting --------------------------

    def _build_related_party(self):
        S = DataSource
        N = NodeType
        E = EdgeType

        self._add_node("person:sara_johansson", N.PERSON, S.BOLAGSVERKET,
                        label="Sara Johansson", cluster="related_party")

        # Landlord company
        self._add_node("company:gbg_fastigheter", N.COMPANY, S.BOLAGSVERKET,
                        label="Göteborg\nFastigheter AB",
                        cluster="related_party")
        self._add_edge("person:sara_johansson", "company:gbg_fastigheter",
                        E.DIRECTS, S.BOLAGSVERKET)

        # Tenant company
        self._add_node("company:gbg_services", N.COMPANY, S.BOLAGSVERKET,
                        label="GBG Services AB",
                        cluster="related_party")
        self._add_edge("person:sara_johansson", "company:gbg_services",
                        E.BOARD_MEMBER, S.BOLAGSVERKET)

        # Rental relationship (below market)
        self._add_edge("company:gbg_fastigheter", "company:gbg_services",
                        E.RENTS_TO, S.SKATTEVERKET_TAX,
                        reported_income="€45,000 below market",
                        note="Related-party transaction at below-market rate")

        # Properties
        for i in range(1, 4):
            pid = f"property:gbg_central_{i}"
            self._add_node(pid, N.PROPERTY, S.LANTMATERIET,
                            label=f"Commercial Property\nCentral Gothenburg #{i}",
                            market_rental="significantly above reported",
                            cluster="related_party")
            self._add_edge("company:gbg_fastigheter", pid, E.OWNS_PROPERTY,
                            S.LANTMATERIET)

        # Tax filing
        self._add_node("tax_filing:gbg_rental", N.TAX_FILING, S.SKATTEVERKET_TAX,
                        label="Rental Income\n€45K below market estimate",
                        discrepancy="€45,000",
                        cluster="related_party")
        self._add_edge("company:gbg_fastigheter", "tax_filing:gbg_rental",
                        E.FILED, S.SKATTEVERKET_TAX)

    # -- Cluster 6: Routine Late Filing ---------------------------------------

    def _build_routine_filing(self):
        S = DataSource
        N = NodeType
        E = EdgeType

        self._add_node("company:sthlm_tech", N.COMPANY, S.BOLAGSVERKET,
                        label="Stockholm Tech\nSolutions AB",
                        cluster="routine_filing")

        self._add_node("tax_filing:late_report", N.TAX_FILING, S.BOLAGSVERKET,
                        label="Annual Report\n15 days late",
                        status="late", days_late=15,
                        cluster="routine_filing")
        self._add_edge("company:sthlm_tech", "tax_filing:late_report",
                        E.FILED, S.BOLAGSVERKET)

        self._add_node("tax_filing:history_ok", N.TAX_FILING, S.BOLAGSVERKET,
                        label="8 Years On-Time\nFiling History",
                        status="on_time", years=8,
                        cluster="routine_filing")
        self._add_edge("company:sthlm_tech", "tax_filing:history_ok",
                        E.FILED, S.BOLAGSVERKET)

    # -- Cross-cluster links --------------------------------------------------

    def _build_cross_links(self):
        """Links between clusters that an agent might discover via multi-hop."""
        E = EdgeType
        S = DataSource

        # Erik Lindqvist's Euro Logistics once shared address with Malmö Import
        self._add_edge("company:euro_logistics", "addr:malmo_1",
                        E.REGISTERED_AT, S.BOLAGSVERKET,
                        note="Previously registered at same address",
                        changed_date="2023-11")

        # Sara Johansson once served on board of Stockholm Tech Solutions
        self._add_edge("person:sara_johansson", "company:sthlm_tech",
                        E.BOARD_MEMBER, S.BOLAGSVERKET,
                        note="Former board member (2020-2023)")

    # -------------------------------------------------------------------------
    # Graph query / traversal → AgentOutput
    # -------------------------------------------------------------------------

    def get_cluster_nodes(self, cluster: str) -> list[str]:
        return [n for n, d in self.G.nodes(data=True) if d.get("cluster") == cluster]

    def get_cluster_subgraph(self, cluster: str) -> nx.MultiDiGraph:
        nodes = self.get_cluster_nodes(cluster)
        return self.G.subgraph(nodes).copy()

    def get_traversal_path(self, cluster: str) -> list[tuple[str, str, dict]]:
        """Return all edges in a cluster as a traversal path."""
        sub = self.get_cluster_subgraph(cluster)
        return list(sub.edges(data=True))

    def _evidence_from_edges(self, cluster: str) -> list[EvidenceItem]:
        """Collect evidence items from graph edges in a cluster."""
        items = []
        seen_summaries = set()
        for u, v, data in self.get_traversal_path(cluster):
            u_data = self.G.nodes[u]
            v_data = self.G.nodes[v]
            src_str = data.get("source", "")
            source = None
            for ds in DataSource:
                if ds.value == src_str:
                    source = ds
                    break
            if not source:
                continue

            summary = self._edge_to_summary(u, v, data, u_data, v_data)
            if summary in seen_summaries:
                continue
            seen_summaries.add(summary)

            items.append(EvidenceItem(
                item_id=new_id(),
                source_id=source.value,
                source_reliability=SOURCE_RELIABILITY.get(source, 0.5),
                collected_at=datetime.now(timezone.utc) - timedelta(days=len(items) + 1),
                content_summary=summary,
                content_hash=_content_hash(f"{u}-{v}-{data.get('edge_type','')}"),
                legal_basis=LEGAL_BASIS.get(source, ""),
            ))
        return items

    def _edge_to_summary(self, u: str, v: str, edge_data: dict,
                         u_data: dict, v_data: dict) -> str:
        """Generate a human-readable summary from an edge."""
        u_label = u_data.get("label", u).replace("\n", " ")
        v_label = v_data.get("label", v).replace("\n", " ")
        etype = edge_data.get("edge_type", "")

        summaries = {
            "directs": f"{u_label} directs {v_label}",
            "owns": f"{u_label} owns {v_label}",
            "filed": f"{u_label} filed {v_label}",
            "registered_at": f"{u_label} registered at {v_label}",
            "claims_benefit": f"{u_label} claims {v_label}",
            "employed_by": f"{u_label} employed at {v_label}",
            "posted": f"{u_label} posted {v_label}",
            "linked_to": f"{u_label} linked to {v_label}",
            "mentioned_in": f"{u_label} mentioned in {v_label}",
            "rents_to": f"{u_label} rents to {v_label}",
            "owns_property": f"{u_label} owns property {v_label}",
            "board_member": f"{u_label} is board member of {v_label}",
            "certified_by": f"{u_label} certified by {v_label}",
            "contradicts": f"{u_label} contradicts {v_label}",
            "has_record": f"{u_label} has record {v_label}",
            "tags": f"{u_label} tags {v_label}",
        }
        base = summaries.get(etype, f"{u_label} → {v_label}")
        note = edge_data.get("note", "")
        return f"{base} — {note}" if note else base

    def _fragments_from_nodes(self, cluster: str) -> list[Fragment]:
        """Extract evidence fragments from node labels in a cluster."""
        fragments = []
        for nid in self.get_cluster_nodes(cluster):
            data = self.G.nodes[nid]
            label = data.get("label", "").replace("\n", " ")
            source = data.get("source", "")
            if data.get("node_type") in (
                NodeType.TAX_FILING.value, NodeType.BENEFIT_CLAIM.value,
                NodeType.EMPLOYMENT_RECORD.value, NodeType.MEDICAL_CERT.value,
                NodeType.SOCIAL_POST.value, NodeType.INTEL_BULLETIN.value,
            ):
                fragments.append(Fragment(
                    value=label, source_id=source, start_position=0,
                ))
        return fragments

    def query_vat_carousel(self) -> dict:
        """Traverse the VAT carousel cluster and produce an AgentOutput."""
        cluster = "vat_carousel"
        evidence = self._evidence_from_edges(cluster)
        fragments = self._fragments_from_nodes(cluster)

        return {
            "name": "VAT Carousel Fraud Network",
            "description": "KG traversal: multi-hop path across Skatteverket + Bolagsverket + OSINT "
                           "reveals 5 shell companies with common director and carousel VAT pattern.",
            "context": "Swedish Tax Authority (Skatteverket) cross-agency investigation",
            "cluster": cluster,
            "output": AgentOutput(
                output_id=new_id(), agent_id="cybersec-agent-skat-01",
                subject_ref=_subject_ref("Erik Lindqvist"),
                claim=Claim(
                    text="Evidence suggests Nordic Consulting AB is part of a VAT carousel fraud network involving 5 linked shell companies with a common director",
                    supporting_evidence=[e.item_id for e in evidence],
                    reasoning_chain=[
                        "KG hop 1: Erik Lindqvist → DIRECTS → Nordic Consulting AB (Bolagsverket)",
                        "KG hop 2: Erik Lindqvist → DIRECTS → 4 additional companies at same address",
                        "KG hop 3: All 5 companies → FILED → VAT returns showing intra-EU acquisitions, zero domestic sales",
                        "KG hop 4: Erik Lindqvist → POSTED → LinkedIn mentions Baltic Trade Group (Tallinn)",
                        "KG hop 5: Baltic Trade Group → MENTIONED_IN → EU Carousel Fraud Bulletin 2024-Q3",
                        "Combined: director network + carousel pattern + known fraud entity link",
                    ],
                    falsification_conditions=[
                        "If Nordic Consulting AB can demonstrate legitimate domestic customers",
                        "If the intra-EU acquisitions correspond to real goods movements with customs documentation",
                        "If Erik Lindqvist's multiple directorships have legitimate business rationale",
                    ],
                    alternative_hypothesis="Erik Lindqvist is a legitimate business consultant who advises multiple startups in import/export, and the VAT patterns reflect normal early-stage trade activity",
                ),
                evidence=evidence, raw_fragments=fragments,
                agent_confidence=0.82,
                action_requested=ActionType.ESCALATE_TO_SENIOR,
            ),
        }

    def query_social_media_fp(self) -> dict:
        cluster = "social_media_fp"
        evidence = self._evidence_from_edges(cluster)
        fragments = self._fragments_from_nodes(cluster)

        return {
            "name": "Social Media OSINT — False Positive",
            "description": "KG traversal: weak social media links. Agent hallucinated 'money laundering' — "
                           "fragments only mention cryptocurrency discussion.",
            "context": "OSINT social media monitoring pipeline",
            "cluster": cluster,
            "output": AgentOutput(
                output_id=new_id(), agent_id="cybersec-agent-osint-01",
                subject_ref=_subject_ref("Anna Svensson"),
                claim=Claim(
                    text="Evidence suggests money laundering operation through cryptocurrency mixing services linked to organised crime network",
                    supporting_evidence=[e.item_id for e in evidence],
                    reasoning_chain=[
                        "KG hop 1: Anna Svensson → POSTED → Tweet about cryptocurrency",
                        "KG hop 2: Tweet → TAGS → @nordic_invest account",
                        "KG hop 3: @nordic_invest → LINKED_TO → Investment Scam Flagged Accounts (follower overlap only)",
                        "Inference: cryptocurrency + flagged accounts = money laundering",
                    ],
                    falsification_conditions=[
                        "If the cryptocurrency discussion is about legitimate investment",
                        "If the flagged accounts were flagged for non-criminal reasons",
                    ],
                    alternative_hypothesis="Citizen discussing legitimate cryptocurrency investment with acquaintances",
                ),
                evidence=evidence, raw_fragments=fragments,
                agent_confidence=0.65,
                action_requested=ActionType.ALERT_OPERATOR,
            ),
        }

    def query_insurance_fraud(self) -> dict:
        cluster = "insurance_fraud"
        evidence = self._evidence_from_edges(cluster)
        fragments = self._fragments_from_nodes(cluster)

        return {
            "name": "Sickness Benefit Fraud — Multi-Agency",
            "description": "KG traversal: cross-agency contradiction path. Försäkringskassan benefit claim "
                           "contradicted by Skatteverket employer records + OSINT social media.",
            "context": "Försäkringskassan (Social Insurance Agency) cross-agency investigation",
            "cluster": cluster,
            "output": AgentOutput(
                output_id=new_id(), agent_id="cybersec-agent-fk-01",
                subject_ref=_subject_ref("Johan Berg"),
                claim=Claim(
                    text="Evidence suggests Johan Berg is working full-time as director of his construction company while simultaneously receiving sickness benefit based on a certificate stating he is unable to work",
                    supporting_evidence=[e.item_id for e in evidence],
                    reasoning_chain=[
                        "KG hop 1: Johan Berg → CLAIMS_BENEFIT → Sjukpenning (Försäkringskassan)",
                        "KG hop 2: Sjukpenning → CERTIFIED_BY → Medical cert: 'unable to work' (Försäkringskassan)",
                        "KG hop 3: Johan Berg → DIRECTS/OWNS → Berg & Partners Bygg AB (Bolagsverket)",
                        "KG hop 4: Berg & Partners Bygg AB → HAS_RECORD → 160 hours April 2024 (Skatteverket)",
                        "KG hop 5: Employment record → CONTRADICTS → Medical certificate",
                        "KG hop 6: Johan Berg → POSTED → Instagram 'Another project delivered!' (OSINT)",
                        "Combined: 4 independent sources converge on contradiction",
                    ],
                    falsification_conditions=[
                        "If the billable hours were logged by another employee under Berg's account",
                        "If the social media posts were scheduled/backdated",
                        "If the medical condition permits supervisory work but not physical labor",
                    ],
                    alternative_hypothesis="Johan Berg delegated all physical work to employees and only performs light administrative duties compatible with his medical condition",
                ),
                evidence=evidence, raw_fragments=fragments,
                agent_confidence=0.88,
                action_requested=ActionType.ESCALATE_TO_LEGAL,
            ),
        }

    def query_address_changes(self) -> dict:
        cluster = "address_changes"
        evidence = self._evidence_from_edges(cluster)
        fragments = self._fragments_from_nodes(cluster)

        return {
            "name": "Weak Signal — Address Changes",
            "description": "KG traversal: single-source pattern. Company changed address 3 times in 6 months. "
                           "Low confidence — G1 should block.",
            "context": "Bolagsverket business registry pattern analysis",
            "cluster": cluster,
            "output": AgentOutput(
                output_id=new_id(), agent_id="cybersec-agent-bol-01",
                subject_ref=_subject_ref("Malmö Import Export AB"),
                claim=Claim(
                    text="Evidence suggests possible shell company activity based on frequent address changes",
                    supporting_evidence=[e.item_id for e in evidence],
                    reasoning_chain=[
                        "KG hop 1: Malmö Import Export AB → REGISTERED_AT → 3 different addresses",
                        "KG pattern: 3 address changes in 6 months is anomalous",
                        "Inference: frequent address changes correlate with shell company behavior",
                    ],
                    falsification_conditions=[
                        "If the company relocated due to office expansion",
                        "If address changes correspond to normal business growth",
                    ],
                    alternative_hypothesis="Growing company moved to larger offices multiple times during rapid expansion phase",
                ),
                evidence=evidence, raw_fragments=fragments,
                agent_confidence=0.15,
                action_requested=ActionType.FLAG_FOR_REVIEW,
            ),
        }

    def query_related_party(self) -> dict:
        cluster = "related_party"
        evidence = self._evidence_from_edges(cluster)
        fragments = self._fragments_from_nodes(cluster)

        return {
            "name": "Related-Party Tax Underreporting",
            "description": "KG traversal: cross-agency join reveals director renting properties to her own company "
                           "at below-market rates. Skatteverket + Bolagsverket + Lantmäteriet.",
            "context": "Skatteverket (Tax Authority) cross-reference with Lantmäteriet (Land Registry)",
            "cluster": cluster,
            "output": AgentOutput(
                output_id=new_id(), agent_id="cybersec-agent-skat-02",
                subject_ref=_subject_ref("Sara Johansson"),
                claim=Claim(
                    text="Evidence suggests director Sara Johansson is underreporting rental income by approximately €45,000 annually through related-party transactions between companies she controls",
                    supporting_evidence=[e.item_id for e in evidence],
                    reasoning_chain=[
                        "KG hop 1: Sara Johansson → DIRECTS → Göteborg Fastigheter AB (Bolagsverket)",
                        "KG hop 2: Sara Johansson → BOARD_MEMBER → GBG Services AB (Bolagsverket)",
                        "KG hop 3: Göteborg Fastigheter AB → RENTS_TO → GBG Services AB (related-party!)",
                        "KG hop 4: Göteborg Fastigheter AB → OWNS_PROPERTY → 3 central properties (Lantmäteriet)",
                        "KG hop 5: Göteborg Fastigheter AB → FILED → rental income €45K below market (Skatteverket)",
                        "Combined: related-party relationship + below-market rents + multiple properties",
                    ],
                    falsification_conditions=[
                        "If rental rates reflect genuine market conditions (e.g. long-term contract signed before price increase)",
                        "If Sara Johansson's board membership in tenant company is non-executive with no influence on rental terms",
                    ],
                    alternative_hypothesis="Long-term rental contracts signed before the Gothenburg property market increase of 2023-2024 explain the below-market rates; relationship is disclosed in both companies' annual reports",
                ),
                evidence=evidence, raw_fragments=fragments,
                agent_confidence=0.74,
                action_requested=ActionType.REFER_TO_INVESTIGATOR,
            ),
        }

    def query_routine_filing(self) -> dict:
        cluster = "routine_filing"
        evidence = self._evidence_from_edges(cluster)
        fragments = self._fragments_from_nodes(cluster)

        return {
            "name": "Late Filing — Routine Flag",
            "description": "KG traversal: minimal graph. Single company, one late filing against 8 years clean history. "
                           "Low risk — auto-approve pathway.",
            "context": "Bolagsverket (Companies Registration Office) routine monitoring",
            "cluster": cluster,
            "output": AgentOutput(
                output_id=new_id(), agent_id="cybersec-agent-bol-02",
                subject_ref=_subject_ref("Stockholm Tech Solutions AB"),
                claim=Claim(
                    text="Evidence suggests minor administrative delay in annual report filing for Stockholm Tech Solutions AB",
                    supporting_evidence=[e.item_id for e in evidence],
                    reasoning_chain=[
                        "KG hop 1: Stockholm Tech Solutions AB → FILED → Annual report (15 days late)",
                        "KG hop 2: Stockholm Tech Solutions AB → FILED → 8 years on-time history",
                        "Assessment: isolated anomaly, no fraud indicators",
                    ],
                    falsification_conditions=[
                        "If late filing coincides with other financial irregularities",
                    ],
                    alternative_hypothesis="Administrative oversight, possibly due to staff changes or holiday period",
                ),
                evidence=evidence, raw_fragments=fragments,
                agent_confidence=0.90,
                action_requested=ActionType.FLAG_FOR_REVIEW,
            ),
        }

    def all_scenarios(self) -> list[dict]:
        """Return all 6 scenarios generated from KG traversals."""
        return [
            self.query_vat_carousel(),
            self.query_social_media_fp(),
            self.query_insurance_fraud(),
            self.query_address_changes(),
            self.query_related_party(),
            self.query_routine_filing(),
        ]

    # -------------------------------------------------------------------------
    # Graph statistics
    # -------------------------------------------------------------------------

    def stats(self) -> dict:
        clusters = set()
        sources = set()
        for _, d in self.G.nodes(data=True):
            clusters.add(d.get("cluster", ""))
            sources.add(d.get("source", ""))
        return {
            "nodes": self.G.number_of_nodes(),
            "edges": self.G.number_of_edges(),
            "clusters": len(clusters - {""}),
            "data_sources": len(sources - {""}),
        }

    def nodes_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, d in self.G.nodes(data=True):
            t = d.get("node_type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return counts

    def edges_by_source(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for _, _, d in self.G.edges(data=True):
            s = d.get("source", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return counts

    # -------------------------------------------------------------------------
    # Visualisation — generates interactive vis.js HTML
    # -------------------------------------------------------------------------

    def to_vis_html(self, highlight_cluster: Optional[str] = None,
                    width: str = "100%", height: str = "650px") -> str:
        """Generate interactive vis.js HTML for embedding in Streamlit.

        Args:
            highlight_cluster: If set, nodes in this cluster are bright,
                               others are dimmed.
            width/height: CSS dimensions.
        """
        nodes_js = []
        for nid, data in self.G.nodes(data=True):
            ntype = data.get("node_type", "")
            cluster = data.get("cluster", "")
            color = _NODE_COLORS.get(ntype, "#888")
            shape = _NODE_SHAPES.get(ntype, "dot")
            label = data.get("label", nid).replace("\n", "\n")

            # Dimming logic
            if highlight_cluster and cluster != highlight_cluster:
                opacity = 0.15
            else:
                opacity = 1.0

            font_color = f"rgba(255,255,255,{opacity})"
            border_color = color if opacity == 1.0 else f"rgba(100,100,100,{opacity})"
            bg_color = color if opacity == 1.0 else f"rgba(60,60,60,{opacity})"

            node_obj = {
                "id": nid,
                "label": label,
                "shape": shape,
                "color": {
                    "background": bg_color,
                    "border": border_color,
                    "highlight": {"background": color, "border": "#fff"},
                },
                "font": {"color": font_color, "size": 11, "face": "monospace"},
                "size": 18 if ntype == NodeType.PERSON.value else 14,
                "title": self._node_tooltip(nid, data),
            }
            nodes_js.append(node_obj)

        edges_js = []
        for i, (u, v, data) in enumerate(self.G.edges(data=True)):
            etype = data.get("edge_type", "")
            source = data.get("source", "")
            u_cluster = self.G.nodes[u].get("cluster", "")
            v_cluster = self.G.nodes[v].get("cluster", "")

            if highlight_cluster:
                in_cluster = (u_cluster == highlight_cluster and
                              v_cluster == highlight_cluster)
                opacity = 0.9 if in_cluster else 0.08
            else:
                opacity = 0.7

            is_contradiction = etype == "contradicts"
            edge_color = "#ef4444" if is_contradiction else f"rgba(150,150,150,{opacity})"
            dashes = etype in ("contradicts", "linked_to")

            edge_obj = {
                "from": u,
                "to": v,
                "label": etype.upper(),
                "color": {"color": edge_color, "highlight": "#fff"},
                "font": {"color": f"rgba(180,180,180,{opacity})", "size": 9,
                         "strokeWidth": 0},
                "arrows": "to",
                "dashes": dashes,
                "width": 2.5 if is_contradiction else 1.2,
                "title": f"Source: {source}\n{data.get('note', '')}",
            }
            edges_js.append(edge_obj)

        nodes_json = json.dumps(nodes_js, ensure_ascii=False)
        edges_json = json.dumps(edges_js, ensure_ascii=False)

        legend_items = "".join(
            f'<span style="color:{color};margin-right:12px;font-size:12px">'
            f'&#9679; {ntype.replace("_"," ").title()}</span>'
            for ntype, color in _NODE_COLORS.items()
        )

        html = f"""<!DOCTYPE html>
<html><head>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin:0; background:#0a0a0a; font-family:monospace; }}
  #graph {{ width:{width}; height:{height}; border:1px solid #333; border-radius:8px; }}
  #legend {{ padding:8px 12px; color:#ccc; font-size:12px; }}
  #info {{ padding:4px 12px; color:#888; font-size:11px; }}
</style>
</head><body>
<div id="legend">{legend_items}</div>
<div id="graph"></div>
<div id="info">Click and drag to explore. Scroll to zoom. Click a node for details.</div>
<script>
var nodes = new vis.DataSet({nodes_json});
var edges = new vis.DataSet({edges_json});
var container = document.getElementById("graph");
var data = {{ nodes: nodes, edges: edges }};
var options = {{
  physics: {{
    solver: "forceAtlas2Based",
    forceAtlas2Based: {{ gravitationalConstant: -60, centralGravity: 0.008,
                        springLength: 120, springConstant: 0.04, damping: 0.4 }},
    stabilization: {{ iterations: 200 }}
  }},
  interaction: {{ hover: true, tooltipDelay: 100, zoomView: true, dragView: true }},
  layout: {{ improvedLayout: true }}
}};
var network = new vis.Network(container, data, options);
</script>
</body></html>"""
        return html

    def _node_tooltip(self, nid: str, data: dict) -> str:
        lines = [f"ID: {nid}", f"Type: {data.get('node_type','')}",
                 f"Source: {data.get('source','')}"]
        for k, v in data.items():
            if k not in ("node_type", "source", "label", "cluster"):
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
