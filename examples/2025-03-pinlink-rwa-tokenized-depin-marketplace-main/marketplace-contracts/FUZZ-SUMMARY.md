# Fuzzing summary — PinLink RWA/DePIN marketplace (2025-03 pinlink)

Run with the `QuillAudits-fuzzing` skill (v2.2) driving **real Foundry invariant fuzzing + Medusa
1.5.1** (crytic-compile 0.4.1). Scope: `pinlinkShop.sol`, `streams.sol`, `FractionalAssets.sol`,
`CentralizedOracle.sol`.

## Approach — orchestrate, don't rebuild
This project ships a strong Foundry invariant suite (multi-actor, cheatcode-based). Per the skill's
first pillar, the run **reused the project's own fuzzing harness** (`test/pinlinkShop/invariants/
helper.sol`) rather than rebuilding it, and the skill contributed additional invariants on top.

## What was run (real engines)

| Engine (tier) | What | Result |
|---------------|------|--------|
| Foundry invariant (Tier-0) | the project's own 9-invariant suite | **9/9 held** (~50k calls) |
| Foundry invariant (Tier-0) | 2 **skill-contributed** invariants layered on the same harness | **2/2 held** (~50k calls) |
| **Medusa** (Tier-1) | fresh Chimera harness for `CentralizedOracle` | **held** (round-trip + staleness, 300k limit) |

## Invariants (`.fuzzpipe/invariants.json`)
| ID | Statement | Source | Verdict |
|----|-----------|--------|---------|
| INV-ASSET-SOLVENCY | shop's physical ERC1155 balance == Σ credited staking (excl. withdrawal proxy) | skill (discovered) | held |
| INV-REWARD-SOLVENCY | Σ pending rewards <= shop USDC balance | project suite | held |
| INV-BALANCE-CONSISTENCY | per account `staked == listed + unlisted` | project suite | held |
| INV-FEE-BOUND-NO-RESTING-PIN | `purchaseFeePerc <= MAX_FEE_PERC` and PIN never rests in the shop | skill (discovered) | held |
| INV-ORACLE-ROUNDTRIP | a USD↔TOKEN round trip never creates value (both directions round down) | skill (discovered) | held |
| INV-ORACLE-STALENESS | a stale price converts to 0, never a nonzero misprice | skill (threat-model) | held |

Skill-contributed harnesses: `test/pinlinkShop/invariants/skillInvariants.t.sol` (asset-solvency +
fee/PIN), `test/recon/CryticTester.sol` (Medusa oracle harness).

## Result — NO-CE-IN-BUDGET (held; **not** "safe")
All invariants held across the Foundry invariant campaigns and the Medusa oracle campaign. This is an
honest empirical result: the protocol is well-built and its accounting (balance consistency, reward
conservation, physical asset solvency, PIN flow, oracle rounding) is self-consistent under the tested
sequences. It does not clear classes these invariants don't model (e.g. cross-asset interactions,
multi-token reward races, or oracle-owner trust).

## How to reproduce
```bash
D=examples/2025-03-pinlink-rwa-tokenized-depin-marketplace-main/marketplace-contracts
cd $D && forge install foundry-rs/forge-std openzeppelin/openzeppelin-contracts   # populate libs
forge test --match-contract Invariant                       # project's own suite (Tier-0)
forge test --match-contract PinlinkShop_SkillInvariants     # skill-contributed invariants
cd - && export PATH="$HOME/Library/Python/3.9/bin:$PATH"
python3 cli/fuzzpipe run --target $D --engine medusa --budget 60   # Medusa on the oracle harness
```
