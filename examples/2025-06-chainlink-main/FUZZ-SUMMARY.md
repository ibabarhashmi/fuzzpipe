# Fuzzing summary — Chainlink Rewards / BUILD Claim (2025-06 chainlink)

Run with the `QuillAudits-fuzzing` skill (v2.2) driving **real Foundry invariant fuzzing**. Scope:
`BUILDClaim.sol` (Merkle-proof token claims, seasons, linear unlock, loyalty/early-claim) and
`BUILDFactory.sol` (project registry, deposit/withdraw accounting, season config).

## Approach — orchestrate, don't rebuild
This is a Chainlink-grade codebase that ships an exhaustive Foundry invariant harness (a multi-project,
multi-user, multi-season `Handler` with Merkle proofs and time skips). Per the skill's first pillar,
the run **reused that harness** and the skill contributed additional invariants on top, rather than
rebuilding the Merkle/season machinery.

## What was run (real engine)

| Suite | Invariants | Result |
|-------|-----------|--------|
| Project's own (`BUILDFactory.invariants`, `BUILDClaim.invariants`) | 9 | **9/9 held** — 256 runs × 500 depth = **128,000 calls each** (~12 min) |
| **Skill-contributed** (`SkillInvariants.t.sol`) | 2 | **2/2 held** — 64 runs × 250 depth = 16,000 calls each |

## Invariants (`.fuzzpipe/invariants.json`)
| ID | Statement | Source | Verdict |
|----|-----------|--------|---------|
| INV-CLAIM-SOLVENCY | claim balance never below total claimable + withdrawable | project suite | held |
| INV-CLAIM-CAP | a user cannot claim more than their max (except the documented early-claim redistribution) | project suite | held |
| INV-NO-UNDERFLOW | `deposited + refunded >= withdrawn + allocated` (max-available never underflows) | project suite | held |
| INV-CROSS-PROJECT-ISOLATION | each BUILDClaim holds only its own token; no cross-project bleed | **skill** (proc 10) | held |
| INV-WITHDRAWN-CONSERVATION | `totalWithdrawn <= totalDeposited + totalRefunded` | **skill** (proc 3) | held |
| INV-GETTERS-NOREVERT | public getters never revert | project suite | held |

Skill-contributed harness: `test/invariants/SkillInvariants.t.sol` (extends the project's
`BaseInvariant`).

## Result — NO-CE-IN-BUDGET (held; **not** "safe")
All 11 invariants held. This is an honest empirical result on a heavily-tested protocol: the
deposit/withdraw/claim accounting, the max-available/underflow math, cross-project isolation, and
inflow/outflow conservation are all self-consistent under the fuzzed sequences. It does not clear
classes these invariants don't model (e.g. Merkle-proof edge cases the off-chain server gates, or the
loyalty/early-claim redistribution math beyond the cap invariant).

## How to reproduce
```bash
D=examples/2025-06-chainlink-main
cd $D
forge test --match-path 'test/invariants/BUILD*'        # the project's own 9 invariants
forge test --match-contract SkillInvariants             # the 2 skill-contributed invariants
```
