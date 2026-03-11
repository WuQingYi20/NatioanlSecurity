"""
Agents for Sentinel-KG RL environment.

- RuleBasedAgent: deterministic heuristic baseline
- create_ppo_agent: stable-baselines3 PPO wrapper
- evaluate_agent: unified evaluation across agent types
"""
from __future__ import annotations

import numpy as np
from stable_baselines3 import PPO

from .environment import SentinelKGEnv, MAX_NEIGHBORS


class RuleBasedAgent:
    """
    Heuristic baseline: follow financial/corporate edges, prefer unvisited
    company and transaction nodes, submit when enough evidence collected.
    """

    def __init__(self, submit_after: int = 15, min_evidence: int = 5):
        self.submit_after = submit_after
        self.min_evidence = min_evidence

    def predict(self, obs: np.ndarray, env: SentinelKGEnv) -> np.ndarray:
        steps = int(obs[18] * env.max_steps)
        evidence_count = int(obs[20] * 30)

        # submit if enough evidence or about to run out of budget
        if evidence_count >= self.min_evidence and steps >= self.submit_after:
            return np.array([2, 0])
        if steps >= env.max_steps - 2:
            return np.array([2, 0])

        neighbors = env._visible_neighbors()

        # no visible neighbors → request clearance
        if not neighbors:
            return np.array([1, 0])

        # score each neighbor
        best_idx, best_score = 0, -1.0
        for i, (nid, edata) in enumerate(neighbors):
            nd = env.graph.nodes[nid]
            score = 0.0
            ntype = nd.get("node_type")

            # prefer companies and transactions (financial investigation)
            if ntype is not None and ntype.value in ("company", "transaction"):
                score += 2.0
            # prefer financial edges
            cat = edata.get("relationship_category")
            if cat is not None and cat.value == "financial":
                score += 1.0
            # strongly prefer unvisited
            if nid not in env.visited:
                score += 3.0
            # prefer high-confidence entity links
            er = edata.get("entity_resolution_confidence", 1.0)
            score += er

            if score > best_score:
                best_score = score
                best_idx = i

        return np.array([0, best_idx])


def create_ppo_agent(env: SentinelKGEnv, **kwargs) -> PPO:
    """Create a PPO agent with defaults tuned for graph-traversal."""
    defaults = dict(
        policy="MlpPolicy",
        env=env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        ent_coef=0.01,
        clip_range=0.2,
        verbose=0,
        policy_kwargs=dict(net_arch=[64, 64]),
    )
    defaults.update(kwargs)
    return PPO(**defaults)


def evaluate_agent(
    agent: RuleBasedAgent | PPO,
    env: SentinelKGEnv,
    n_episodes: int = 50,
) -> dict:
    """Run agent for n_episodes, return statistics."""
    rewards: list[float] = []
    steps_list: list[int] = []
    threat_precisions: list[float] = []

    for _ in range(n_episodes):
        obs, _ = env.reset()
        total_reward = 0.0
        done = False
        ep_steps = 0

        while not done:
            if isinstance(agent, RuleBasedAgent):
                action = agent.predict(obs, env)
            else:
                action, _ = agent.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(action)
            total_reward += reward
            ep_steps += 1
            done = terminated or truncated

        rewards.append(total_reward)
        steps_list.append(ep_steps)

        # compute threat precision of collected evidence
        if env.evidence:
            tp = sum(1 for n in env.evidence
                     if env.graph.nodes[n].get("_ground_truth") == "threat")
            threat_precisions.append(tp / len(env.evidence))
        else:
            threat_precisions.append(0.0)

    return {
        "mean_reward": float(np.mean(rewards)),
        "std_reward": float(np.std(rewards)),
        "mean_steps": float(np.mean(steps_list)),
        "mean_precision": float(np.mean(threat_precisions)),
        "min_reward": float(np.min(rewards)),
        "max_reward": float(np.max(rewards)),
    }
