"""
Training loop for Sentinel-KG RL agent.

Produces a reward curve comparing rule-based baseline vs PPO.

Usage:
    python -m rl_training.train [--timesteps 50000] [--output reward_curve.png]
"""
from __future__ import annotations

import argparse
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

from .synthetic_graph import SyntheticGraphGenerator, GraphConfig
from .environment import SentinelKGEnv
from .agent import RuleBasedAgent, create_ppo_agent, evaluate_agent


class RewardLogger(BaseCallback):
    """Periodically evaluate the PPO agent and log mean rewards."""

    def __init__(self, eval_env: SentinelKGEnv, eval_freq: int = 2048,
                 n_eval: int = 20, verbose: int = 0):
        super().__init__(verbose)
        self.eval_env = eval_env
        self.eval_freq = eval_freq
        self.n_eval = n_eval
        self.timesteps: list[int] = []
        self.mean_rewards: list[float] = []
        self.std_rewards: list[float] = []
        self.mean_precisions: list[float] = []

    def _on_step(self) -> bool:
        if self.n_calls % self.eval_freq == 0:
            res = evaluate_agent(self.model, self.eval_env, self.n_eval)
            self.timesteps.append(self.num_timesteps)
            self.mean_rewards.append(res["mean_reward"])
            self.std_rewards.append(res["std_reward"])
            self.mean_precisions.append(res["mean_precision"])
            if self.verbose:
                print(f"  [{self.num_timesteps:>6d}]  reward={res['mean_reward']:+.3f}  "
                      f"precision={res['mean_precision']:.2f}")
        return True


def main():
    parser = argparse.ArgumentParser(description="Sentinel-KG RL Training")
    parser.add_argument("--timesteps", type=int, default=50_000,
                        help="Total PPO training timesteps")
    parser.add_argument("--eval-episodes", type=int, default=50,
                        help="Episodes for final evaluation")
    parser.add_argument("--eval-freq", type=int, default=2048,
                        help="Evaluate every N training steps")
    parser.add_argument("--output", type=str, default="reward_curve.png",
                        help="Output image path")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # ── 1. Generate synthetic graph ────────────────────────────────────
    print("Generating synthetic knowledge graph...")
    gen = SyntheticGraphGenerator(GraphConfig(seed=args.seed))
    graph = gen.generate()
    threat_seeds = gen.get_threat_seed_nodes()
    threat_clusters = gen.get_all_threat_node_clusters()

    total_threat = sum(len(c) for c in threat_clusters.values())
    print(f"  Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}")
    print(f"  Threat clusters: {len(threat_clusters)}, threat nodes: {total_threat}")

    # ── 2. Create environments ─────────────────────────────────────────
    train_env = SentinelKGEnv(graph, threat_seeds, threat_clusters, max_steps=50)
    eval_env = SentinelKGEnv(graph, threat_seeds, threat_clusters, max_steps=50)

    # ── 3. Rule-based baseline ─────────────────────────────────────────
    print("\nEvaluating rule-based baseline...")
    rule_agent = RuleBasedAgent()
    baseline = evaluate_agent(rule_agent, eval_env, n_episodes=args.eval_episodes)
    print(f"  Reward:    {baseline['mean_reward']:+.3f} ± {baseline['std_reward']:.3f}")
    print(f"  Precision: {baseline['mean_precision']:.2f}")
    print(f"  Steps:     {baseline['mean_steps']:.1f}")

    # ── 4. Train PPO ───────────────────────────────────────────────────
    print(f"\nTraining PPO for {args.timesteps} timesteps...")
    callback = RewardLogger(eval_env, eval_freq=args.eval_freq, n_eval=20, verbose=1)
    ppo = create_ppo_agent(train_env, verbose=0)
    ppo.learn(total_timesteps=args.timesteps, callback=callback)

    # ── 5. Final evaluation ────────────────────────────────────────────
    print("\nFinal PPO evaluation...")
    ppo_result = evaluate_agent(ppo, eval_env, n_episodes=args.eval_episodes)
    print(f"  Reward:    {ppo_result['mean_reward']:+.3f} ± {ppo_result['std_reward']:.3f}")
    print(f"  Precision: {ppo_result['mean_precision']:.2f}")
    print(f"  Steps:     {ppo_result['mean_steps']:.1f}")

    # ── 6. Plot ────────────────────────────────────────────────────────
    print(f"\nSaving reward curve → {args.output}")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    ts = np.array(callback.timesteps)
    mr = np.array(callback.mean_rewards)
    sr = np.array(callback.std_rewards)
    mp = np.array(callback.mean_precisions)

    # reward curve
    ax1.plot(ts, mr, color="#6366f1", linewidth=2, label="PPO")
    ax1.fill_between(ts, mr - sr, mr + sr, alpha=0.2, color="#6366f1")
    ax1.axhline(baseline["mean_reward"], color="#ef4444", linestyle="--",
                linewidth=2, label=f"Rule-based ({baseline['mean_reward']:+.2f})")
    ax1.axhspan(baseline["mean_reward"] - baseline["std_reward"],
                baseline["mean_reward"] + baseline["std_reward"],
                alpha=0.08, color="#ef4444")
    ax1.set_ylabel("Mean Episode Reward", fontsize=12)
    ax1.set_title("Sentinel-KG: PPO vs Rule-Based Agent", fontsize=14)
    ax1.legend(fontsize=11)
    ax1.grid(True, alpha=0.3)

    # precision curve
    ax2.plot(ts, mp, color="#10b981", linewidth=2, label="PPO threat precision")
    ax2.axhline(baseline["mean_precision"], color="#ef4444", linestyle="--",
                linewidth=2, label=f"Rule-based ({baseline['mean_precision']:.2f})")
    ax2.set_xlabel("Training Timesteps", fontsize=12)
    ax2.set_ylabel("Threat Precision", fontsize=12)
    ax2.set_ylim(-0.05, 1.05)
    ax2.legend(fontsize=11)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(args.output, dpi=150)
    print("Done.")


if __name__ == "__main__":
    main()
