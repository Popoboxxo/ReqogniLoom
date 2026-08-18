# Pipeline `se-cascade`

Execution mode: loop


**l0-stakeholder** — REPEAT_UNTIL Loop:
  - invoke_subagent("se-requirements", "Stakeholder Needs → formal SN-xxx Requirements")
  - invoke_subagent("se-critic", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l1-requirements** — REPEAT_UNTIL Loop:
  - invoke_subagent("se-requirements", "L1 System Requirements (REQ-L1) from Stakeholder Needs")
  - invoke_subagent("se-critic", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l1-architecture** — REPEAT_UNTIL Loop:
  - invoke_subagent("se-architect", "L1 System White-Box Decomposition (ARCH-L1)")
  - invoke_subagent("se-critic", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l2-requirements** — REPEAT_UNTIL Loop:
  - invoke_subagent("se-requirements", "L2 System Requirements (REQ-L2) derived from L1 Architecture")
  - invoke_subagent("se-critic", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l2-architecture** — REPEAT_UNTIL Loop:
  - invoke_subagent("se-architect", "L2 System White-Box Decomposition (ARCH-L2)")
  - invoke_subagent("se-critic", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen

1. invoke_subagent("se-interface-mgr", "Interface Registry + Propagation Map for L2") → warten bis abgeschlossen

**l3-requirements** — REPEAT_UNTIL Loop:
  - invoke_subagent("se-requirements", "L3 System Requirements (REQ-L3) derived from L2 Architecture")
  - invoke_subagent("se-critic", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l3-architecture** — REPEAT_UNTIL Loop:
  - invoke_subagent("se-architect", "L3 System White-Box Decomposition (ARCH-L3)")
  - invoke_subagent("se-critic", "Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**termination** — Conditional execution:
  - Condition evaluated by se-termination: Per-system leaf/continue decision (respects SE_MIN_DEPTH / SE_MAX_DEPTH)
  Decision agent: se-termination
  If 'continue': Orchestrator spawns new cell at level n+1 with sanitized context
  If 'leaf': Component is final — handover to implementation discipline


**implementation** — REPEAT_UNTIL Loop:
  - invoke_subagent("se-developer", "For each leaf node with domain: software from the termination phase:
- Route to se-junior-developer for trivial leafs (0-1 interfaces, no cross-cutting)
- Route to se-developer for standard leafs (2-4 interfaces)
- Route to se-senior-developer for complex leafs (5+ interfaces, cross-cutting, boundary-level, security/performance-critical)
Implement each leaf against its Black-Box specification and interface contracts from the interface-registry.
Each implementation must reference its req_id and leaf_id in code artifacts.
hardware/mechanics leafs → document as COTS/spec (not implemented).
")
  - invoke_subagent("code-reviewer", "Review / Critic feedback")
  Max iterations: 2 → Erfolg pruefen; bei Abbruch User benachrichtigen


**validation** — Parallel dispatch:
  - invoke_subagent("se-validator", "L1 User-Journey validation")
  - invoke_subagent("se-verifier", "Multi-Level verification")
  - invoke_subagent("se-integration-and-test-manager", "V&V orchestration")

