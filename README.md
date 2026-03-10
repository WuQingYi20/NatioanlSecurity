# Sentinel-KG

Guardrailed AI agents for national security knowledge graph traversal.

## System Architecture

```
                          ┌─────────────────────────────────┐
                          │        CyberSecurity AB         │
                          │    (Untrusted External Feed)    │
                          │  International OSINT KG         │
                          └──────────────┬──────────────────┘
                                         │ one-way queries
                                         │ (obfuscated, batched)
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        AIR-GAPPED GOVERNMENT ENVIRONMENT                     │
│                                                                              │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────┐ ┌──────────────────┐   │
│  │ Skatteverket │ │Försäkrings-  │ │Arbetsför-      │ │  Bolagsverket    │   │
│  │ (Tax)        │ │kassan (Ins.) │ │medlingen (Emp.)│ │  (Companies)     │   │
│  └──────┬───────┘ └──────┬───────┘ └───────┬────────┘ └────────┬─────────┘  │
│         │                │                  │                   │            │
│         └────────────────┴──────────────────┴───────────────────┘            │
│                          │                                                   │
│                          ▼                                                   │
│              ┌───────────────────────┐                                       │
│              │   Entity Resolution   │  personnummer/org.nr matching         │
│              │   Pipeline            │  + probabilistic disambiguation       │
│              └───────────┬───────────┘                                       │
│                          │                                                   │
│                          ▼                                                   │
│         ┌────────────────────────────────┐                                   │
│         │      Sovereign Knowledge       │  ~100M+ nodes, ~1B+ edges        │
│         │           Graph                │  Neo4j / JanusGraph / custom      │
│         └────────────────┬───────────────┘                                   │
│                          │                                                   │
│    ┌─────────────────────┼──────────────────────┐                            │
│    │          SEMANTIC WINDOW (§3.5)             │                            │
│    │  Relationship-type filter per investigation │                            │
│    │  + agent can request_clearance() to widen   │                            │
│    └─────────────────────┬──────────────────────┘                            │
│                          │                                                   │
│    ┌─────────────────────▼──────────────────────┐                            │
│    │            RL AGENT ENSEMBLE                │                            │
│    │                                             │                            │
│    │  Agent 1 ──┐                                │                            │
│    │  Agent 2 ──┼── GRPO scoring ── diverge? ──┐ │                            │
│    │  Agent 3 ──┤                    agree? ──┐│ │                            │
│    │  Agent N ──┘                             ││ │                            │
│    │                                          ││ │                            │
│    │  Local LLM (Llama/Mistral)               ││ │                            │
│    │  + domain-scoped LoRA adapters            ││ │                            │
│    │  + read-only sandbox (no writes)          ││ │                            │
│    └──────────────────────────────────────────┼┼─┘                            │
│                                               ││                             │
│                      ┌────────────────────────┘│                             │
│                      │                 ┌───────┘                             │
│                      ▼                 ▼                                     │
│              ┌──────────────┐  ┌──────────────┐                              │
│              │  Evidence     │  │  Escalation  │                              │
│              │  Bundle       │  │  (disagreement)                            │
│              └──────┬───────┘  └──────┬───────┘                              │
│                     │                 │                                      │
│    ┌────────────────▼─────────────────▼────────────────────┐                 │
│    │              GUARDRAIL LAYER (Runtime)                 │                 │
│    │                                                        │                 │
│    │  G1 Confidence Calibration (Platt scaling)             │                 │
│    │  G2 Scope Boundary Check                               │                 │
│    │  G3 Anti-Hallucination (evidence → real DB entry)      │                 │
│    │  G4 Evidence Sufficiency                               │                 │
│    │  G5 Disproportion Detector (bias check)                │                 │
│    │  G6 Independent Risk Assessment (agent self-report     │                 │
│    │     discarded)                                         │                 │
│    └────────────────────────┬───────────────────────────────┘                 │
│                             │                                                │
│    ┌────────────────────────▼───────────────────────────────┐                 │
│    │          HUMAN-IN-THE-LOOP (Operator)                   │                 │
│    │                                                         │                 │
│    │  Evidence shown FIRST, conclusion hidden                │                 │
│    │  Mandatory alternative hypothesis                       │                 │
│    │  Risk-tiered routing:                                   │                 │
│    │    Low    → standard analyst                            │                 │
│    │    Medium → senior analyst + written reasoning           │                 │
│    │    High   → senior analyst + deliberation delay          │                 │
│    │    Critical → dual independent approval                 │                 │
│    └────────────────────────┬───────────────────────────────┘                 │
│                             │                                                │
│    ┌────────────────────────▼───────────────────────────────┐                 │
│    │              AUDIT TRAIL                                │                 │
│    │  Every action, state, decision logged                   │                 │
│    │  Accessible to oversight body + Riksdag                 │                 │
│    └─────────────────────────────────────────────────────────┘                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Actors

| Actor | Role | Trust Level |
|---|---|---|
| **RL Agents** | Traverse KG, build evidence bundles | Untrusted — all outputs validated |
| **Guardrail Layer** | Automated checks (G1–G6), independent risk scoring | System component |
| **Operators** | Review evidence, approve/reject, document reasoning | Trusted but monitored for bias |
| **Oversight Body** | Audit access, halt authority | Independent authority |
| **Riksdag** | Sunset renewal (3-year cycle), annual reporting | Democratic accountability |
| **CyberSecurity AB** | External threat intelligence feed | Untrusted — hypothesis source only |
| **Entity Resolution Pipeline** | Cross-agency identity stitching | Preprocessing — confidence-scored |

## Key Actions

```
Agent Actions (P4-derived protocol)        Governance Actions
─────────────────────────────               ──────────────────
explore_node(entity_id)                     G1-G6 runtime checks
  └─ must be within scope                   risk_level independently assessed
                                            evidence → DB verification
request_clearance(level)
  └─ widens semantic window                 Operator reviews evidence-first
  └─ requires human approval                writes reasoning (Medium+)
                                            dual approval (Critical)
submit_evidence_bundle()
  └─ anti-hallucination validated           Audit logs every transition
  └─ mandatory ALTERNATIVE field            Oversight body can halt pipeline
```

## RL Training Loop

```
              ┌──────────────────────────────────────┐
              │                                      │
   Observe    │    Act         Environment    Reward │   Update
   state ────►│── action ────► sandbox ────► calc. ──┼──► LoRA
              │                   │                  │
              │              read-only               │
              │              (no writes)             │
              └──────────────────────────────────────┘

Reward = α·Threat_Confidence + β·Efficiency − γ·Privacy_Penalty
         ▲ weak signal          ▲ noisy        ▲ strong signal
         (biased labels)        (objective)    (objective binary)
```

## Data Flow: CyberSecurity AB

```
Sweden ──query(obfuscated)──► AB API
                                │
AB response ──► Ingestion Adapter ──► Guardrail G1-G6 ──► Operator
                     │
              stored separately
              (never merged into
               sovereign KG)

Trust posture: low-trust hypothesis generator
Architecture: plugin, not dependency — disconnection must be painless
```
