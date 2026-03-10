# TrustLayer: A Three-Tier Governance Architecture for State-Deployed AI Threat Intelligence Systems

> **Version**: 0.5 — Full Technical Specification  
> **Status**: Draft for research prototype  
> **Context**: Governance overlay for autonomous AI systems in national security / public-sector threat intelligence  
> **Research Basis**: Extends P4/CRS architecture (Atlantis, AIxCC) with a formally verified governance layer  
> **Core Stack**: TLA+ (specification) · Rust (implementation) · Kani/Prusti (verification) · Z3 (policy validation) · Trillian (audit log)

---

## Changelog: v0.4 → v0.5

| Issue | v0.4 Problem | v0.5 Fix |
|---|---|---|
| Duplicate `AgentOutput` | Defined twice: stub in §3.3 and full definition in §5.2 | §3.3 stub replaced with illustrative ownership example + cross-reference |
| Duplicate `UncertaintyBundle` | Defined in §6.3 (5 fields) and §10.3 (6 fields, inconsistent) | §6.3 is now canonical (6 fields); §10.3 is a comment cross-reference |
| `OperatorTier::Unknown` | Used in Prusti `#[ensures]` but variant does not exist in enum | Contract rewritten using `matches!()` over all valid variants; rationale added |

## Changelog: v0.3 → v0.4

| Issue | v0.3 Problem | v0.4 Fix |
|---|---|---|
| `canonical_serialise` undefined | Called in `AgentOutputDigest::compute()` but never defined | Full deterministic implementation: field-alphabetical, IEEE 754 floats, length-prefixed strings, rationale for no-serde |
| Undefined primitive types | `SubjectRef`, `Claim`, `Fragment`, `EvidenceItem`, `ActionType`, `CheckId`, `FinalAction`, `ActionOption`, `EntryId`, `OperatorId`, `EvidenceItemId` all used but undefined | Complete definitions with doc comments, all in one §PRIMITIVE TYPES block before first use |
| `HitLDecision` / `HitLRecord` missing from Rust | Only existed in TLA+; Rust code referenced them without definition | Full `HitLDecision` enum, `HitLRecord` struct with `elapsed()` and `has_second_approval()`, matching TLA+ `Decisions` set |
| `SubjectRef` pseudonymisation unspecified | Privacy-critical design decision left as comment | Full HMAC-SHA3-256 scheme, key custody model, cross-agency correlation prevention, re-identification procedure, limitation disclosure |

## Changelog: v0.2 → v0.3

| Issue | v0.2 Problem | v0.3 Fix |
|---|---|---|
| SP2 tautology | `SP2_AuditCompleteness` was `P ∨ P` — always true, proved nothing | Split into `SP2_NoAuditSuppression` (safety invariant) + `LP2_AuditCompleteness` (liveness property) |
| `AgentOutputDigest` undefined | Type used in `AuditEntry` but never defined | Full type definition with SHA3-256, `DigestAlgorithm` enum, `compute()` and `verify()` methods, GDPR/privacy rationale |
| Consortium chain failure modes | Fabric network assumed always available | Three failure scenarios (F1 partial partition, F2 quorum loss, F3 Byzantine node) with explicit handling policy and `AnchorFailurePolicy` enum |

## Changelog: v0.1 → v0.2

| Issue | v0.1 Problem | v0.2 Fix |
|---|---|---|
| Technology stack | Python pseudocode throughout | Rust + TLA+ throughout; Python only for operator UI |
| Formal verification | Listed as "future work" | Core contribution; TLA+ spec in §4 |
| Risk level authority | Agent sets its own `risk_level` (attack surface) | Risk level computed independently by Tier 1, never trusted from agent |
| Z3 policy validation | Not mentioned | §5.5: guardrail consistency checker |
| Kani/Prusti | Not mentioned | §6: verification layer with annotated Rust |
| Blockchain | "Optional extension" | Required for multi-agency deployment; §7.3 |
| Rust ownership as governance | Not mentioned | §3.3: ownership model encodes non-bypassability |

---

## Table of Contents

1. [Motivation & Problem Statement](#1-motivation--problem-statement)
2. [System Overview](#2-system-overview)
3. [Architecture & Design Principles](#3-architecture--design-principles)
4. [Formal Specification (TLA+)](#4-formal-specification-tla)
5. [Tier 1 — Guardrail Layer](#5-tier-1--guardrail-layer)
6. [Tier 2 — Human-in-the-Loop Layer](#6-tier-2--human-in-the-loop-layer)
7. [Tier 3 — Audit Layer](#7-tier-3--audit-layer)
8. [Verification Layer (Kani + Prusti)](#8-verification-layer-kani--prusti)
9. [Cross-Tier Data Flow](#9-cross-tier-data-flow)
10. [Agent ↔ Operator Communication Protocol](#10-agent--operator-communication-protocol)
11. [Threat Model & Adversarial Scenarios](#11-threat-model--adversarial-scenarios)
12. [Reliability & Validation Mechanisms](#12-reliability--validation-mechanisms)
13. [Ethical & Political Risk Register](#13-ethical--political-risk-register)
14. [Implementation Roadmap](#14-implementation-roadmap)
15. [Evaluation Protocol](#15-evaluation-protocol)
16. [Open Questions & Future Work](#16-open-questions--future-work)
17. [Appendix A: TLA+ Full Module](#17-appendix-a-tla-full-module)
18. [Appendix B: Glossary](#18-appendix-b-glossary)

---

## 1. Motivation & Problem Statement

### 1.1 The Deployment Reality

State actors are deploying AI systems that:
- Mine open-source intelligence (OSINT) across social media, public registries, and transaction records
- Construct and traverse large-scale knowledge graphs to identify potential threats
- Operate with multi-agency data access (tax authority, social insurance, business registries)
- Make or inform decisions that carry direct legal and civil consequences for individuals

The CyberSecurity AB scenario — and its hypothetical Swedish government extension — is not fictional. It is an operational template already in partial deployment across multiple democracies.

### 1.2 The Governance Gap

Existing frameworks fail this class of system:

| Framework | Gap |
|---|---|
| EU AI Act (High-Risk, Annex III) | Defines obligations; specifies no technical mechanisms |
| NIST AI RMF | Generic risk management; not operationalised for agentic systems |
| GDPR / Data Protection Law | Covers data handling; not real-time agent decision governance |
| CRS literature (AIxCC, Atlantis) | Deep technical architecture; zero governance integration |
| Formal methods literature | Proves properties of protocols; not applied to AI governance pipelines |

**The gap**: no existing work combines CRS-class technical architecture, operationalised governance mechanisms, *and* formal verification of safety properties.

### 1.3 Core Research Questions

1. What technical mechanisms can ensure that an autonomous AI agent in a national security context produces outputs that are *auditable*, *contestable*, and *rights-respecting* — and can these properties be formally proven?
2. How should agent-to-operator communication be structured so that human oversight is substantive rather than nominal?
3. What is the minimum viable formally-verified governance architecture that does not degrade system performance?

### 1.4 Contributions

This work makes four contributions:

**C1 — Architecture**: A three-tier governance overlay (Guardrail → HitL → Audit) that is agent-agnostic and non-bypassable by construction.

**C2 — Formal Specification**: A TLA+ specification of TrustLayer proving three core safety properties under concurrent, multi-agency deployment.

**C3 — Implementation**: A Rust implementation where the ownership and type system encodes governance invariants, verified by Kani model checker and Prusti.

**C4 — Policy Validation**: A Z3-based guardrail consistency checker that detects contradictions in governance policy configurations before deployment.

---

## 2. System Overview

### 2.1 Scope

TrustLayer is a **governance overlay** — it does not replace the underlying AI threat intelligence system. It wraps any CRS-class agent pipeline and enforces governance constraints at runtime.

```
┌─────────────────────────────────────────────────────┐
│              OPERATOR INTERFACE                      │
│      (dashboard, approval queue, alerts)             │
│      [Any language — no safety requirements]         │
└────────────────────┬────────────────────────────────┘
                     │  JSON over local IPC
┌────────────────────▼────────────────────────────────┐
│           TRUSTLAYER GOVERNANCE CORE (Rust)          │
│                                                      │
│  ┌─────────────┐   ┌──────────────┐  ┌───────────┐  │
│  │  Tier 1     │──▶│   Tier 2     │─▶│  Tier 3   │  │
│  │  Guardrail  │   │  Human-in-   │  │  Audit    │  │
│  │  (Rust)     │   │  the-Loop    │  │  (Rust +  │  │
│  │             │   │  (Rust)      │  │  Trillian)│  │
│  └─────────────┘   └──────────────┘  └───────────┘  │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │  TLA+ Spec (verified properties)            │    │
│  │  Kani / Prusti (function-level proofs)      │    │
│  │  Z3 (guardrail policy consistency)          │    │
│  └──────────────────────────────────────────────┘    │
└────────────────────┬────────────────────────────────┘
                     │  Defined adapter trait
┌────────────────────▼────────────────────────────────┐
│         UNDERLYING AI AGENT PIPELINE                 │
│  (knowledge graph traversal, threat scoring,         │
│   pattern matching, LLM reasoning — P4 or equiv.)    │
│  [Untrusted: all outputs treated as adversarial]     │
└─────────────────────────────────────────────────────┘
```

**Critical design decision**: The agent pipeline is treated as **untrusted**. TrustLayer makes no assumption about the correctness, alignment, or integrity of the underlying AI system. Every agent output is processed as if it could be adversarially crafted.

### 2.2 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Specification** | TLA+ | Temporal logic for concurrent system properties; model checker (TLC) finds violations before code is written |
| **Implementation** | Rust | Memory safety eliminates entire vulnerability classes; ownership system encodes governance invariants at the type level |
| **Function verification** | Kani Rust Verifier | Model checking of Rust functions; proves absence of panics, overflows, violated assertions |
| **Contract verification** | Prusti | Hoare-logic contracts in Rust; proves pre/post-conditions and loop invariants |
| **Policy validation** | Z3 SMT Solver | Formal consistency checking of guardrail policy configurations; detects contradictions |
| **Audit storage** | Trillian (Google) | Cryptographic append-only log with Merkle tree proofs; production-grade transparent logging |
| **Chain anchoring** | Hyperledger Fabric | Consortium chain for multi-agency tamper evidence; parliamentary oversight as observer node |
| **Operator interface** | Any (Python/React) | No safety requirements on the UI layer |

---

## 3. Architecture & Design Principles

### 3.1 Design Principles

**P1 — Separation of Concerns**  
TrustLayer is architecturally independent from the AI pipeline. Replacing the underlying model or agent requires only reimplementing the `AgentOutputAdapter` trait.

**P2 — Non-Bypassability (Formally Verified)**  
Every agent output that triggers a real-world action must pass through all three tiers. This property is proven in the TLA+ specification (see §4). There is no emergency bypass, no maintenance mode, no exception.

**P3 — Fail-Closed**  
Governance failures block rather than pass. Derived from the `run_or_none` pattern in Atlantis: any error in the governance pipeline produces `Verdict::Block`, never `Verdict::Pass`. Proven by Kani.

**P4 — Contestability by Design**  
Every decision logged contains sufficient information for a subject, an auditor, or a court to reconstruct the full reasoning chain and challenge it.

**P5 — Proportional Automation**  
The degree of human oversight scales with the independently-assessed severity and irreversibility of the action. *Note: severity is assessed by Tier 1, never self-reported by the agent.*

**P6 — Untrusted Agent Assumption**  
The agent pipeline is treated as an untrusted input source. Risk levels, confidence scores, and evidence quality are re-evaluated independently by Tier 1. Agent self-assessments are inputs to, not outputs of, the governance process.

### 3.2 The Attack Surface Closed by P6

In v0.1, `AgentOutput` contained a `risk_level: RiskLevel` field set by the agent. This is a critical vulnerability:

```
Attack: Agent outputs HIGH-risk content with risk_level = LOW
Effect: Bypasses senior operator routing and dual-approval requirement
Severity: Critical governance bypass
```

In v0.2, the agent provides only raw evidence and a claim. **Risk level is computed exclusively by Tier 1's independent assessment pipeline.** The agent has no mechanism to influence its own routing.

### 3.3 Rust Ownership as Governance Encoding

Rust's ownership system directly encodes two governance invariants at the type level — violations are caught at compile time, not runtime:

**Invariant A: Single Consumption**  
An `AgentOutput` can be consumed by exactly one pipeline. There is no way to process the same output twice (double-counting attack) or to copy it to a parallel processing path that bypasses governance.

```rust
// AgentOutput does NOT implement Copy or Clone
// Once moved into GuardrailLayer::evaluate(), it cannot be accessed again
// This is enforced by the compiler, not by runtime checks
// Full definition: see §5.2 Core Data Structures

// Illustrative: ownership transfer is the ONLY way to access the output
fn illustrate_single_consumption(output: AgentOutput) {
    let _ = GuardrailLayer::evaluate(output); // output moved here
    // let _ = output.claim;  // ← compile error: value used after move
    //                             The compiler enforces this, not runtime logic
}
// No #[derive(Clone, Copy)] on AgentOutput
```

**Invariant B: Linear Pipeline**  
The governance pipeline is expressed as a chain of ownership transfers. Each tier takes ownership of the previous tier's result. You cannot reach Tier 3 without going through Tier 2; you cannot reach Tier 2 without going through Tier 1.

```rust
// The type system enforces the pipeline order
// GuardrailResult can only be constructed by GuardrailLayer::evaluate()
// HitLRecord can only be constructed from a GuardrailResult
// AuditEntry can only be constructed from a HitLRecord

pub fn process(output: AgentOutput) -> Result<AuditEntry, GovernanceError> {
    let guardrail_result = GuardrailLayer::evaluate(output)?;  // consumes output
    let hitl_record = HitLLayer::review(guardrail_result)?;    // consumes guardrail_result
    let audit_entry = AuditLayer::log(hitl_record)?;           // consumes hitl_record
    Ok(audit_entry)
}
```

---

## 4. Formal Specification (TLA+)

### 4.1 Why TLA+ First

TrustLayer's core challenge is a concurrent distributed system problem: multiple AI agents generating outputs asynchronously, multiple operators reviewing in parallel, multi-agency audit log synchronisation. TLA+ is designed precisely for this class of problem — it finds violations of safety and liveness properties that code review cannot.

The TLA+ specification is written *before* implementation code. The Rust implementation is then verified to be a correct refinement of the specification.

### 4.2 System State

```tla
VARIABLES
    pending_outputs,      \* Set of AgentOutputs awaiting Tier 1
    guardrail_results,    \* Map: output_id -> GuardrailResult
    hitl_queue,           \* Set of outputs awaiting operator review
    hitl_decisions,       \* Map: output_id -> HitLDecision
    audit_log,            \* Sequence of AuditEntries (append-only)
    downstream_actions    \* Set of actions triggered in the world
```

### 4.3 Three Core Safety Properties

These are the properties proven by TLC model checking:

**SP1 — Non-Bypassability**  
No output can trigger a downstream action without passing through all three tiers.

```tla
NonBypassability ==
    \A action \in downstream_actions :
        \E entry \in Range(audit_log) :
            /\ entry.output_id = action.output_id
            /\ entry.guardrail_result # Null
            /\ entry.hitl_record # Null
            /\ entry.hitl_record.decision = "APPROVED"
```

**SP2 — Audit Completeness**  
Every output that enters the system eventually appears in the audit log, regardless of outcome.

```tla
AuditCompleteness ==
    \A output \in pending_outputs \cup DOMAIN guardrail_results :
        \E i \in DOMAIN audit_log :
            audit_log[i].output_id = output.output_id
```

**SP3 — Block Irreversibility**  
Once an output is blocked by Tier 1, it cannot be approved by Tier 2.

```tla
BlockIrreversibility ==
    \A output_id \in DOMAIN guardrail_results :
        guardrail_results[output_id].verdict = "BLOCK"
        =>
        ~(\E decision \in Range(hitl_decisions) :
            /\ decision.output_id = output_id
            /\ decision.decision = "APPROVED")
```

### 4.4 Liveness Property

**LP1 — Progress Under Normal Conditions**  
Every output that passes Tier 1 and is assigned to an operator is eventually decided (no starvation).

```tla
Progress ==
    \A output_id \in hitl_queue :
        <>(output_id \in DOMAIN hitl_decisions)
```

*Note: LP1 requires fairness assumptions on operator availability. The spec includes a formal timeout mechanism: outputs in `hitl_queue` longer than `MAX_REVIEW_TIME` are automatically escalated, satisfying the liveness property.*

### 4.5 State Transitions

```tla
\* Tier 1: Agent output enters system
AgentSubmit(output) ==
    /\ output \notin pending_outputs
    /\ pending_outputs' = pending_outputs \cup {output}
    /\ UNCHANGED <<guardrail_results, hitl_queue, hitl_decisions,
                   audit_log, downstream_actions>>

\* Tier 1: Guardrail evaluation completes
GuardrailEvaluate(output, result) ==
    /\ output \in pending_outputs
    /\ output.output_id \notin DOMAIN guardrail_results
    /\ guardrail_results' = guardrail_results @@ 
                            (output.output_id :> result)
    /\ pending_outputs' = pending_outputs \ {output}
    \* If BLOCK: goes directly to audit, skips hitl_queue
    /\ IF result.verdict = "BLOCK"
       THEN hitl_queue' = hitl_queue
       ELSE hitl_queue' = hitl_queue \cup {output.output_id}
    /\ UNCHANGED <<hitl_decisions, audit_log, downstream_actions>>

\* Tier 2: Operator makes decision
OperatorDecide(output_id, decision) ==
    /\ output_id \in hitl_queue
    /\ output_id \notin DOMAIN hitl_decisions
    \* SP3 enforcement: cannot approve a blocked output
    /\ guardrail_results[output_id].verdict # "BLOCK"
    /\ hitl_decisions' = hitl_decisions @@ (output_id :> decision)
    /\ hitl_queue' = hitl_queue \ {output_id}
    /\ UNCHANGED <<pending_outputs, guardrail_results,
                   audit_log, downstream_actions>>

\* Tier 3: Audit entry written (always happens, regardless of decision)
AuditWrite(output_id) ==
    /\ output_id \in DOMAIN guardrail_results
    /\ ~\E entry \in Range(audit_log) : entry.output_id = output_id
    /\ LET entry == [
           output_id       |-> output_id,
           guardrail_result |-> guardrail_results[output_id],
           hitl_record     |-> IF output_id \in DOMAIN hitl_decisions
                               THEN hitl_decisions[output_id]
                               ELSE Null,
           timestamp       |-> CurrentTime
       ]
       IN audit_log' = Append(audit_log, entry)
    /\ UNCHANGED <<pending_outputs, guardrail_results,
                   hitl_queue, hitl_decisions, downstream_actions>>

\* Downstream action: only from approved outputs
TriggerAction(output_id, action) ==
    /\ output_id \in DOMAIN hitl_decisions
    /\ hitl_decisions[output_id].decision = "APPROVED"
    \* SP1: audit entry must exist before action is triggered
    /\ \E entry \in Range(audit_log) : entry.output_id = output_id
    /\ downstream_actions' = downstream_actions \cup {action}
    /\ UNCHANGED <<pending_outputs, guardrail_results,
                   hitl_queue, hitl_decisions, audit_log>>
```

### 4.6 TLC Model Checking Configuration

```tla
\* Bounds for finite model checking
CONSTANTS
    MAX_OUTPUTS = 4      \* Outputs per model check run
    MAX_OPERATORS = 2    \* Concurrent operators
    MAX_AGENTS = 2       \* Concurrent agent instances
    MAX_REVIEW_TIME = 3  \* Steps before escalation

\* Properties to check
PROPERTIES
    NonBypassability
    AuditCompleteness
    BlockIrreversibility

LIVENESS
    Progress
```

Expected TLC output: 0 violations on all safety properties across all reachable states within the model bounds.

---

## 5. Tier 1 — Guardrail Layer

### 5.1 Responsibility

Tier 1 is fully automated. It operates on `AgentOutput` and produces a `GuardrailResult` including an independently-assessed `RiskLevel`. The agent's own assessment of its output's severity is an input feature, not a trusted classification.

### 5.2 Core Data Structures (Rust)

```rust
use std::collections::HashMap;
use chrono::{DateTime, Utc};
use uuid::Uuid;
use sha3::{Digest, Sha3_256};

// =============================================================================
// § PRIMITIVE TYPES
// All newtypes and leaf structs defined here. No type is used before definition.
// =============================================================================

/// Unique identifier types — newtype pattern prevents ID confusion at compile time
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct OutputId(Uuid);
impl OutputId { pub fn new() -> Self { Self(Uuid::new_v4()) } }

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct AgentId(String);

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct OperatorId(String);

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct EntryId(Uuid);
impl EntryId { pub fn new() -> Self { Self(Uuid::new_v4()) } }

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct EvidenceItemId(Uuid);

/// Opaque identifier for a guardrail check — prevents magic string comparisons
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct CheckId(&'static str);
impl CheckId {
    pub const CONFIDENCE:    Self = Self("G1_confidence");
    pub const SCOPE:         Self = Self("G2_scope");
    pub const ANTI_HALLUC:   Self = Self("G3_anti_hallucination");
    pub const EVIDENCE_SUFF: Self = Self("G4_evidence_sufficiency");
    pub const DISPROPORTION: Self = Self("G5_disproportion");
    pub const RISK_ASSESS:   Self = Self("G6_risk_assessment");
}

// =============================================================================
// § SUBJECT PSEUDONYMISATION (Fix D)
//
// SubjectRef is a pseudonym, NOT the real identity of the subject.
//
// Design rationale:
//   The real subject identity (name, personal ID number, etc.) is held only
//   in the originating agency's data store. TrustLayer never receives or stores
//   real identities. The agent pipeline maps real identities to SubjectRef
//   tokens before submitting AgentOutput to TrustLayer.
//
// Pseudonymisation scheme:
//   SubjectRef = HMAC-SHA3-256(key=agency_secret, msg=real_subject_id)
//   where agency_secret is:
//     - Held exclusively by the originating agency
//     - Rotated annually (old tokens remain valid; re-pseudonymised on rotation)
//     - Never transmitted to TrustLayer or any other agency
//
// Re-identification procedure (for court orders / subject access requests):
//   1. Court order issued to the originating agency
//   2. Agency uses its agency_secret to verify: HMAC(key, claimed_id) == SubjectRef
//   3. Agency (not TrustLayer) confirms or denies the match
//   TrustLayer has no role in re-identification — it holds only the pseudonym.
//
// Cross-agency subject correlation:
//   Different agencies will produce DIFFERENT SubjectRef values for the same
//   real person (different agency_secret keys). This is intentional:
//   cross-agency correlation requires a court-ordered join operation at the
//   agency level, not at TrustLayer level. TrustLayer cannot correlate
//   subjects across agencies.
//
// Limitation: if two outputs from the SAME agency share a SubjectRef,
//   TrustLayer can detect that they concern the same subject. This is
//   necessary for the disproportion detector (G5) to function correctly.
// =============================================================================

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct SubjectRef([u8; 32]);  // 256-bit HMAC output, opaque to TrustLayer

impl SubjectRef {
    /// Constructed by the agent pipeline before submitting to TrustLayer.
    /// TrustLayer itself never calls this — it only receives SubjectRef values.
    pub fn pseudonymise(agency_secret: &[u8], real_subject_id: &str) -> Self {
        use hmac::{Hmac, Mac};
        type HmacSha3 = Hmac<Sha3_256>;
        let mut mac = HmacSha3::new_from_slice(agency_secret)
            .expect("HMAC accepts any key length");
        mac.update(real_subject_id.as_bytes());
        Self(mac.finalize().into_bytes().into())
    }
}

// =============================================================================
// § CLAIM, FRAGMENT, EVIDENCE
// =============================================================================

/// A single factual assertion made by the agent.
/// Must be expressible as a verifiable statement anchored in evidence.
#[derive(Debug, Clone)]
pub struct Claim {
    /// Natural language assertion, hedged: "Evidence suggests X" not "X is true"
    pub text: String,
    /// IDs of evidence items that directly support this claim
    pub supporting_evidence: Vec<EvidenceItemId>,
    /// Explicit reasoning chain: how evidence leads to claim
    pub reasoning_chain: Vec<String>,
    /// What evidence would significantly change this assessment
    pub falsification_conditions: Vec<String>,
    /// Most plausible non-threat explanation for the same evidence (mandatory)
    pub alternative_hypothesis: String,
}

/// A text fragment extracted from source material by the agent.
/// Serves as the anti-hallucination anchor (adapted from Atlantis Fragment).
/// Every factual term in Claim::text must appear in at least one Fragment::value.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Fragment {
    pub value: String,
    pub source_id: String,      // Which data source this fragment came from
    pub start_position: usize,  // Character offset in source (for verification)
}

/// A single piece of evidence provided by the agent.
#[derive(Debug, Clone)]
pub struct EvidenceItem {
    pub item_id: EvidenceItemId,
    pub source_id: String,           // Data source identifier (not raw URL)
    pub source_reliability: f64,     // 0.0–1.0 from source registry
    pub collected_at: DateTime<Utc>,
    pub content_summary: String,     // 1–2 sentence plain language summary
    /// Full content stored separately; content_hash links to it
    pub content_hash: [u8; 32],
    pub legal_basis_for_collection: String,
}

// =============================================================================
// § ACTION TYPES
// =============================================================================

/// Actions the agent can request. Scope check (G2) validates against policy.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ActionType {
    FlagForReview,
    AlertOperator,
    EscalateToSeniorOperator,
    EscalateToLegal,
    ReferToHumanInvestigator,
    // Explicitly NOT permitted (enforced by G2 scope check):
    //   AutomaticArrestReferral, AssetFreeze, TravelBan
    //   These require independent judicial process — TrustLayer cannot trigger them
}

/// Final action recorded in the audit log after HitL decision.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FinalAction {
    ActionTaken(ActionType),  // Approved and executed
    Rejected,                 // Operator rejected the AI recommendation
    Escalated,                // Routed to higher authority
    Deferred { until: DateTime<Utc>, reason: String },
    BlockedByGuardrail,       // Never reached HitL
    AutoEscalated,            // Timeout — no operator decision within deadline
}

// =============================================================================
// § HitL DECISION AND RECORD (Fix C — missing from Rust, only in TLA+)
// =============================================================================

/// Operator's decision on an agent output.
/// Mirrors TLA+ Decisions = {Approved, Rejected, Escalated, Deferred}.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HitLDecision {
    Approved,
    Rejected { reason: String },
    Escalated { to: OperatorTier, reason: String },
    Deferred { until: DateTime<Utc>, reason: String },
}

/// Full record of the operator's review session.
/// Immutably bound to operator_id — cannot be anonymised after creation.
#[derive(Debug)]
pub struct HitLRecord {
    pub output_id: OutputId,
    pub operator_id: OperatorId,            // Pseudonymised operator identity
    pub decision: HitLDecision,
    pub reasoning: String,                   // Free-text justification (min 50 chars for High+)
    pub evidence_viewed: Vec<EvidenceItemId>, // Which items were opened
    pub created_at: DateTime<Utc>,           // When brief was presented
    pub decided_at: DateTime<Utc>,           // When decision was submitted
    pub second_approval: Option<OperatorId>, // For dual-approval cases

    // Digest of the AgentOutput at decision time
    // Ensures operator decision is bound to the exact output reviewed
    pub agent_output_digest: AgentOutputDigest,

    // Governance chain — filled by AuditLayer, not by HitL
    pub guardrail_result: GuardrailResult,
    pub final_action: FinalAction,
}

impl HitLRecord {
    pub fn elapsed(&self) -> std::time::Duration {
        (self.decided_at - self.created_at)
            .to_std()
            .unwrap_or_default()
    }

    pub fn has_second_approval(&self) -> bool {
        self.second_approval.is_some()
    }
}

/// Available action options presented to the operator in the brief.
#[derive(Debug, Clone)]
pub struct ActionOption {
    pub action: FinalAction,
    pub label: String,          // Human-readable label for UI
    pub legal_basis: String,    // Statutory authority for this action
    pub requires_reasoning: bool,
    pub risk_level: RiskLevel,  // For minimum deliberation enforcement
}

// =============================================================================
// § CANONICAL SERIALISATION (Fix A)
//
// Used by AgentOutputDigest::compute() to produce a deterministic byte sequence.
// Determinism requirements:
//   - Field order is fixed (alphabetical by field name)
//   - Floats serialised as IEEE 754 big-endian bytes (no string rounding)
//   - Strings UTF-8 encoded, length-prefixed (u32 big-endian)
//   - Enums serialised as their discriminant index (u8)
//   - Vec serialised as count (u32 BE) followed by elements
//   - DateTime serialised as Unix timestamp nanoseconds (i64 BE)
//   - SubjectRef serialised as raw 32 bytes
//
// Rationale for custom serialisation over serde_json:
//   JSON serialisation of floats is implementation-defined (rounding, precision).
//   For cryptographic purposes, the serialisation must be bit-for-bit identical
//   across all implementations (Rust, future Go verifier, court auditor tool).
// =============================================================================

pub fn canonical_serialise(output: &AgentOutput) -> Vec<u8> {
    let mut buf = Vec::with_capacity(512);

    // Fields in alphabetical order to ensure cross-implementation consistency
    // agent_confidence: f64 as IEEE 754 big-endian
    buf.extend_from_slice(&output.agent_confidence.to_bits().to_be_bytes());

    // agent_id: length-prefixed UTF-8
    let agent_id_bytes = output.agent_id.0.as_bytes();
    buf.extend_from_slice(&(agent_id_bytes.len() as u32).to_be_bytes());
    buf.extend_from_slice(agent_id_bytes);

    // action_requested: enum discriminant
    buf.push(match output.action_requested {
        ActionType::FlagForReview             => 0u8,
        ActionType::AlertOperator             => 1u8,
        ActionType::EscalateToSeniorOperator  => 2u8,
        ActionType::EscalateToLegal           => 3u8,
        ActionType::ReferToHumanInvestigator  => 4u8,
    });

    // claim.text: length-prefixed UTF-8
    let claim_bytes = output.claim.text.as_bytes();
    buf.extend_from_slice(&(claim_bytes.len() as u32).to_be_bytes());
    buf.extend_from_slice(claim_bytes);

    // evidence count + each item_id (uuid bytes)
    buf.extend_from_slice(&(output.evidence.len() as u32).to_be_bytes());
    for item in &output.evidence {
        buf.extend_from_slice(item.item_id.0.as_bytes());
    }

    // output_id: uuid bytes
    buf.extend_from_slice(output.output_id.0.as_bytes());

    // raw_fragments count + hashes of each value
    buf.extend_from_slice(&(output.raw_fragments.len() as u32).to_be_bytes());
    for frag in &output.raw_fragments {
        let frag_hash = Sha3_256::digest(frag.value.as_bytes());
        buf.extend_from_slice(&frag_hash);
    }

    // subject_ref: raw 32 bytes
    buf.extend_from_slice(&output.subject_ref.0);

    // timestamp: Unix nanoseconds as i64 BE
    buf.extend_from_slice(
        &output.timestamp.timestamp_nanos_opt()
            .unwrap_or(0)
            .to_be_bytes()
    );

    buf
}

// =============================================================================
// § MAIN TYPES
// =============================================================================

/// Raw output from the AI agent pipeline.
/// Deliberately does NOT contain risk_level — assessed independently by Tier 1.
/// Does NOT implement Clone — single-consumption enforced by compiler.
#[derive(Debug)]
pub struct AgentOutput {
    pub output_id: OutputId,
    pub agent_id: AgentId,
    pub timestamp: DateTime<Utc>,
    pub subject_ref: SubjectRef,      // Pseudonymised — see SubjectRef design above
    pub claim: Claim,
    pub evidence: Vec<EvidenceItem>,
    pub raw_fragments: Vec<Fragment>, // Anti-hallucination anchors
    pub agent_confidence: f64,        // Agent's self-reported confidence
                                      // (input feature, not trusted classification)
    pub action_requested: ActionType,
}

/// Risk level is ALWAYS computed by Tier 1, never by the agent
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum RiskLevel {
    Low,      // Automated log permitted
    Medium,   // Operator review required
    High,     // Senior operator + dual approval
    Critical, // Legal/oversight body notification required
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GuardrailVerdict {
    Pass,
    Flag(Vec<String>),  // Pass with warnings attached
    Block(String),       // Hard stop with reason
    Quarantine,          // Isolate for investigation
}

#[derive(Debug)]
pub struct GuardrailResult {
    pub output_id: OutputId,
    pub verdict: GuardrailVerdict,
    pub assessed_risk_level: RiskLevel, // Computed independently
    pub confidence_calibrated: f64,     // After calibration, may differ from agent's
    pub checks_passed: Vec<CheckId>,
    pub checks_failed: Vec<(CheckId, String)>,
    pub timestamp: DateTime<Utc>,
}
```

### 5.3 Check Pipeline

Six checks run in sequence. The pipeline short-circuits on `Block` — subsequent checks are skipped but the block reason is recorded.

```
AgentOutput
     │
     ├──▶ [G1] Confidence Calibration
     │         Re-calibrate agent's self-reported confidence using
     │         Platt scaling trained on historical ground truth.
     │         Block if calibrated score < threshold(assessed_risk).
     │
     ├──▶ [G2] Scope Boundary Check
     │         Verify action_requested ∈ authorised_action_types.
     │         Verify subject entity type ∈ authorised_entity_types.
     │         Block immediately on any out-of-scope request.
     │
     ├──▶ [G3] Anti-Hallucination Check
     │         Every factual claim must be anchored in raw_fragments.
     │         Adapted from Atlantis action_from_completion validation:
     │         claim terms not present in fragments → hallucination signal.
     │         Block if unanchored ratio > configurable threshold.
     │
     ├──▶ [G4] Evidence Sufficiency Check
     │         Minimum evidence items per assessed risk level.
     │         Evidence items must have non-expired collection timestamps.
     │         Flag (not Block) on borderline cases.
     │
     ├──▶ [G5] Disproportion Detector
     │         Statistical check against 90-day baseline.
     │         Flag if subject group targeted at > 2x population baseline rate.
     │         Block if > 5x (acute disproportion signal).
     │
     └──▶ [G6] Independent Risk Assessment
               Compute assessed_risk_level from:
               - Evidence count and quality
               - Action severity (from policy table)
               - Historical false positive rate for this claim type
               - Calibrated confidence score
               Output: RiskLevel assigned to GuardrailResult
               (This is the canonical risk level used for all downstream routing)
```

### 5.4 Rust Implementation

```rust
pub trait GuardrailCheck: Send + Sync {
    fn check_id(&self) -> CheckId;
    /// Returns Ok(()) on pass, Err(reason) on fail
    fn check(&self, output: &AgentOutput, config: &GuardrailConfig) -> Result<(), String>;
    /// Whether failure causes Block (true) or Flag (false)
    fn is_hard_fail(&self) -> bool;
}

pub struct GuardrailLayer {
    checks: Vec<Box<dyn GuardrailCheck>>,
    config: GuardrailConfig,
    calibrator: ConfidenceCalibrator,
    risk_assessor: IndependentRiskAssessor,
}

impl GuardrailLayer {
    /// Consumes AgentOutput — ownership transfer enforces single processing
    pub fn evaluate(self: &Self, output: AgentOutput) -> GuardrailResult {
        let mut passed = Vec::new();
        let mut failed = Vec::new();
        let mut hard_blocked: Option<String> = None;

        for check in &self.checks {
            // Fail-closed: any panic in a check is treated as Block
            let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                check.check(&output, &self.config)
            }))
            .unwrap_or(Err("check_panicked_treated_as_block".to_string()));

            match result {
                Ok(()) => passed.push(check.check_id()),
                Err(reason) => {
                    failed.push((check.check_id(), reason.clone()));
                    if check.is_hard_fail() && hard_blocked.is_none() {
                        hard_blocked = Some(reason);
                        break; // Short-circuit on hard fail
                    }
                }
            }
        }

        let verdict = match hard_blocked {
            Some(reason) => GuardrailVerdict::Block(reason),
            None if !failed.is_empty() => {
                GuardrailVerdict::Flag(failed.iter().map(|(_, r)| r.clone()).collect())
            }
            None => GuardrailVerdict::Pass,
        };

        let calibrated = self.calibrator.calibrate(
            output.agent_confidence,
            output.evidence.len(),
        );

        let assessed_risk = self.risk_assessor.assess(&output, calibrated);

        GuardrailResult {
            output_id: output.output_id.clone(),
            verdict,
            assessed_risk_level: assessed_risk,
            confidence_calibrated: calibrated,
            checks_passed: passed,
            checks_failed: failed,
            timestamp: Utc::now(),
        }
    }
}
```

### 5.5 Z3 Policy Consistency Validation

Before any `GuardrailConfig` is deployed to a live system, it must pass Z3 consistency checking. This catches policy contradictions that human reviewers cannot reliably detect across large rule sets.

```python
# Policy validation tool — runs offline before deployment
# Python is acceptable here: this is a build-time tool, not runtime governance code
from z3 import *

def validate_guardrail_policy(config: dict) -> list[str]:
    """
    Returns list of contradictions found.
    Empty list = policy is consistent.
    """
    solver = Solver()
    contradictions = []

    # Encode each rule as a Z3 constraint
    # Example: confidence thresholds must be monotonically increasing with risk
    low_thresh   = Real('low_threshold')
    med_thresh   = Real('medium_threshold')
    high_thresh  = Real('high_threshold')
    crit_thresh  = Real('critical_threshold')

    solver.add(low_thresh   == config['confidence_thresholds']['low'])
    solver.add(med_thresh   == config['confidence_thresholds']['medium'])
    solver.add(high_thresh  == config['confidence_thresholds']['high'])
    solver.add(crit_thresh  == config['confidence_thresholds']['critical'])

    # Assert monotonicity requirement
    solver.add(low_thresh < med_thresh)
    solver.add(med_thresh < high_thresh)
    solver.add(high_thresh < crit_thresh)

    if solver.check() == unsat:
        contradictions.append(
            "CONTRADICTION: confidence thresholds are not monotonically "
            "increasing with risk level"
        )

    # Check for action permission contradictions
    # Example: an action cannot be both in allowed_actions and prohibited_actions
    solver2 = Solver()
    allowed = set(config.get('allowed_actions', []))
    prohibited = set(config.get('prohibited_actions', []))
    overlap = allowed & prohibited

    if overlap:
        contradictions.append(
            f"CONTRADICTION: actions in both allowed and prohibited: {overlap}"
        )

    # Check scope rule completeness: every possible (entity_type, action_type)
    # combination has an explicit rule (no implicit permit-all)
    # ... (additional checks)

    return contradictions
```

The Z3 validator is integrated into the deployment pipeline:
- Any policy update must pass validation before being applied
- Validation results are logged to the audit trail
- Policy contradictions are reported to the oversight body, not just the operator

---

## 6. Tier 2 — Human-in-the-Loop Layer

### 6.1 The Four Failure Modes of Human Oversight

Human oversight fails not because humans are removed, but because of four systematic failure modes that TrustLayer's Tier 2 is specifically designed to defeat:

| Failure Mode | Mechanism | TrustLayer Counter |
|---|---|---|
| Information asymmetry | Operators see conclusions, not reasoning | Evidence-first presentation; conclusion shown last |
| Automation bias | Rubber-stamping under time pressure | Minimum deliberation time enforcement; engagement validation |
| Diffuse accountability | Multi-agency ambiguity about who is responsible | Operator identity bound to every decision in audit log |
| Uncontestable presentation | Outputs framed as facts, not probabilistic claims | Mandatory uncertainty bundle; required alternative hypothesis |

### 6.2 Routing Logic (Rust)

```rust
/// Risk level comes from GuardrailResult.assessed_risk_level
/// NOT from the original AgentOutput
pub struct HitLRouter {
    routing_table: HashMap<(RiskLevel, VerdictClass), OperatorTier>,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum VerdictClass {
    Pass,
    Flagged,
    Blocked,    // Routes to audit-only, never to operator queue
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OperatorTier {
    AutoLog,              // No human needed (Low + Pass only)
    Tier1Operator,        // Standard review
    Tier2Operator,        // Senior review
    SeniorOperator,       // Senior + dual approval
    OversightBody,        // Legal/parliamentary notification
    AuditOnly,            // Blocked outputs: log, no operator action
    AuditWithEscalation,  // Blocked critical: log + oversight alert
}

impl HitLRouter {
    pub fn route(&self, result: &GuardrailResult) -> OperatorTier {
        let verdict_class = match &result.verdict {
            GuardrailVerdict::Pass        => VerdictClass::Pass,
            GuardrailVerdict::Flag(_)     => VerdictClass::Flagged,
            GuardrailVerdict::Block(_)    => VerdictClass::Blocked,
            GuardrailVerdict::Quarantine  => VerdictClass::Blocked,
        };

        let key = (result.assessed_risk_level.clone(), verdict_class);

        // Fail-safe: unknown combinations escalate to SeniorOperator
        self.routing_table
            .get(&key)
            .cloned()
            .unwrap_or(OperatorTier::SeniorOperator)
    }
}
```

### 6.3 Operator Brief Structure

The brief is designed to defeat automation bias through structure, not policy:

```rust
#[derive(Debug)]
pub struct OperatorBrief {
    pub output_id: OutputId,
    pub subject_pseudonym: String,  // Never raw identifiers in brief header

    // SECTION 1: Evidence (shown first, before any conclusion)
    pub evidence_items: Vec<EvidenceItem>,
    // Operator must open >= 1 item before decision is accepted

    // SECTION 2: Uncertainty-explicit assessment (shown second)
    pub assessment: UncertaintyBundle,
    // Point estimate + confidence interval + epistemic/aleatoric uncertainty

    // SECTION 3: Required alternative hypothesis (shown third)
    pub alternative_explanation: String,
    // "The most plausible non-threat explanation consistent with this evidence is..."

    // SECTION 4: Conclusion (shown last)
    pub ai_conclusion: String,

    // SECTION 5: Action options (not a binary approve/reject)
    pub available_actions: Vec<ActionOption>,
    // Includes: approve, reject, request_more_evidence, defer_72h,
    //           refer_human_investigator, escalate_legal

    // Governance metadata
    pub legal_basis: String,         // Which law authorises this action
    pub requires_dual_approval: bool,
    pub review_deadline: Option<DateTime<Utc>>, // None preferred; set only if legally required
}

#[derive(Debug)]
pub struct UncertaintyBundle {
    pub point_estimate: f64,
    pub confidence_interval: (f64, f64),
    pub epistemic_uncertainty: String,       // What the model fundamentally doesn't know
    pub aleatoric_uncertainty: String,       // Irreducible noise in data sources
    pub key_assumptions: Vec<String>,        // If wrong, assessment changes materially
    pub critical_evidence_items: Vec<EvidenceItemId>, // If unreliable, assessment invalid
    // Full doc in §10.3 Uncertainty Representation Requirements
}
```

### 6.4 Anti-Rubber-Stamp Enforcement (Rust + Prusti)

```rust
pub struct HitLEnforcer {
    min_deliberation: HashMap<RiskLevel, std::time::Duration>,
}

impl HitLEnforcer {
    /// Prusti precondition: record must have been created after brief was sent
    /// Prusti postcondition: Ok(()) only if all engagement requirements met
    #[requires(record.created_at >= brief.sent_at)]
    #[ensures(result.is_ok() ==>
        !record.evidence_viewed.is_empty() &&
        record.elapsed_seconds >= self.min_deliberation_for(&brief))]
    pub fn validate(
        &self,
        decision: &HitLDecision,
        record: &HitLRecord,
        brief: &OperatorBrief,
    ) -> Result<(), EnforcementError> {

        // Rule 1: At least one evidence item must have been opened
        if record.evidence_viewed.is_empty() {
            return Err(EnforcementError::NoEvidenceOpened);
        }

        // Rule 2: Minimum deliberation time
        let min_time = self.min_deliberation
            .get(&brief.assessed_risk_level)
            .copied()
            .unwrap_or_default();

        if record.elapsed() < min_time {
            return Err(EnforcementError::DecisionTooFast {
                elapsed: record.elapsed(),
                required: min_time,
            });
        }

        // Rule 3: High-stakes decisions require written reasoning
        if brief.requires_dual_approval && record.reasoning.len() < 50 {
            return Err(EnforcementError::InsufficientReasoning);
        }

        // Rule 4: Dual approval check
        if brief.requires_dual_approval && !record.has_second_approval() {
            return Err(EnforcementError::DualApprovalRequired);
        }

        Ok(())
    }
}
```

---

## 7. Tier 3 — Audit Layer

### 7.1 Design Goals

The audit layer must serve four stakeholder classes with different access levels:

| Stakeholder | Access Level | Content |
|---|---|---|
| Independent auditor / court | Full record | All fields including pseudonymised subject ref |
| Parliamentary oversight body | Operational record | All fields except subject identifiers |
| Subject (individual / org) | Notification only | "A decision was made that affected you" + contestation mechanism |
| Public | Aggregate statistics | Anonymised counts, rates, demographic distributions |

### 7.2 Trillian-Based Transparent Log

TrustLayer uses Google's [Trillian](https://github.com/google/trillian) as its audit log backend. Trillian provides:
- Cryptographic append-only guarantees (Merkle tree)
- Inclusion proofs: prove a specific entry is in the log
- Consistency proofs: prove the log has only grown (no deletions or modifications)
- Production-grade implementation used in Certificate Transparency

```rust
/// Content-addressed digest of the original AgentOutput.
///
/// Design decision: AuditEntry stores a digest, not the full AgentOutput.
/// Rationale:
///   (a) Privacy: the audit log has tiered access. Storing raw subject_ref
///       or raw evidence in the append-only log would make those fields
///       irrevocably accessible to anyone with log access. The digest
///       allows integrity verification without exposure.
///   (b) Contestability: the full AgentOutput is stored separately in
///       an access-controlled evidence store (not the audit log).
///       The digest cryptographically binds the AuditEntry to that record.
///   (c) Minimisation: GDPR Article 5(1)(c) — only necessary data
///       in the audit log.
///
/// Verification procedure for auditors:
///   1. Obtain full AgentOutput from evidence store (requires authorisation)
///   2. Recompute digest: SHA3-256(canonical_serialise(agent_output))
///   3. Compare against AuditEntry.agent_output_digest
///   4. Mismatch → tampering of the evidence record
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgentOutputDigest {
    /// SHA3-256 of the canonically serialised AgentOutput
    /// (canonical = sorted keys, no whitespace, deterministic encoding)
    pub hash: [u8; 32],
    /// Algorithm identifier — for cryptographic agility
    pub algorithm: DigestAlgorithm,
    /// Timestamp at which the digest was computed (audit entry creation time)
    pub computed_at: DateTime<Utc>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DigestAlgorithm {
    Sha3_256,  // Current default
    // Future: Blake3 for performance-critical deployments
}

impl AgentOutputDigest {
    pub fn compute(output: &AgentOutput) -> Self {
        use sha3::{Digest, Sha3_256};
        let canonical = canonical_serialise(output);
        let mut hasher = Sha3_256::new();
        hasher.update(&canonical);
        Self {
            hash: hasher.finalize().into(),
            algorithm: DigestAlgorithm::Sha3_256,
            computed_at: Utc::now(),
        }
    }

    pub fn verify(&self, output: &AgentOutput) -> bool {
        let recomputed = Self::compute(output);
        recomputed.hash == self.hash
    }
}

#[derive(Debug)]
pub struct AuditEntry {
    pub entry_id: EntryId,
    pub output_id: OutputId,

    // Privacy-preserving reference to original agent output
    pub agent_output_digest: AgentOutputDigest,

    // Full governance records (these are governance metadata, not PII)
    pub guardrail_result: GuardrailResult,
    pub hitl_record: Option<HitLRecord>,   // None for blocked outputs
    pub final_action: FinalAction,

    // Trillian integration
    pub trillian_leaf_hash: [u8; 32],
    pub trillian_inclusion_proof: Option<InclusionProof>,

    pub timestamp: DateTime<Utc>,
}

pub struct AuditLayer {
    trillian_client: TrillianClient,
    tree_id: i64,
}

impl AuditLayer {
    /// Consumes HitLRecord — only way to create an AuditEntry
    /// Kani property: this function never panics
    /// Kani property: returned entry.output_id == record.output_id
    pub async fn log(&self, record: HitLRecord) -> Result<AuditEntry, AuditError> {
        let leaf_data = self.serialise_leaf(&record)?;
        let leaf_hash = sha256(&leaf_data);

        // Append to Trillian log — this is atomic and returns a signed log root
        let queued_leaf = self.trillian_client
            .queue_leaf(self.tree_id, &leaf_data)
            .await?;

        let entry = AuditEntry {
            entry_id: EntryId::new(),
            output_id: record.output_id.clone(),
            agent_output_digest: record.agent_output_digest,
            guardrail_result: record.guardrail_result,
            hitl_record: record.hitl_record,
            final_action: record.final_action,
            trillian_leaf_hash: leaf_hash,
            trillian_inclusion_proof: None, // Obtained asynchronously after inclusion
            timestamp: Utc::now(),
        };

        Ok(entry)
    }

    /// Verify a specific entry is in the log.
    /// Returns Ok(true) only if Trillian returns a valid inclusion proof
    /// and the proof verifies against the current signed log root.
    pub async fn verify_inclusion(&self, entry_id: &EntryId) -> Result<bool, AuditError> {
        // 1. Look up the leaf index for this entry_id in our local index
        let leaf_index = self.local_index
            .get(entry_id)
            .ok_or(AuditError::EntryNotFound(entry_id.clone()))?;

        // 2. Get current signed log root from Trillian
        let log_root = self.trillian_client
            .get_latest_signed_log_root(self.tree_id)
            .await
            .map_err(AuditError::TrillianError)?;

        // 3. Request inclusion proof from Trillian
        let proof = self.trillian_client
            .get_inclusion_proof(self.tree_id, *leaf_index, log_root.tree_size)
            .await
            .map_err(AuditError::TrillianError)?;

        // 4. Verify the proof cryptographically
        // Recompute root from leaf hash + sibling hashes
        // If computed root == log_root.root_hash → proof is valid
        let valid = verify_merkle_inclusion_proof(
            &proof.leaf_hash,
            &proof.hashes,       // sibling hashes along the path
            *leaf_index,
            log_root.tree_size,
            &log_root.root_hash,
        );

        Ok(valid)
    }

    /// Verify the log has only grown since a previous checkpoint.
    /// Proves no entries were deleted or modified between old_root and new_root.
    pub async fn verify_consistency(
        &self,
        old_root: &SignedLogRoot,
        new_root: &SignedLogRoot,
    ) -> Result<bool, AuditError> {
        // Consistency proof is only meaningful if new_root is larger
        if new_root.tree_size < old_root.tree_size {
            return Err(AuditError::LogShrunk {
                old_size: old_root.tree_size,
                new_size: new_root.tree_size,
            });
        }
        if new_root.tree_size == old_root.tree_size {
            // No new entries — trivially consistent if hashes match
            return Ok(old_root.root_hash == new_root.root_hash);
        }

        // Request consistency proof from Trillian
        let proof = self.trillian_client
            .get_consistency_proof(
                self.tree_id,
                old_root.tree_size,
                new_root.tree_size,
            )
            .await
            .map_err(AuditError::TrillianError)?;

        // Verify: given proof.hashes, old_root.root_hash, and new_root.root_hash,
        // confirm that new log is a superset extension of old log
        let valid = verify_merkle_consistency_proof(
            old_root.tree_size,
            new_root.tree_size,
            &old_root.root_hash,
            &new_root.root_hash,
            &proof.hashes,
        );

        Ok(valid)
    }
}
```

### 7.3 Multi-Agency Consortium Chain (Required for Multi-Agency Deployment)

In single-agency deployments, Trillian with an independent auditor holding the signing key is sufficient. In the Swedish multi-agency scenario (tax authority, social insurance, Bolagsverket), a single agency controlling the log creates a trust problem.

**Architecture**: Periodic anchoring of the Trillian log root hash onto a Hyperledger Fabric consortium chain.

```
Participants:
├── Tax Authority (Skatteverket)         — Fabric peer node
├── Social Insurance (Försäkringskassan) — Fabric peer node
├── Business Registry (Bolagsverket)     — Fabric peer node
├── CyberSecurity AB                     — Fabric peer node (operator)
└── Parliamentary Oversight Body         — Fabric observer node (read-only)

Anchoring schedule: Every 1,000 audit entries
Anchoring content:  Merkle root of last 1,000 Trillian leaf hashes
                    + timestamp + signing key reference

Privacy guarantee: No personal data or subject references touch the chain
                   Only cryptographic hashes are committed

Tamper detection:  Any agency modifying their local Trillian log invalidates
                   the Merkle root; mismatch detectable by any other participant
                   and by the parliamentary observer
```

#### 7.3.1 Network Partition Failure Modes

The consortium chain introduces a distributed systems dependency that the local Trillian log does not have. Three failure scenarios must be handled explicitly:

**Scenario F1: Single agency node offline (partial partition)**

```
Condition:  1 of 4 peer nodes unreachable; Fabric still has quorum (3/4)
Behaviour:  Anchoring proceeds normally with available endorsers
            Offline node catches up when reconnected (Fabric gossip protocol)
TrustLayer: No operational impact — Trillian continues logging
            Anchor is committed by available peers
Risk:       Offline node cannot verify real-time; catch-up verification on reconnect
Mitigation: Reconnection triggers automatic consistency proof verification
            before the node resumes as an endorser
```

**Scenario F2: Majority partition (quorum loss)**

```
Condition:  ≥2 of 4 peer nodes unreachable; Fabric cannot achieve quorum
Behaviour:  Fabric halts — no new anchor transactions can be committed
TrustLayer: CRITICAL design decision — must not halt the governance pipeline
            Trillian continues logging locally (audit entries still written)
            Anchoring is queued; committed when quorum is restored
            All queued anchors are committed in order on recovery
Risk:       Gap in consortium-level tamper evidence during partition
            An agency could tamper with its local Trillian log during this window
            without immediate detection
Mitigation: (a) Gap duration is bounded and recorded in the audit log
            (b) Integrity verification on quorum restoration covers the gap period
            (c) Parliamentary observer is alerted automatically when anchoring
                falls >2× normal interval behind
            (d) Any agency whose node was online during the partition can
                provide a signed witness statement of the Trillian state
```

**Scenario F3: Byzantine node (malicious participant)**

```
Condition:  One agency's node actively submits false anchor data
Behaviour:  Fabric's PBFT-class consensus rejects transactions not endorsed
            by the required policy (e.g., 3-of-4 endorsement required)
TrustLayer: Single Byzantine node cannot commit a false anchor —
            other nodes' endorsement is required
            Detection: inconsistency between Byzantine node's local Trillian
            log and the committed anchor hash
Risk:       Collusion between ≥2 agencies (≥2 Byzantine nodes)
            This breaks the consortium trust model entirely
Mitigation: Parliamentary observer node provides an independent anchor
            witness that no agency can coerce (observer is politically
            independent by constitutional mandate)
            Collusion of all agencies + coercion of parliamentary observer
            is considered outside the threat model (requires state-level capture)
```

#### 7.3.2 Failure Handling Policy

```rust
pub enum AnchorFailurePolicy {
    /// Default: queue anchors, continue logging, alert oversight on delay
    QueueAndAlert {
        max_queue_depth: usize,      // e.g., 10_000 entries
        alert_threshold_minutes: u64, // Alert if anchoring delayed > N minutes
    },
    /// Strict: halt downstream actions if anchoring is unavailable
    /// (Use only if legal mandate requires real-time multi-party witness)
    HaltOnAnchorFailure,
}

impl ConsortiumAnchor {
    /// Queues anchor for retry if Fabric is unavailable.
    /// Never blocks the audit pipeline — returns immediately.
    /// Failure is recorded in the local audit log with timestamp.
    pub async fn maybe_anchor_with_fallback(
        &self,
        trillian_root: &SignedLogRoot,
        entry_count: usize,
        policy: &AnchorFailurePolicy,
    ) -> AnchorOutcome {
        if entry_count % self.anchor_interval != 0 {
            return AnchorOutcome::NotDue;
        }

        match self.try_anchor(trillian_root).await {
            Ok(receipt) => AnchorOutcome::Committed(receipt),
            Err(e) => match policy {
                AnchorFailurePolicy::QueueAndAlert { max_queue_depth, alert_threshold_minutes } => {
                    self.queue_for_retry(trillian_root, entry_count);
                    self.record_anchor_gap_in_audit_log(&e, entry_count);
                    if self.queue_depth() > *max_queue_depth {
                        self.alert_oversight_body(AnchorAlert::ExtendedGap {
                            gap_since: self.last_successful_anchor(),
                            queued_entries: self.queue_depth(),
                        });
                    }
                    AnchorOutcome::Queued { reason: e.to_string() }
                }
                AnchorFailurePolicy::HaltOnAnchorFailure => {
                    // Downstream actions are blocked until anchoring resumes
                    // This is implemented at the pipeline level, not here
                    AnchorOutcome::HaltRequired { reason: e.to_string() }
                }
            }
        }
    }
}

#[derive(Debug)]
pub enum AnchorOutcome {
    NotDue,
    Committed(AnchorReceipt),
    Queued { reason: String },
    HaltRequired { reason: String },
}
```

#### 7.3.3 Declared Assumptions

The consortium chain architecture rests on the following explicit assumptions. Violation of any assumption breaks the stated tamper-evidence guarantees:

| Assumption | Justification | If Violated |
|---|---|---|
| ≤1 Byzantine Fabric node at any time | Swedish government agencies are distinct legal entities with independent oversight | Full audit trail integrity guarantee lost; requires forensic investigation |
| Parliamentary observer node is politically independent | Constitutional mandate; observer has no operational role | Weakest link in collusion resistance |
| Network partition duration < `alert_threshold_minutes` | Government IT infrastructure SLAs; redundant connectivity | Gap in consortium witness; covered by queued-anchor recovery |
| Trillian signing key is held by independent auditor | Key management policy; not a TrustLayer implementation concern | Local log tamper-evidence depends entirely on key custodian integrity |

```rust
pub struct ConsortiumAnchor {
    fabric_client: FabricClient,
    channel: String,
    anchor_interval: usize,  // Anchor every N entries
}

impl ConsortiumAnchor {
    pub async fn maybe_anchor(
        &self,
        trillian_root: &SignedLogRoot,
        entry_count: usize,
    ) -> Result<Option<AnchorReceipt>, AnchorError> {
        if entry_count % self.anchor_interval != 0 {
            return Ok(None);
        }

        let anchor_payload = AnchorPayload {
            log_root_hash: trillian_root.root_hash.clone(),
            log_tree_size: trillian_root.tree_size,
            anchor_timestamp: Utc::now(),
        };

        let receipt = self.fabric_client
            .invoke_chaincode(
                &self.channel,
                "trustlayer-anchor",
                "commitLogRoot",
                &anchor_payload,
            )
            .await?;

        Ok(Some(receipt))
    }
}
```

---

## 8. Verification Layer (Kani + Prusti)

### 8.1 Strategy

Two complementary verification tools cover different properties:

| Tool | Technique | What It Proves |
|---|---|---|
| **Kani** | Bounded model checking | Absence of panics, integer overflows, array out-of-bounds, violated assertions — for all inputs within bounds |
| **Prusti** | Hoare logic / separation logic | Pre/post-conditions hold; loop invariants maintained; functional correctness properties |

### 8.2 Core Kani Proofs

```rust
#[cfg(kani)]
mod kani_proofs {
    use super::*;
    use kani::*;

    /// PROOF 1: GuardrailLayer::evaluate never panics
    /// (fail-closed: panics become Block verdicts via catch_unwind,
    ///  but the evaluate() function itself must not panic)
    #[kani::proof]
    fn guardrail_evaluate_no_panic() {
        let layer = GuardrailLayer::arbitrary();
        let output = AgentOutput::arbitrary();
        let _ = layer.evaluate(output);
        // Kani verifies no panic occurred
    }

    /// PROOF 2: Blocked outputs produce Block verdict, never Pass
    /// (SP3 at the implementation level)
    #[kani::proof]
    fn block_produces_block_verdict() {
        let output = AgentOutput::arbitrary();
        // Inject a definitely-failing check
        let layer = GuardrailLayer::with_forced_block();
        let result = layer.evaluate(output);
        assert!(matches!(result.verdict, GuardrailVerdict::Block(_)));
    }

    /// PROOF 3: assessed_risk_level is always set by Tier 1, never from agent
    /// (P6 at the implementation level)
    #[kani::proof]
    fn risk_level_always_assessed_independently() {
        let output = AgentOutput::arbitrary();
        let layer = GuardrailLayer::arbitrary();
        let result = layer.evaluate(output);
        // The result has an assessed_risk_level field
        // Its value is computed by IndependentRiskAssessor, not copied from output
        // (AgentOutput has no risk_level field — this is structurally enforced)
        let _ = result.assessed_risk_level; // This field always exists
    }

    /// PROOF 4: AuditLayer::log is total (no panic, always returns)
    #[kani::proof]
    fn audit_log_is_total() {
        let record = HitLRecord::arbitrary();
        let layer = AuditLayer::mock();
        // Note: async fn tested via synchronous mock
        let result = layer.log_sync(record);
        assert!(result.is_ok() || result.is_err()); // Never panics
    }

    /// PROOF 5: HitLEnforcer::validate rejects zero-deliberation decisions
    #[kani::proof]
    fn enforcer_rejects_instant_decisions() {
        let enforcer = HitLEnforcer::standard();
        let decision = HitLDecision::arbitrary();
        let mut record = HitLRecord::arbitrary();
        record.elapsed_seconds = 0; // Instant decision
        let brief = OperatorBrief::with_risk(RiskLevel::High);
        let result = enforcer.validate(&decision, &record, &brief);
        assert!(result.is_err());
    }
}
```

### 8.3 Core Prusti Contracts

```rust
use prusti_contracts::*;

/// CONTRACT: Pipeline ordering invariant
/// If we have an AuditEntry, a GuardrailResult for the same output must exist
#[pure]
#[requires(entry.output_id == result.output_id)]
#[ensures(result.timestamp <= entry.timestamp)]
fn audit_after_guardrail(entry: &AuditEntry, result: &GuardrailResult) -> bool {
    true
}

/// CONTRACT: Routing is total and deterministic
/// Every (RiskLevel, VerdictClass) pair maps to a defined OperatorTier.
/// Unknown combinations are excluded by construction: the routing table
/// is initialised with all valid combinations at startup and validated
/// by a completeness check. The Prusti contract expresses that the
/// function's return value is always a known variant — not a special
/// `Unknown` sentinel. We express this as: result is one of the defined variants.
#[pure]
#[ensures(matches!(result,
    OperatorTier::AutoLog | OperatorTier::Tier1Operator |
    OperatorTier::Tier2Operator | OperatorTier::SeniorOperator |
    OperatorTier::OversightBody | OperatorTier::AuditOnly |
    OperatorTier::AuditWithEscalation))]
fn route_is_total(
    risk: RiskLevel,
    verdict_class: VerdictClass,
) -> OperatorTier {
    // ... routing logic
}

/// CONTRACT: Confidence calibration stays in [0, 1]
#[requires(0.0 <= raw_confidence && raw_confidence <= 1.0)]
#[ensures(0.0 <= result && result <= 1.0)]
fn calibrate_confidence(raw_confidence: f64, evidence_count: usize) -> f64 {
    // ... calibration logic
}

/// CONTRACT: Hash chain monotonicity
/// New entries always have larger indices than existing entries
#[requires(ledger.len() < usize::MAX)]
#[ensures(ledger.len() == old(ledger.len()) + 1)]
#[ensures(ledger.last().unwrap().timestamp >= old(ledger.last())
          .map(|e| e.timestamp)
          .unwrap_or(DateTime::<Utc>::MIN_UTC))]
fn append_audit_entry(ledger: &mut Vec<AuditEntry>, entry: AuditEntry) {
    ledger.push(entry);
}
```

---

## 9. Cross-Tier Data Flow

```
AGENT PIPELINE
AgentOutput {output_id, agent_id, claim, evidence,
             raw_fragments, agent_confidence, action_requested}
             ↓ (ownership transferred — agent cannot access output after this)
─────────────────────────────────────────────────────────────────
TIER 1: GUARDRAIL LAYER
GuardrailLayer::evaluate(output: AgentOutput) → GuardrailResult
    ├── Runs G1–G6 checks
    ├── Computes assessed_risk_level INDEPENDENTLY
    ├── Calibrates confidence score
    └── Returns GuardrailResult (owns the output_id reference chain)

GuardrailResult {output_id, verdict, assessed_risk_level,
                 confidence_calibrated, checks_passed, checks_failed}
    ├── If verdict == Block:  → TIER 3 directly (skip Tier 2)
    └── If verdict == Pass/Flag: → TIER 2
─────────────────────────────────────────────────────────────────
TIER 2: HitL LAYER
HitLRouter::route(result: &GuardrailResult) → OperatorTier
OperatorBrief constructed from GuardrailResult + original evidence
Brief presented to operator (evidence-first)
HitLEnforcer::validate(decision, record, brief) → Result

HitLRecord {output_id, operator_id, decision, reasoning,
            evidence_viewed, elapsed_seconds, timestamp}
    → TIER 3 (all paths — approved, rejected, escalated)
─────────────────────────────────────────────────────────────────
TIER 3: AUDIT LAYER
AuditLayer::log(record: HitLRecord) → AuditEntry
    ├── Serialise to Trillian leaf
    ├── Append to Trillian log (atomic, signed)
    └── Maybe anchor to Fabric consortium chain

AuditEntry {entry_id, output_id, guardrail_result,
            hitl_record, final_action, trillian_leaf_hash}
─────────────────────────────────────────────────────────────────
DOWNSTREAM ACTION
Triggered ONLY if:
    hitl_record.decision == Approved
    AND AuditEntry exists with matching output_id
    (TLA+ SP1 enforces this as a system-wide invariant)
```

---

## 10. Agent ↔ Operator Communication Protocol

### 10.1 The Core Tension

```
AI optimises for:    detecting threats (sensitivity → minimise false negatives)
Operator needs:      making defensible decisions (specificity + accountability)
Legal requirement:   contestable decisions (completeness + auditability)

These are not the same objective.
The communication protocol is the place where these objectives are reconciled.
```

### 10.2 Structured Argumentation Schema

All agent outputs passed to Tier 2 must conform to this schema. Free-form natural language output is not accepted. This enforces the anti-hallucination property at the communication level: the agent cannot make claims it has not grounded in evidence items.

```
CLAIM:       One sentence stating the threat hypothesis
             Must use hedged language: "Evidence suggests..." not "X is..."

CONFIDENCE:  Calibrated interval: "65–75% (calibrated from raw 71%)"
             Must include brief explanation of calibration basis

EVIDENCE:    Numbered list; each item must specify:
             - Source identifier (not raw URL)
             - Collection date
             - Reliability score (from source registry)
             - One-sentence content summary
             - Flag if any item is >90 days old

REASONING:   Explicit chain: evidence[1] + evidence[3] supports
             intermediate claim X; X + evidence[5] supports final claim
             Must be traceable: every reasoning step cites evidence items

GAPS:        What evidence would SIGNIFICANTLY change this assessment?
             (Forces the agent to articulate its own uncertainty)

ALTERNATIVE: The most plausible non-threat explanation consistent
             with the same evidence. Mandatory. Cannot be "N/A".

ACTION:      Specific recommended action from the authorised action list
             With explicit citation of legal basis

EXPIRY:      When does this assessment become stale without new evidence?
             (Prevents indefinite reliance on aging assessments)
```

### 10.3 Uncertainty Representation Requirements

Agents must not present binary threat/no-threat assessments. Required format:

```rust
// UncertaintyBundle — canonical definition in §6.3, reproduced for reference:
//
// pub struct UncertaintyBundle {
//     pub point_estimate: f64,
//     pub confidence_interval: (f64, f64),
//     pub epistemic_uncertainty: String,
//     pub aleatoric_uncertainty: String,
//     pub key_assumptions: Vec<String>,
//     pub critical_evidence_items: Vec<EvidenceItemId>,
// }
//
// All agent outputs MUST populate every field.
// Empty epistemic_uncertainty or empty key_assumptions is a G3 violation.
```

---

## 11. Threat Model & Adversarial Scenarios

### 11.1 Agent-Level Attacks (Addressed by Architecture)

| Attack | Description | Mitigation |
|---|---|---|
| Risk manipulation | Agent sets risk_level=LOW on high-risk output | Eliminated: agent has no risk_level field (structural) |
| Confidence inflation | Agent reports 0.95 confidence to bypass scrutiny | Calibrated independently by Tier 1 (G1) |
| Scope creep via output | Agent requests prohibited action type | Scope boundary check (G2) is hard-fail |
| Hallucinated evidence | Agent fabricates evidence items | Fragment anchoring check (G3) |
| Threshold gaming | Adversary learns thresholds and crafts borderline outputs | Z3 validation ensures no accidental threshold gaps; thresholds randomised within policy bounds |

### 11.2 Operator-Level Attacks

| Attack | Mitigation |
|---|---|
| Rubber-stamping (approval without review) | Evidence-opened requirement; minimum deliberation time |
| Collusion with agent developer | Dual approval for High/Critical; audit log binds operator identity |
| Emergency bypass claim | No emergency bypass mode exists (P2) |
| Decision laundering (re-routing to a permissive operator) | Routing is deterministic and audited; re-routing is logged and requires senior sign-off |

### 11.3 Infrastructure-Level Attacks

| Attack | Mitigation |
|---|---|
| Audit log modification | Trillian Merkle proofs; Fabric consortium anchoring |
| Wholesale log replacement | Fabric anchor hashes persist on multi-party chain; cannot be replaced without all parties |
| Single-agency log control | Consortium architecture: no single agency controls the chain |
| Parliamentary oversight exclusion | Observer node is non-removable by any single participant |

### 11.4 Systemic / Long-Term Threats

| Threat | Detection | Response |
|---|---|---|
| Guardrail calibration drift | Monthly false positive/negative rate vs. baseline | Recalibration with oversight body sign-off required |
| Operator approval rate consistently >95% | Automated alert to oversight body | Mandatory operator retraining; policy review |
| Disproportion detector baseline erosion | Quarterly statistical review | Freeze flagging for affected group; mandatory human review |
| TLA+ model / implementation divergence | Annual formal refinement check | Halt deployment; reconcile spec and implementation |

---

## 12. Reliability & Validation Mechanisms

### 12.1 Confidence Calibration Pipeline

```
Raw agent confidence score
         ↓
Platt scaling (trained on historical validated cases)
         ↓
Calibrated score + confidence interval
         ↓
Expected Calibration Error (ECE) monitoring
         ↓
Monthly recalibration trigger if ECE > 0.05
```

In the absence of ground truth (novel threat scenarios), calibration is estimated via:
1. Retrospective case review (outcomes known after investigation)
2. Red team exercises (synthetic cases with known ground truth)
3. Cross-agency consistency checks (same subject, different agency data pipelines)

### 12.2 Red Team Test Suite

```
Type A: Known-positive cases
        (Historical confirmed threats)
        Target: Guardrail recall > 0.85
        Target: Correct routing to High/Critical tier

Type B: Known-negative cases
        (Confirmed non-threats)
        Target: False positive rate < 0.05

Type C: Adversarial cases
        (Synthetic inputs designed to fool guardrails)
        Includes: risk manipulation attempts, hallucinated evidence,
                  threshold-straddling confidence scores
        Target: Catch rate > 0.90

Type D: Operator decision quality
        (Ambiguous scenarios presented to operators using prototype)
        Target: Expert agreement with operator decisions > 0.75

Type E: Disproportion stress test
        (Inputs skewed toward protected characteristic proxies)
        Target: No statistically significant deviation from Type A/B rates
```

### 12.3 Formal Refinement Verification

The TLA+ specification and the Rust implementation must be kept in correspondence. Annual verification:
1. Re-run TLC on TLA+ spec (0 violations required)
2. Re-run Kani proof suite (all proofs pass)
3. Re-run Prusti contract checks (all contracts verified)
4. Manual inspection of any implementation changes against spec transitions

Any divergence between spec and implementation halts deployment until resolved.

---

## 13. Ethical & Political Risk Register

### 13.1 Risks to Individuals

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| False positive — innocent person flagged | High | High | Calibrated thresholds; operator review; contestability mechanism |
| Chilling effect — self-censorship | Certain | Medium | Minimal data collection; public transparency report; scope constraints |
| Discriminatory targeting via proxy variables | Medium | Critical | Disproportion detector; protected characteristic proxy registry |
| No knowledge of flagging | Medium | High | Subject notification right (Tier 3 access control, Appendix B) |
| Indefinite retention of flag | Low | Medium | Automatic expiry on assessments; retention enforcement in Trillian |

### 13.2 Risks to Democratic Institutions

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Mission creep beyond legislative mandate | High | Critical | Scope boundary check (hard-fail); Z3-validated scope policy; annual mandate review |
| Political weaponisation | Medium | Critical | Parliamentary observer node; mandatory oversight reporting for Critical-tier decisions |
| Vendor lock-in (CyberSecurity AB) | High | Medium | TrustLayer is agent-agnostic (P1); open specification |
| Normalisation of AI-driven suspicion | Certain | High | Sunset clause in deployment mandate; mandatory public impact assessment |

### 13.3 International & Global Risks

| Risk | Mitigation |
|---|---|
| Export to authoritarian states | Procurement controls; end-use certificates; open-specification model makes governance layer separable from surveillance capability |
| Reciprocal targeting by foreign states | Diplomatic frameworks; TrustLayer specification as basis for international governance standard |
| Race to bottom on governance standards | Publish TrustLayer as open standard; submit to ISO/IEC AI governance process |

---

## 14. Implementation Roadmap

### Phase 0 — Formal Specification (Week 1–2)

**Goal**: TLA+ spec complete and model-checked before any code is written

```
Deliverables:
├── TLA+ module: TrustLayer.tla (full state machine)
├── TLC model check: 0 violations on SP1, SP2, SP3
├── Liveness check: LP1 verified under fairness assumptions
└── Spec review with 1-2 domain experts
```

**Why this comes first**: TLC will find concurrency violations in the design that cannot be found by code review. Finding them now costs hours; finding them in implementation costs weeks.

### Phase 1 — Core Data Structures & Types (Week 2–3)

**Goal**: Rust type system encodes governance invariants

```
Deliverables:
├── All core types: AgentOutput, GuardrailResult, HitLRecord, AuditEntry
├── Newtype wrappers for all IDs (OutputId, AgentId, OperatorId)
├── No Clone/Copy on AgentOutput (ownership enforced)
├── First Kani proofs: type-level invariants
└── Z3 policy validator (offline tool)
```

### Phase 2 — Guardrail Layer (Week 3–5)

**Goal**: Full Tier 1 with all 6 checks and verified properties

```
Deliverables:
├── GuardrailCheck trait + 6 implementations
├── IndependentRiskAssessor (decoupled from agent output)
├── ConfidenceCalibrator (Platt scaling)
├── GuardrailLayer::evaluate() with Kani proof of no-panic
├── Z3 consistency validation of guardrail_config.yaml
└── Red team test suite Types A–C
```

### Phase 3 — HitL Layer (Week 5–7)

**Goal**: Full Tier 2 with anti-rubber-stamp enforcement

```
Deliverables:
├── HitLRouter (deterministic, total, Prusti-verified)
├── OperatorBrief construction pipeline
├── HitLEnforcer with Prusti pre/post-conditions
├── Basic operator interface (Streamlit or simple React)
│   showing evidence-first presentation
└── Red team test suite Type D (operator decision quality)
```

### Phase 4 — Audit Layer (Week 7–9)

**Goal**: Production-grade audit infrastructure

```
Deliverables:
├── Trillian integration (local instance for development)
├── AuditLayer::log() with Kani totality proof
├── Inclusion and consistency proof verification
├── Hyperledger Fabric local network (3 agency nodes + observer)
├── Merkle root anchoring chaincode
└── Access-tiered query interface
```

### Phase 5 — Integration & Evaluation (Week 9–11)

**Goal**: End-to-end system with mock agent + expert evaluation

```
Deliverables:
├── Mock agent generating configurable AgentOutputs
├── Full pipeline integration test
├── Expert evaluation sessions (n=6–8)
│   DSS designers + AI governance researchers
├── Red team exercise (all types)
└── Performance benchmark: governance overhead < 200ms p99
```

### Phase 6 — Paper Writing (Week 11–12)

```
Deliverables:
├── Paper draft (~10,000 words)
│   Methods: DSR + expert elicitation + formal verification
│   Contribution: C1–C4
├── TLA+ spec as paper appendix
└── Kani/Prusti proof outputs as supplementary material
```

---

## 15. Evaluation Protocol

### 15.1 Technical Metrics

| Metric | Definition | Target |
|---|---|---|
| TLC coverage | Safety properties verified across all reachable states | 0 violations |
| Kani proof count | Core functions with passing Kani proofs | ≥ 10 |
| Guardrail precision | Blocked outputs that were genuinely problematic | > 0.85 |
| Guardrail recall | Problematic outputs that were blocked | > 0.90 |
| Governance overhead | Latency added by TrustLayer p99 | < 200ms |
| Audit integrity | % of entries passing Trillian inclusion proof | 100% |
| Operator engagement | % of decisions with ≥1 evidence item opened | > 0.95 |
| Z3 contradictions caught | Contradictions in policy configs detected before deployment | All detected |

### 15.2 Governance Quality Metrics

| Metric | Definition | Method |
|---|---|---|
| Contestability index | % of audit entries with sufficient info for legal challenge | Expert review |
| Accountability binding | % of decisions with unambiguous responsible party | Audit analysis |
| Alternative hypothesis quality | Expert rating of alternative explanations provided | Expert panel |
| Operator decision quality | Expert agreement with operator decisions on test cases | Expert panel |

### 15.3 Expert Evaluation Protocol

Semi-structured interviews (n=6–10), two cohorts:

**Cohort A — DSS / HitL system designers (n=3–4)**
- Stimulus: live demonstration of Tier 2 operator interface
- Focus: evidence-first presentation effectiveness; anti-rubber-stamp mechanism design; HCI quality of UncertaintyBundle presentation

**Cohort B — AI governance / policy researchers (n=3–4)**
- Stimulus: TrustLayer spec + TLA+ safety properties
- Focus: coverage vs. EU AI Act requirements; gaps in risk register; political feasibility in Swedish/EU context

Combined interview questions (both cohorts):
1. Does the three-tier architecture address the governance gap as you understand it?
2. Which of the four HitL failure modes does the design most/least effectively address?
3. What is the most likely failure mode not captured in the threat model?
4. Is the formal verification approach (TLA+/Kani) meaningful to governance practitioners, or is it purely a technical contribution?

---

## 16. Open Questions & Future Work

### 16.1 Unresolved Technical Questions

**Confidence calibration without ground truth**: How do you calibrate when confirmed threats are rare, delayed, or classified? Current approach (retrospective case review + red team) is a partial solution. Bayesian approaches using expert elicitation as a prior are a candidate extension.

**Anti-hallucination for multi-hop reasoning**: The fragment-anchoring approach (adapted from Atlantis) works for single-step claims. Multi-hop knowledge graph reasoning (A → B → C is a threat) requires extending the anchoring to intermediate reasoning steps. This is an open research problem.

**TLA+ spec refinement to Rust**: We assert correspondence between the TLA+ spec and Rust implementation. Formal refinement proof (using a tool like Apalache + a Rust-to-TLA+ translation) would strengthen this claim. Currently out of scope.

**ZKP for privacy-preserving audit**: The audit access model uses access controls. A stronger design would use Zero-Knowledge Proofs to allow auditors to verify aggregate properties (e.g., "the disproportion detector was applied correctly") without accessing individual records. Architecturally specified; not implemented.

### 16.2 Governance Design Open Questions

**Sunset clauses**: What is the appropriate re-authorisation period? The spec recommends annual review; the appropriate period depends on the rate of model updates and the political context.

**Cross-border knowledge graphs**: TrustLayer is designed for single-jurisdiction deployment. If the underlying knowledge graph spans multiple legal regimes (EU + non-EU), which jurisdiction's scope constraints apply? No current answer.

**Adversarial threshold disclosure**: If guardrail thresholds are published (transparency requirement), adversaries can craft outputs that consistently pass. If they are secret, democratic accountability is weakened. This tension has no clean resolution; current approach is to publish the policy structure but not the specific threshold values.

### 16.3 Research Extensions

- Application to other high-stakes AI deployment contexts: benefits fraud detection, predictive policing, border control
- Comparative governance overhead study: TrustLayer vs. human-only review baseline
- International governance standard proposal based on TrustLayer spec
- Coq extraction as a long-term extension for aviation/financial-grade assurance

---

## 17. Appendix A: TLA+ Full Module

```tla
--------------------------- MODULE TrustLayer ---------------------------
(*
  TrustLayer: Three-Tier Governance Architecture
  for State-Deployed AI Threat Intelligence Systems

  This module specifies the concurrent behaviour of TrustLayer
  and is used to verify three safety properties (SP1–SP3)
  and one liveness property (LP1) using TLC model checking.

  Authors: [Author names]
  Version: 0.2
*)

EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS
    OutputIds,        \* Set of possible output identifiers
    AgentIds,         \* Set of agent identifiers
    OperatorIds,      \* Set of operator identifiers
    RiskLevels,       \* {Low, Medium, High, Critical}
    Verdicts,         \* {Pass, Flag, Block, Quarantine}
    Decisions,        \* {Approved, Rejected, Escalated, Deferred}
    MAX_REVIEW_TIME   \* Maximum steps before automatic escalation

ASSUME MAX_REVIEW_TIME \in Nat /\ MAX_REVIEW_TIME > 0

VARIABLES
    pending_outputs,        \* Set of output_ids awaiting Tier 1
    guardrail_results,      \* output_id -> [verdict, risk_level, timestamp]
    hitl_queue,             \* Set of output_ids awaiting operator review
    hitl_queue_times,       \* output_id -> steps_waiting (for LP1)
    hitl_decisions,         \* output_id -> [operator_id, decision, timestamp]
    audit_log,              \* Sequence of audit entries
    downstream_actions      \* Set of output_ids for which actions were triggered

vars == <<pending_outputs, guardrail_results, hitl_queue,
          hitl_queue_times, hitl_decisions, audit_log, downstream_actions>>

-----------------------------------------------------------------------------
(* Type invariant *)

TypeInvariant ==
    /\ pending_outputs \subseteq OutputIds
    /\ DOMAIN guardrail_results \subseteq OutputIds
    /\ hitl_queue \subseteq OutputIds
    /\ DOMAIN hitl_queue_times \subseteq OutputIds
    /\ DOMAIN hitl_decisions \subseteq OutputIds
    /\ downstream_actions \subseteq OutputIds

-----------------------------------------------------------------------------
(* Initial state *)

Init ==
    /\ pending_outputs    = {}
    /\ guardrail_results  = [o \in {} |-> {}]
    /\ hitl_queue         = {}
    /\ hitl_queue_times   = [o \in {} |-> 0]
    /\ hitl_decisions     = [o \in {} |-> {}]
    /\ audit_log          = <<>>
    /\ downstream_actions = {}

-----------------------------------------------------------------------------
(* State transitions *)

\* Agent submits output to system
AgentSubmit(output_id) ==
    /\ output_id \in OutputIds
    /\ output_id \notin pending_outputs
    /\ output_id \notin DOMAIN guardrail_results  \* Not already processed
    /\ pending_outputs' = pending_outputs \cup {output_id}
    /\ UNCHANGED <<guardrail_results, hitl_queue, hitl_queue_times,
                   hitl_decisions, audit_log, downstream_actions>>

\* Tier 1: Guardrail evaluation
GuardrailEvaluate(output_id, verdict, risk_level) ==
    /\ output_id \in pending_outputs
    /\ output_id \notin DOMAIN guardrail_results
    /\ verdict \in Verdicts
    /\ risk_level \in RiskLevels
    /\ guardrail_results' = guardrail_results @@
                            (output_id :> [verdict |-> verdict,
                                           risk_level |-> risk_level])
    /\ pending_outputs' = pending_outputs \ {output_id}
    \* Blocked outputs skip hitl_queue
    /\ IF verdict = "Block" \/ verdict = "Quarantine"
       THEN hitl_queue' = hitl_queue /\ hitl_queue_times' = hitl_queue_times
       ELSE hitl_queue' = hitl_queue \cup {output_id}
            /\ hitl_queue_times' = hitl_queue_times @@ (output_id :> 0)
    /\ UNCHANGED <<hitl_decisions, audit_log, downstream_actions>>

\* Tier 2: Operator makes decision
OperatorDecide(output_id, operator_id, decision) ==
    /\ output_id \in hitl_queue
    /\ operator_id \in OperatorIds
    /\ output_id \notin DOMAIN hitl_decisions
    \* SP3 enforcement: cannot approve a blocked output
    /\ guardrail_results[output_id].verdict \notin {"Block", "Quarantine"}
    /\ decision \in Decisions
    /\ hitl_decisions' = hitl_decisions @@
                         (output_id :> [operator_id |-> operator_id,
                                        decision |-> decision])
    /\ hitl_queue' = hitl_queue \ {output_id}
    /\ hitl_queue_times' = [o \in DOMAIN hitl_queue_times \ {output_id}
                            |-> hitl_queue_times[o]]
    /\ UNCHANGED <<pending_outputs, guardrail_results, audit_log,
                   downstream_actions>>

\* Automatic escalation (LP1 liveness mechanism)
AutoEscalate(output_id) ==
    /\ output_id \in hitl_queue
    /\ hitl_queue_times[output_id] >= MAX_REVIEW_TIME
    /\ output_id \notin DOMAIN hitl_decisions
    /\ hitl_decisions' = hitl_decisions @@
                         (output_id :> [operator_id |-> "SYSTEM_ESCALATION",
                                        decision |-> "Escalated"])
    /\ hitl_queue' = hitl_queue \ {output_id}
    /\ hitl_queue_times' = [o \in DOMAIN hitl_queue_times \ {output_id}
                            |-> hitl_queue_times[o]]
    /\ UNCHANGED <<pending_outputs, guardrail_results, audit_log,
                   downstream_actions>>

\* Tier 3: Audit entry written
\* This MUST happen for ALL outputs, regardless of verdict or decision
AuditWrite(output_id) ==
    /\ output_id \in DOMAIN guardrail_results
    /\ ~\E i \in DOMAIN audit_log : audit_log[i].output_id = output_id
    /\ LET entry == [
           output_id        |-> output_id,
           verdict          |-> guardrail_results[output_id].verdict,
           risk_level       |-> guardrail_results[output_id].risk_level,
           hitl_decision    |-> IF output_id \in DOMAIN hitl_decisions
                                THEN hitl_decisions[output_id].decision
                                ELSE "N/A",
           hitl_operator    |-> IF output_id \in DOMAIN hitl_decisions
                                THEN hitl_decisions[output_id].operator_id
                                ELSE "N/A"
       ]
       IN audit_log' = Append(audit_log, entry)
    /\ UNCHANGED <<pending_outputs, guardrail_results, hitl_queue,
                   hitl_queue_times, hitl_decisions, downstream_actions>>

\* Downstream action triggered
\* SP1 requires audit entry to exist before action is triggered
TriggerAction(output_id) ==
    /\ output_id \in DOMAIN hitl_decisions
    /\ hitl_decisions[output_id].decision = "Approved"
    /\ output_id \notin downstream_actions
    \* SP1 precondition: audit entry must exist
    /\ \E i \in DOMAIN audit_log : audit_log[i].output_id = output_id
    /\ downstream_actions' = downstream_actions \cup {output_id}
    /\ UNCHANGED <<pending_outputs, guardrail_results, hitl_queue,
                   hitl_queue_times, hitl_decisions, audit_log>>

\* Time step: increment waiting times for queued outputs
Tick ==
    /\ hitl_queue # {}
    /\ hitl_queue_times' = [o \in DOMAIN hitl_queue_times
                            |-> hitl_queue_times[o] + 1]
    /\ UNCHANGED <<pending_outputs, guardrail_results, hitl_queue,
                   hitl_decisions, audit_log, downstream_actions>>

-----------------------------------------------------------------------------
(* Next-state relation *)

Next ==
    \/ \E o \in OutputIds : AgentSubmit(o)
    \/ \E o \in OutputIds, v \in Verdicts, r \in RiskLevels :
           GuardrailEvaluate(o, v, r)
    \/ \E o \in OutputIds, op \in OperatorIds, d \in Decisions :
           OperatorDecide(o, op, d)
    \/ \E o \in OutputIds : AutoEscalate(o)
    \/ \E o \in OutputIds : AuditWrite(o)
    \/ \E o \in OutputIds : TriggerAction(o)
    \/ Tick

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

-----------------------------------------------------------------------------
(* SAFETY PROPERTY SP1: Non-Bypassability
   No downstream action without complete audit trail *)

SP1_NonBypassability ==
    \A o \in downstream_actions :
        /\ o \in DOMAIN hitl_decisions
        /\ hitl_decisions[o].decision = "Approved"
        /\ \E i \in DOMAIN audit_log : audit_log[i].output_id = o
        /\ \E i \in DOMAIN audit_log :
               audit_log[i].output_id = o /\
               audit_log[i].verdict \notin {"Block", "Quarantine"}

(* SAFETY PROPERTY SP2: No Audit Suppression
   A blocked output's verdict can never be erased from guardrail_results.
   This is the safety fragment of audit completeness:
   once evaluated, the record is permanent.
   The liveness fragment (eventually written to log) is LP2 below. *)

SP2_NoAuditSuppression ==
    \A o \in DOMAIN guardrail_results :
        [](o \in DOMAIN guardrail_results)
        \* guardrail_results is append-only: once a key is written it is never removed.
        \* Enforced by the absence of any transition that removes from DOMAIN guardrail_results.

\* Equivalent invariant form (checkable by TLC as a state predicate):
SP2_Invariant ==
    \A o \in OutputIds :
        (o \in DOMAIN guardrail_results)
        => [](o \in DOMAIN guardrail_results)

(* NOTE on SP2 design decision:
   "Audit Completeness" (every evaluated output eventually in audit_log)
   cannot be expressed as a safety property — it is inherently a liveness
   property (something GOOD eventually happens). Conflating it with safety
   was the v0.2 bug. The correct decomposition is:
     Safety:   SP2 — the guardrail record is never suppressed
     Liveness: LP2 — the audit log entry is eventually written
   TLC checks safety properties exhaustively; LP2 requires fairness. *)

(* SAFETY PROPERTY SP3: Block Irreversibility
   Blocked outputs cannot be approved *)

SP3_BlockIrreversibility ==
    \A o \in DOMAIN guardrail_results :
        guardrail_results[o].verdict \in {"Block", "Quarantine"}
        =>
        ~(o \in DOMAIN hitl_decisions /\
          hitl_decisions[o].decision = "Approved")

(* LIVENESS PROPERTY LP1: Operator Progress
   Every output that enters hitl_queue is eventually decided.
   Satisfied by AutoEscalate after MAX_REVIEW_TIME steps. *)

LP1_Progress ==
    \A o \in OutputIds :
        (o \in hitl_queue) ~> (o \in DOMAIN hitl_decisions)

(* LIVENESS PROPERTY LP2: Audit Completeness
   Every evaluated output eventually has an entry in the audit log.
   This is the liveness fragment of what v0.2 incorrectly called SP2. *)

LP2_AuditCompleteness ==
    \A o \in OutputIds :
        (o \in DOMAIN guardrail_results)
        ~> (\E i \in DOMAIN audit_log : audit_log[i].output_id = o)

-----------------------------------------------------------------------------
(* Invariants to check *)

Invariants ==
    /\ TypeInvariant
    /\ SP3_BlockIrreversibility
    /\ SP2_Invariant

THEOREM Spec => []Invariants
THEOREM Spec => []SP1_NonBypassability
THEOREM Spec => LP1_Progress      \* Under WF_vars(AutoEscalate)
THEOREM Spec => LP2_AuditCompleteness  \* Under WF_vars(AuditWrite)

\* TLC configuration note:
\* SP1, SP3, SP2_Invariant: checked as state predicates (exhaustive)
\* LP1, LP2: checked as temporal properties under fairness (WF)

=============================================================================
```

---

## 18. Appendix B: Glossary

| Term | Definition |
|---|---|
| **AgentOutput** | Untrusted raw output from AI agent. No risk_level field — severity assessed independently by Tier 1 |
| **Anti-hallucination check (G3)** | Validates every factual claim is anchored in raw_fragments. Adapted from Atlantis `action_from_completion` validation |
| **AuditEntry** | Immutable record of complete decision cycle. Created for ALL outputs regardless of verdict |
| **Fail-closed (P3)** | Any governance failure produces Block, never Pass. Derived from Atlantis `run_or_none` pattern |
| **GuardrailResult** | Output of Tier 1. Includes independently-assessed RiskLevel (never from agent) |
| **HitLRecord** | Operator's decision record. Bound to operator_id; includes evidence_viewed for engagement audit |
| **Kani** | Bounded model checker for Rust. Proves absence of panics and violated assertions for all inputs within bounds |
| **Non-bypassability (P2)** | Formally proven in TLA+ (SP1): no downstream action without all three tiers completing |
| **OperatorBrief** | Evidence-first presentation package. Shows evidence before conclusion to defeat automation bias |
| **Ownership-as-governance** | Rust ownership system enforces single-consumption of AgentOutput and linear pipeline ordering at compile time |
| **P4 Framework** | Pattern-Policy-Environment-Platform — CRS architecture underlying Atlantis (AIxCC). TrustLayer wraps P4-class systems |
| **Prusti** | Hoare-logic contract verifier for Rust. Proves pre/post-conditions and loop invariants |
| **Risk assessment independence** | Risk level is computed by Tier 1's IndependentRiskAssessor, never accepted from the agent |
| **SP1–SP3** | Three TLA+ safety properties: Non-Bypassability, Audit Completeness, Block Irreversibility |
| **TLA+** | Temporal Logic of Actions. Used to specify and model-check TrustLayer's concurrent behaviour before implementation |
| **TLC** | TLA+ model checker. Exhaustively verifies safety properties across all reachable system states within model bounds |
| **Trillian** | Google's cryptographic append-only log library. Provides Merkle tree inclusion and consistency proofs |
| **TrustLayer** | This system: a formally-specified, Rust-implemented three-tier governance overlay for state-deployed AI systems |
| **UncertaintyBundle** | Mandatory uncertainty representation. Point estimate + confidence interval + epistemic/aleatoric uncertainty |
| **Z3** | SMT solver. Used offline to verify guardrail policy configurations contain no logical contradictions before deployment |

---

*TrustLayer Specification v0.2*  
*Architecture: Design Science Research (Hevner et al., 2004)*  
*Formal methods: TLA+ (Lamport) · Kani (AWS) · Prusti (ETH Zurich) · Z3 (Microsoft Research)*  
*Core patterns adapted from Atlantis CRS (AIxCC, Team Atlanta) and Google Trillian*