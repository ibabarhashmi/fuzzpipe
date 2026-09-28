---
name: fuzzpipe-fuzzing
version: 2.2.0
description: >-
  AI-driven, verified-before-confirmed EVM/Solidity invariant fuzzing. Keeps the fuzzpipe
  pipeline (scaffold → 11-procedure invariant discovery → Chimera harness → multi-engine
  campaign → triage → report, with a human invariant-approval checkpoint) and adds a
  counterexample-first tiered ladder (forge → medusa/echidna → eval-gated halmos), a typed
  Invariant IR, and a re-execution VERDICT GATE: nothing is a CONFIRMED finding until its
  auto-lowered Foundry PoC re-compiles, re-executes, and asserts HARM. Everything else is
  SUSPECTED — never reported as a bug. Use when the user wants to fuzz a Solidity protocol,
  set up invariant testing, generate a fuzzing harness, run medusa/echidna, or triage
  fuzzer counterexamples. Triggers on /fuzzpipe-fuzzing, "fuzz this protocol", "set up
  invariant testing", "write fuzz/invariant tests", "run medusa/echidna".
license: MIT
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Skill
metadata:
  domain: smart-contract-security
  engines: forge, medusa, echidna, halmos
  runtime: python3 (stdlib only — no CLI dependencies)
  supersedes: fuzzpipe-fuzzing v0.2
---

# fuzzpipe-fuzzing v2.2 — Verified-Before-Confirmed Invariant Fuzzing Orchestrator

You orchestrate an end-to-end invariant fuzzing workflow for EVM/Solidity protocols. You do
**not** reimplement fuzzers — you drive proven engines (Foundry, Medusa, Echidna, and the
eval-gated Halmos symbolic tier via the Chimera scaffold) and add the intelligence none of them
ship: **deriving invariants, generating the harness, and triaging results into auditor-reviewable
findings — each proven by a re-executed PoC.**

v2.2 keeps everything that made v0.2 strong (the 9-procedure derivation methodology, the human
checkpoint, the Chimera write-once-run-everywhere harness, Foundry + Hardhat support) and
re-implements the back half of the pipeline around a counterexample-first, *verified-before-confirmed*
trust model. It also **fixes every defect that adversarial testing found in v0.2** and **designs in
four robustness guards** (§4). Every fix in this document was validated against the exact inputs that
broke v0.2.

---

## 0. What changed from v0.2 (read this first)

| Area | v0.2 | v2.2 |
|------|------|------|
| **Finding confirmation** | "triage writes a reproducer" (best-effort) | **Verdict gate**: `CONFIRMED` only after the PoC **compiles + re-executes + asserts harm**; else `SUSPECTED`. |
| **Campaign structure** | one engine at a time | **Tiered ladder**: Tier-0 forge smoke → Tier-1 medusa/echidna → Tier-2 halmos (eval-gated). Counterexample at any tier short-circuits to lowering. |
| **Invariant artifact** | a Markdown table (human-only) | Markdown table **+ a typed Invariant IR** (`invariants.json`) consumed by the harness generator and the gate. |
| **Triage arg rendering** | `", ".join(args)` → **crashes** on `bool`/array/tuple (Q2) | **type-aware `sol_literal`** + array/tuple preludes + compile-check (§9, validated). |
| **doctor on a fresh machine** | **uncaught traceback** when a tool is missing (Q1) | every probe guarded → graceful "MISSING → install: …". |
| **Medusa per-invariant runs** | one shared `medusa.json` (cross-contamination) | **per-invariant staged config** targeting only that invariant's harness + its own corpus. |
| **Coverage** | capped by invariant count | **complete by construction**: `gen-handlers` wires every mutating entry point. |
| **False positives** | none measured | **materiality gate** flags dust-only breaks as bad invariants. |

---

## 1. The three pillars

1. **Orchestrate, don't rebuild.** Foundry / Medusa / Echidna / Halmos and the Chimera scaffold
   already exist. You call them; you never write a fuzzer.
2. **CLI = mechanics, Skill = reasoning.** Deterministic steps (scaffold, run, parse, lower,
   re-execute) go through `cli/fuzzpipe`. Judgment (invariants, harness, triage) is the skill's job.
   The CLI never calls the AI.
3. **Nothing is a finding until a PoC re-executes.** A campaign break is a *candidate*. It becomes a
   **CONFIRMED** finding only after its lowered Foundry PoC **compiles, re-runs the specific break,
   and asserts the harm**. Everything else is **SUSPECTED** and is never reported as a bug.

---

## 2. Pipeline stages

```
AUDITOR: contracts + docs + optional threat model / seed invariants
   │
[Stage 0] threat model + seeds        (auto-generated when none given)
[Stage 1] scaffold        → CLI → Chimera recon/ skeleton (engine-discoverable paths)
[Stage 2] derive invariants → 11 gated procedures + 7 adversarial personas → TABLE + typed IR
   2b       adversarial personas + FP filters + coverage critic
            └─► AUDITOR APPROVAL CHECKPOINT (mandatory human gate)
[Stage 3] generate harness → fill the Chimera recon/ (Setup/Targets/Properties/BeforeAfter)
   3b       gen-handlers  → complete ABI-driven handler surface (coverage by construction)
[Stage 4] run the LADDER  → CLI → Tier-0 forge → Tier-1 medusa‖echidna (parallel) → Tier-2 halmos*
            └─ counterexample at any tier short-circuits ▼
[Stage 5] VERDICT GATE    → CLI lowers CE → forge build → forge test → harm assert → CONFIRMED / SUSPECTED
[Stage 6] report          → CONFIRMED findings (each w/ re-executing PoC) + honest SUMMARY
* Tier-2 halmos is eval-gated (FUZZPIPE_SYMBOLIC=1), critical bounded SAFETY/CORRECTNESS only.
```

Per-run state lives **inside each target** at `<target>/.fuzzpipe/`: `state.json`, `invariants.md`
(human table), `invariants.json` (typed IR), `threatmodel.md`, `runs/`, `corpus/`, `poc/`, `findings/`.

---

## 3. Stage 0 — Threat model + seeds

If auditor provides seeds/threat model, use them. Otherwise auto-generate:
- Scan contracts for entry points, state vars, privileged functions, external dependencies
- Build threat model from 7 adversarial personas (see §5)
- Seed invariants from protocol-type priors (AMM, lending, staking, governance, etc.)

Output: `.fuzzpipe/threatmodel.md` + seeded `invariants.md` (if any).

---

## 4. Stage 1 — Scaffold (CLI)

```
fuzzpipe scaffold --target <path> [--offline]
```

- Vendors Chimera + setup-helpers (non-fatal if offline)
- Writes recon/ stubs: Setup.sol, TargetFunctions.sol, Properties.sol, BeforeAfter.sol, CryticTester.sol, CryticToFoundry.sol
- Sets up remappings.txt, foundry.toml (for Hardhat)

---

## 5. Stage 2 — Derive invariants

### 5.1 Procedures (11, gated)

1. **State consistency** — pre/post conditions on state vars
2. **Functional correctness** — inputs → expected outputs
3. **Authorization** — who can call what, privilege escalation
4. **Solvency** — assets ≥ liabilities, no fund loss
5. **Stateful sequence** — multi-tx invariants (e.g., deposit→withdraw)
6. **Cross-contract** — invariants spanning deployed instances
7. **Economic/MEV/oracle** — price manipulation, sandwich, oracle drift
8. **Reentrancy/read-only reentrancy** — callback safety
9. **ERC/standard compliance** — transfer hooks, permit, etc.
10. **Protocol-specific** — AMM invariant, lending health factor, staking rewards
11. **Governance/upgrade** — timelock, multisig, admin powers

Each procedure has: trigger, template, acceptance criteria. You must fill the template.

### 5.2 Adversarial personas (7 concurrent)

| Persona | Goal |
|---------|------|
| **Attacker** | drain funds, break accounting |
| **Griefers** | DoS, brick contracts, spike gas |
| **MEV searcher** | sandwich, front-run, back-run |
| **Oracle manipulator** | price drift, stale data |
| **Governance attacker** | proposal injection, timelock bypass |
| **Upgrade exploiter** | storage collision, init theft |
| **Coverage critic** | finds untested code paths |

Each persona reviews the invariant table, proposes additions/modifications. Fan out concurrently; merge results.

### 5.3 FP-reduction filters (apply to every invariant)

1. **Grounding** — code ref + origin + harm description + compiling impl
2. **Two-sided/tolerance** — allowable deviation (e.g., ±1 wei)
3. **Materiality** — dust threshold below which break = bad invariant
4. **Adversarial refutation** — try to disprove; if it holds, keep
5. **Classify-before-confirm** — tag as safety/liveness/correctness/auth

### 5.4 Coverage critic

- Scans `invariants.json` against Solidity surface
- Flags untested entry points / state vars / privileged fns
- Requires justified waiver in `.fuzzpipe/coverage-waivers.json`

### 5.5 Machine-enforced completeness gate

```
fuzzpipe ir coverage-audit --target <path>
```

Exit 2 = gap found. Fix Stage 2 or add waiver.

### 5.6 Output

- `invariants.md` — human table (auditor reviews)
- `invariants.json` — typed IR (machine contract)

**MANDATORY AUDITOR APPROVAL** before Stage 3.

---

## 6. Stage 3 — Generate harness

```
fuzzpipe gen-handlers --target <path>
```

- Scans ABI of every deployed target in Setup.sol
- Emits `TargetFunctionsAuto.sol` with one clamped, multi-actor, revert-tolerant handler per mutating entry point
- Splices into inheritance chain (no duplicate-definition conflicts)
- Privileged fns get admin + attacker variants
- Struct/tuple args → `_build_<fn>` hook for skill to fill

### 6.1 You only tune

- Clamp bounds (CLAMP_CAP, ETH_CAP, MAX_ARR)
- Setup: deploy contracts, fund actors, seed address book
- Invariant assertions: `property_INV_<ID>() public returns (bool)`

---

## 7. Stage 4 — Run ladder (CLI)

```
fuzzpipe run --target <path> [--max-tier 2] [--jobs N] [--workers N] [--no-parallel]
```

### 7.1 Tier-0: Foundry (smoke)

- `forge test --match-contract CryticToFoundry`
- Fast, deterministic, catches trivial breaks

### 7.2 Tier-1: Medusa + Echidna (parallel)

- Per-invariant Medusa shards (isolated corpus, staged config)
- Echidna cross-check
- Concurrent via `proc.run_many_bounded`
- First CE short-circuits escalation (in-flight jobs finish)

### 7.3 Tier-2: Halmos (eval-gated)

- `FUZZPIPE_SYMBOLIC=1`
- Critical bounded SAFETY/CORRECTNESS only (non-economic, tier_hint ≥ 2)
- Symbolic execution for deep paths

### 7.4 Budgets

- Tier-0: 60s (configurable in `.fuzzpipe/config.json`)
- Tier-1: 600s default (`--budget`)
- Tier-2: 900s default

---

## 8. Stage 5 — Verdict gate

Every break → `triage` → `verify`

### 8.1 Triage

```
fuzzpipe triage --target <path>
```

- Reads Medusa failing sequences (flat + all shards)
- Version-tolerant `medusa_parse` (warns on drift, never silently drops)
- Type-aware rendering: `bool`/`uint`/`address`/`array`/`tuple` compile
- Emits `MedusaReproducers.t.sol` with `test_repro_<N>`
- Runs `forge build` + `forge test` (re-execution)
- CE without harm assert = SUSPECTED

### 8.2 Verify (single PoC)

```
fuzzpipe verify --target <path> --poc <file> --test <name> --marker <INV-ID>
```

- Compile → re-execute specific break (marker in revert) → assert harm
- **Three gates**: compiles + reproduces specific break + asserts harm
- `asserts_harm` rejects: trivial (`assertEq(1,1)`), comment-only markers, tautologies

---

## 9. Stage 6 — Report

- `CONFIRMED` findings: each with re-executing PoC in `findings/`
- `SUSPECTED` breaks: listed with reason (no re-execution / no harm assert / compile fail)
- Honest SUMMARY: "held under budget at X% coverage" — never "safe"

---

## 10. CLI reference (mechanical layer)

```
fuzzpipe doctor          [-t <t>]         # toolchain check (never crashes)
fuzzpipe init            -t <t>           # create .fuzzpipe/
fuzzpipe scaffold        -t <t> [--offline]
fuzzpipe verify-harness  -t <t>           # preflight: engine sees harness
fuzzpipe build           -t <t>           # forge build (+ hardhat compile)
fuzzpipe ir  put|get|list|validate|candidates|coverage-audit -t <t> [--file]
fuzzpipe run             -t <t> [--max-tier N] [--engine E] [--budget S] [--jobs N] [--workers N] [--no-parallel]
fuzzpipe triage          -t <t>           # lower breaks + verdict gate
fuzzpipe verify          -t <t> --poc <f> --test <name> --marker <INV-ID>
fuzzpipe materiality     -t <t> --test <fn> --material <amt>
fuzzpipe coverage        -t <t> -e medusa # exit 2 = uncovered
fuzzpipe status          -t <t>
fuzzpipe selftest        [-v]             # 127 tests, zero deps
```

Environment (single `FUZZPIPE_*` namespace):
- `FUZZPIPE_SYMBOLIC=1` → Halmos
- `FUZZPIPE_SWEEP_AMOUNT` → materiality sweep amount
- `FUZZPIPE_LOG=json` → machine-readable logs

---

## 11. Robustness guards (validated against v0.2 breakage)

| Guard | Prevents |
|-------|----------|
| **R1** — env drift | tier silently disabled |
| **R5** — undiscovered harness | reads as `UNTESTED` |
| **R6** — real wall-clock timeout | engine hangs |
| **R7** — marker-keyed reproduction | any-revert mistaken for CE |

---

## 12. Regression suite

```
fuzzpipe selftest
```

127 tests, 7 skipped. Zero deps. Golden fixture: `examples/vulnerable-vault/` (4 seeded bugs, forge-only).

---

## 13. Support matrix

`fuzzpipe doctor` prints the single source of truth.

- Python 3.11+ (CLI, stdlib only)
- `forge` **required** (verdict gate)
- `medusa` + `crytic-compile` / `echidna` optional (Tier-1)
- `halmos` optional (Tier-2, eval-gated)
- `slither` optional (dictionary seeds)
- Node/`npx` for Hardhat only
- Hardhat v2 and v3 (v3 needs `crytic-compile >= 0.4`)

---

## 14. Install the skill

```bash
cp -r skill/fuzzpipe-fuzzing ~/.claude/skills/fuzzpipe-fuzzing
# or ~/.cursor/skills/fuzzpipe-fuzzing
```

Composes six Trail of Bits skills: `property-based-testing`, `entry-point-analyzer`, `harness-writing`, `coverage-analysis`, `fuzzing-dictionary`, `fuzzing-obstacles`. Install them into your assistant's skills directory.