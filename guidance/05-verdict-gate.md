# Guidance 05 - The Verdict Gate (lowering, re-execution, harm)

> Pipeline Stage 5. This is the trust core of v2.1: **nothing is a CONFIRMED finding until its
> lowered Foundry PoC compiles, re-executes the specific break, and asserts the harm.** Everything
> else is SUSPECTED and is never reported as a bug. Read together with `guidance/04`.

## Why a gate at all

A fuzzer flagging a "failing property" is a *candidate*, not a finding. Three things routinely make
a candidate a false alarm:

1. the failing sequence does not lower to compiling Solidity (bad arg types, missing state);
2. the replay reverts for a reason **unrelated** to the invariant (an unrelated `require`, an OOG,
   arithmetic panic) - the property never actually broke;
3. the break is a *mechanism* ("the call was possible") with no demonstrable *consequence*.

The gate rejects all three by construction. A candidate becomes CONFIRMED only when it survives.

## The five checks (in order)

`fuzzpipe triage` / `fuzzpipe verify` run these; you supply the judgment and the harm assertion.

1. **Parse** the failing sequence (version-tolerant reader; bool/int/array/tuple values preserved).
2. **Lower** it to a standalone Foundry test with **type-aware rendering**: scalars inline, dynamic
   arrays/tuples via a `new T[](n)` memory prelude. A value that cannot be rendered does not crash
   the tool - it produces Solidity that fails the next step.
3. **`forge build`** the PoC - it MUST compile. Non-compiling ⇒ `SUSPECTED: poc did not compile`.
4. **`forge test`** the PoC - it MUST reproduce the **specific** property break. The gate keys on an
   **invariant marker** in the revert reason (e.g. `require(..., "INV-SOLVENCY broken: ...")`), not
   on the exit code and not on "some test reverted". An unrelated revert ⇒
   `SUSPECTED: did not reproduce the specific property break`.
5. **Harm assertion** - the PoC MUST assert the consequence (who loses what), not just that a call
   ran. No harm assertion ⇒ `SUSPECTED: no harm assertion - mechanism only`.

Only if all five hold → **CONFIRMED**, and the PoC ships with the finding.

## Writing the harm assertion

The auto-generated reproducer replays the sequence and leaves a `TODO(skill)` where the harm
assertion goes. Your job is to turn the mechanism into a quantified consequence:

```solidity
function test_repro_INV_SOLVENCY() public {
    // ... replayed sequence ...
    // HARM: the vault is left insolvent - liabilities exceed assets by 50.
    require(vault.assets() >= vault.totalOwed(), "INV-SOLVENCY broken: assets < owed");
}
```

- Assert on **value flow** (balances, shares, debt), not on a boolean "did it revert".
- Embed the **invariant id** in the revert string so the gate can attribute the break (and so an
  unrelated revert elsewhere in the sequence is never mistaken for this one).
- Quantify where you can (`X wei stranded`, `attacker gained 1.5x fair share`).

## CONFIRMED vs SUSPECTED (what you may claim)

| State | You may say | You may NOT say |
|-------|-------------|-----------------|
| **CONFIRMED** | "reproduced by `test_repro_*`, harm asserted" | - |
| **SUSPECTED** | "engine flagged a candidate; PoC did not compile/reproduce/assert harm - needs a hand-authored PoC" | "this is a bug" / present it as a finding |

A SUSPECTED candidate is a lead for a human, never a reported vulnerability. Downgrading is not
failure - it is the tool refusing to overclaim.

## Classifying a CONFIRMED break

Even a reproduced break has three explanations (see `guidance/04` step 2): **real bug** (→ finding),
**bad invariant** (→ fix Stage 2, re-run), **bad harness** (→ fix Stage 3, re-run). Ask: *could this
exact sequence happen on mainnet against the real deployment?* If a step is only possible because of
a harness shortcut, it is a harness artifact, not a bug.

## Running it

```bash
fuzzpipe triage --target <t>                        # lower every candidate + re-execute (gate)
fuzzpipe verify --target <t> --poc test/MedusaReproducers.t.sol \
                --test test_repro_1 --marker INV-SOLVENCY   # gate one PoC -> CONFIRMED/SUSPECTED
```
