"""
Gymnasium environment for Sentinel-KG RL training.

Implements the proposal's key architectural elements:
  - Semantic window with relationship-type filtering (Option B, §3.5)
  - Action space: explore_node / request_clearance / submit_evidence_bundle
  - Reward: α·Threat_Confidence + β·Efficiency − γ·Privacy_Penalty
  - Guardrails G2 (scope boundary) and G3 (anti-hallucination)
  - Read-only sandbox (agent cannot modify graph)
"""
from __future__ import annotations

from typing import Any

import gymnasium as gym
import networkx as nx
import numpy as np
from gymnasium import spaces

from .synthetic_graph import NodeType, RelCat

# ── Constants ──────────────────────────────────────────────────────────────

OBSERVATION_DIM = 48
MAX_NEIGHBORS = 20

# Reward weights (proposal §3.3):
# γ >> α  — privacy penalty dominates; threat signal is weak
ALPHA = 0.3   # threat confidence (weak / subjective)
BETA = 0.1    # efficiency (noisy / objective)
GAMMA = 1.0   # privacy penalty (strong / objective)


# ── Semantic Window ────────────────────────────────────────────────────────

class SemanticWindow:
    """Controls what the agent can see (proposal §3.5, Option B)."""

    CLEARANCE_LEVELS: dict[int, set[RelCat]] = {
        0: {RelCat.FINANCIAL, RelCat.CORPORATE},
        1: {RelCat.FINANCIAL, RelCat.CORPORATE, RelCat.PERSONAL},
    }

    def __init__(self, graph: nx.MultiDiGraph, clearance: int = 0):
        self.graph = graph
        self.clearance = clearance

    @property
    def allowed(self) -> set[RelCat]:
        return self.CLEARANCE_LEVELS.get(
            min(self.clearance, max(self.CLEARANCE_LEVELS)), set(RelCat)
        )

    def visible_neighbors(self, node: str) -> list[tuple[str, dict]]:
        """Return (neighbor_id, edge_data) visible under current clearance."""
        allowed = self.allowed
        out: list[tuple[str, dict]] = []
        seen: set[str] = set()

        for _, target, data in self.graph.out_edges(node, data=True):
            cat = data.get("relationship_category")
            if cat in allowed and target not in seen:
                out.append((target, data))
                seen.add(target)

        for source, _, data in self.graph.in_edges(node, data=True):
            cat = data.get("relationship_category")
            if cat in allowed and source not in seen:
                out.append((source, data))
                seen.add(source)

        return out


# ── Node type index mapping ────────────────────────────────────────────────

_NTYPE_IDX = {NodeType.PERSON: 0, NodeType.COMPANY: 1,
              NodeType.TRANSACTION: 2, NodeType.ADDRESS: 3}
_NUM_NTYPES = len(_NTYPE_IDX)


# ── Environment ────────────────────────────────────────────────────────────

class SentinelKGEnv(gym.Env):
    """
    Gymnasium environment wrapping the Sentinel-KG synthetic graph.

    Actions (MultiDiscrete[3, MAX_NEIGHBORS]):
        0: explore_node(neighbor_index)
        1: request_clearance (param ignored)
        2: submit_evidence_bundle (param ignored)

    Observation: Box(48,) float32 in [0, 1]
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        graph: nx.MultiDiGraph,
        threat_seeds: list[str],
        threat_clusters: dict[int, set[str]],
        max_steps: int = 50,
        threat_start_prob: float = 0.7,
    ):
        super().__init__()
        self.graph = graph
        self.threat_seeds = threat_seeds
        self.threat_clusters = threat_clusters
        self.max_steps = max_steps
        self.threat_start_prob = threat_start_prob

        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(OBSERVATION_DIM,), dtype=np.float32
        )
        self.action_space = spaces.MultiDiscrete([3, MAX_NEIGHBORS])

        # precompute normalisation constants
        amounts = [d.get("amount", 0.0) for _, d in graph.nodes(data=True)]
        self._max_amount = max(amounts) if amounts else 1.0
        self._total_nodes = graph.number_of_nodes()
        self._total_edges = graph.number_of_edges()
        self._all_threat_nodes: set[str] = set()
        for s in threat_clusters.values():
            self._all_threat_nodes |= s

        # episode state (set in reset)
        self.current_node: str = ""
        self.visited: set[str] = set()
        self.evidence: list[str] = []
        self.steps: int = 0
        self.window: SemanticWindow | None = None
        self.target_cluster: set[str] = set()
        self._neighbors_cache: list[tuple[str, dict]] = []

    # ── reset / step ───────────────────────────────────────────────────

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)

        if self.np_random.random() < self.threat_start_prob and self.threat_seeds:
            self.current_node = self.np_random.choice(self.threat_seeds)
            for cid, nodes in self.threat_clusters.items():
                if self.current_node in nodes:
                    self.target_cluster = nodes
                    break
        else:
            self.current_node = self.np_random.choice(list(self.graph.nodes))
            self.target_cluster = set()

        self.visited = {self.current_node}
        self.evidence = [self.current_node]
        self.steps = 0
        self.window = SemanticWindow(self.graph, clearance=0)
        self._neighbors_cache = []

        return self._obs(), {"start": self.current_node}

    def step(self, action):
        atype, aparam = int(action[0]), int(action[1])
        reward = 0.0
        terminated = False
        truncated = False
        info: dict[str, Any] = {}
        self.steps += 1

        if atype == 0:
            reward, info = self._do_explore(aparam)
        elif atype == 1:
            reward, info = self._do_clearance()
        elif atype == 2:
            reward = self._submission_reward()
            terminated = True
            info = {"submitted": True, "evidence": len(self.evidence)}

        # per-step efficiency cost
        reward -= BETA * 0.01

        # budget exceeded
        if self.steps >= self.max_steps and not terminated:
            reward -= 0.5
            truncated = True

        return self._obs(), float(reward), terminated, truncated, info

    # ── actions ────────────────────────────────────────────────────────

    def _do_explore(self, idx: int):
        neighbors = self._visible_neighbors()
        if idx >= len(neighbors):
            return -0.05, {"action": "explore", "ok": False}

        target, edata = neighbors[idx]
        self.current_node = target
        self.visited.add(target)
        self.evidence.append(target)

        gt = self.graph.nodes[target].get("_ground_truth", "benign")
        er = edata.get("entity_resolution_confidence", 1.0)

        if gt == "threat":
            r = ALPHA * 0.2
        elif gt == "ambiguous":
            r = 0.0
        else:
            r = -GAMMA * 0.3 if not self._near_threat(target) else -GAMMA * 0.05

        # penalise traversal on low-confidence entity links
        if er < 0.6:
            r -= GAMMA * 0.1

        return r, {"action": "explore", "ok": True, "target": target}

    def _do_clearance(self):
        if self.window is None:
            return -0.02, {"action": "clearance", "ok": False}
        if self.window.clearance >= 1:
            return -0.02, {"action": "clearance", "ok": False, "reason": "already"}
        # simulate HITL approval (80 % grant rate during training)
        if self.np_random.random() < 0.8:
            self.window.clearance = 1
            return -0.05, {"action": "clearance", "ok": True}
        return -0.1, {"action": "clearance", "ok": False, "reason": "denied"}

    def _submission_reward(self) -> float:
        if not self.evidence:
            return -1.0

        threat_count = sum(
            1 for n in self.evidence
            if self.graph.nodes[n].get("_ground_truth") == "threat"
        )
        precision = threat_count / len(self.evidence)
        if self.target_cluster:
            recall = threat_count / max(len(self.target_cluster), 1)
        else:
            recall = 0.0

        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        r = ALPHA * f1 * 10.0

        # efficiency bonus
        r += BETA * (1.0 - self.steps / self.max_steps) * 5.0

        # G3: anti-hallucination — all evidence must be visited
        unvisited = sum(1 for n in self.evidence if n not in self.visited)
        r -= GAMMA * 2.0 * unvisited

        return r

    # ── observation ────────────────────────────────────────────────────

    def _obs(self) -> np.ndarray:
        obs = np.zeros(OBSERVATION_DIM, dtype=np.float32)
        nd = self.graph.nodes[self.current_node]

        # [0:4] current node type one-hot
        ntype = nd.get("node_type", NodeType.PERSON)
        tidx = _NTYPE_IDX.get(ntype if isinstance(ntype, NodeType) else NodeType.PERSON, 0)
        obs[tidx] = 1.0

        # [4] normalised amount (transactions only)
        obs[4] = min(nd.get("amount", 0.0) / max(self._max_amount, 1.0), 1.0)

        # [5] is in evidence
        obs[5] = 1.0 if self.current_node in self.evidence else 0.0

        # [6:10] neighbor counts by relationship category
        neighbors = self._visible_neighbors()
        for _, edata in neighbors:
            cat = edata.get("relationship_category")
            if cat == RelCat.FINANCIAL:
                obs[6] += 1
            elif cat == RelCat.CORPORATE:
                obs[7] += 1
            elif cat == RelCat.PERSONAL:
                obs[8] += 1
        obs[9] = len(neighbors)
        # normalise [6:10]
        for i in range(6, 10):
            obs[i] = min(obs[i] / MAX_NEIGHBORS, 1.0)

        # [10:14] neighbor node-type counts (normalised)
        for nb, _ in neighbors:
            nt = self.graph.nodes[nb].get("node_type", NodeType.PERSON)
            ni = _NTYPE_IDX.get(nt if isinstance(nt, NodeType) else NodeType.PERSON, 0)
            obs[10 + ni] += 1
        for i in range(10, 14):
            obs[i] = min(obs[i] / max(len(neighbors), 1), 1.0)

        # [14] avg transaction amount in neighborhood
        nbr_amounts = [self.graph.nodes[nb].get("amount", 0.0) for nb, _ in neighbors]
        if nbr_amounts:
            obs[14] = min(np.mean(nbr_amounts) / max(self._max_amount, 1.0), 1.0)

        # [15] max transaction amount in neighborhood
        if nbr_amounts:
            obs[15] = min(max(nbr_amounts) / max(self._max_amount, 1.0), 1.0)

        # [16:18] low-confidence edges among neighbors
        low_er = sum(1 for _, ed in neighbors if ed.get("entity_resolution_confidence", 1.0) < 0.6)
        obs[16] = min(low_er / max(len(neighbors), 1), 1.0)

        # [17] unique data sources in neighborhood
        sources = {self.graph.nodes[nb].get("source") for nb, _ in neighbors}
        obs[17] = min(len(sources) / 4.0, 1.0)

        # ── investigation state [18:30] ───────────────────────────────
        obs[18] = self.steps / self.max_steps                       # steps used
        obs[19] = len(self.visited) / max(self._total_nodes, 1)     # nodes visited
        obs[20] = min(len(self.evidence) / 30.0, 1.0)               # evidence count
        obs[21] = float(self.window.clearance if self.window else 0) # clearance level
        obs[22] = 1.0 - self.steps / self.max_steps                 # budget remaining

        # how many visited are threat
        threat_visited = sum(1 for n in self.visited
                             if self.graph.nodes[n].get("_ground_truth") == "threat")
        obs[23] = min(threat_visited / max(len(self.target_cluster), 1), 1.0)

        # how many distinct node types visited
        visited_types = {self.graph.nodes[n].get("node_type") for n in self.visited}
        obs[24] = min(len(visited_types) / _NUM_NTYPES, 1.0)

        # fraction of unvisited neighbors (exploration signal)
        unvisited_nb = sum(1 for nb, _ in neighbors if nb not in self.visited)
        obs[25] = unvisited_nb / max(len(neighbors), 1)

        # ── visited-node histogram [26:42] (4 node_type × 4 source) ──
        for n in self.visited:
            nd2 = self.graph.nodes[n]
            nt = nd2.get("node_type", NodeType.PERSON)
            ni = _NTYPE_IDX.get(nt if isinstance(nt, NodeType) else NodeType.PERSON, 0)
            src = nd2.get("source")
            si = list(DataSource).index(src) if src in DataSource else 0
            if 26 + ni * 4 + si < 42:
                obs[26 + ni * 4 + si] += 1
        total_v = max(len(self.visited), 1)
        obs[26:42] = np.minimum(obs[26:42] / total_v, 1.0)

        # ── graph statistics [42:48] ──────────────────────────────────
        obs[42] = min(self._total_nodes / 1000.0, 1.0)
        obs[43] = min(self._total_edges / 5000.0, 1.0)
        obs[44] = min(len(self._all_threat_nodes) / 100.0, 1.0)
        # 45-47 reserved
        obs[45] = 0.0
        obs[46] = 0.0
        obs[47] = 0.0

        return obs

    # ── helpers ────────────────────────────────────────────────────────

    def _visible_neighbors(self) -> list[tuple[str, dict]]:
        if self.window is None:
            return []
        self._neighbors_cache = self.window.visible_neighbors(self.current_node)[:MAX_NEIGHBORS]
        return self._neighbors_cache

    def _near_threat(self, node: str) -> bool:
        for _, t, _ in self.graph.out_edges(node, data=True):
            if self.graph.nodes[t].get("_ground_truth") == "threat":
                return True
        for s, _, _ in self.graph.in_edges(node, data=True):
            if self.graph.nodes[s].get("_ground_truth") == "threat":
                return True
        return False


# re-export DataSource for observation histogram
from .synthetic_graph import DataSource  # noqa: E402
