# Guidance 04 - Analyzing & Interpreting Results

> Pipeline Stage 5-6. Read together with the `coverage-analysis` skill. Turn raw fuzzer
> output into auditor-reviewable findings - or correctly conclude "no bug found, here's the
> coverage."

## Step 1 - Convert the break into a reproducible test

When an invariant breaks, the engine emits a call sequence. Make it a reproducible test:

```bash
cli/fuzzpipe triage        # native parser: reads Medusa test_results/*.json
```

On a **Foundry** project this writes `test/MedusaReproducers.t.sol` (replays each broken
sequence against the Chimera harness) and runs it with `forge test`. On a **Hardhat** project it
writes a best-effort ethers replay DRAFT plus, if forge is installed, the byte-exact Foundry
reproducer (see the Hardhat section below). Confirm it reproduces deterministically.
**A finding without a reproducing test is not confirmed.**

## Step 2 - Classify every break (the key judgment)

A broken invariant has exactly three explanations. Decide which:

| Explanation | Signal | Action |
|-------------|--------|--------|
| **Real bug** | sequence is realistic; harm is genuine | → Stage 6 finding |
| **Bad invariant** | invariant was too strict / encoded a wrong assumption | → fix Stage 2, re-run |
| **Bad harness** | setup/clamp let an *impossible* state occur (e.g. minted tokens for free in Setup) | → fix Stage 3, re-run |

Ask: *could this exact sequence happen on mainnet against the real deployment?* If a step
is only possible because of a harness shortcut, it's a harness artifact, not a bug.

## Step 3 - Prove the HARM, not just the mechanism

The reproducer must assert the **consequence**, not merely that a function was callable.

- ❌ mechanism: "`withdraw` succeeded with a crafted value"
- ✅ harm: "attacker ended with 1.5× their fair share; vault left insolvent by X"

If you cannot write an assertion on the harm, it is not yet a confirmed finding - downgrade
to "needs review" and say why.

## Step 4 - Shrink / minimize

Reduce the sequence to the smallest set of calls that still breaks the invariant. A 3-call
repro is far more convincing and debuggable than a 200-call one. Medusa's shrinking is
limited - finish minimizing by hand if needed; Echidna shrinks well.

## Step 5 - Coverage sanity (don't trust a clean run blindly)

Run `coverage-analysis` on the campaign. Two failure modes to catch:
- **Passed but uncovered:** invariants "held" only because the fuzzer never reached the
  risky code. Report the uncovered functions - this is itself an actionable gap, not safety.
- **Magic-value walls:** a `require(x == 0xDEADBEEF)` the fuzzer can't pass. Add to the
  dictionary or patch via `fuzzing-obstacles`, then re-run.

Always report achieved coverage alongside results.

## Step 6 - Severity (Impact × Likelihood)

| | Likelihood High | Likelihood Med | Likelihood Low |
|---|---|---|---|
| **Impact High** (fund loss / permanent lock) | Critical | High | Medium |
| **Impact Med** (conditional loss / breakage) | High | Medium | Medium |
| **Impact Low** (broken view / non-fund) | Medium | Low | Low |

Likelihood from the repro: does it need special preconditions, specific ordering, or a
privileged actor? Impact from the harm assertion (quantify in tokens/$ where possible).

## Step 7 - Write the finding

Use `templates/finding.md` → `output/findings/`. Required: title, severity, the invariant
that broke, the minimized repro test (the PoC), quantified harm, and remediation.

## What to put in `output/SUMMARY.md`

- Invariants tested (count by category) and which were seed vs discovered vs library.
- Engines run + campaign sizes.
- **Coverage achieved** (and notable uncovered functions).
- Broken invariants → confirmed bugs (with finding links).
- Breaks classified as bad-invariant / bad-harness (and what was fixed).
- **Invariants that could NOT be tested** and why (honesty requirement).
- Loop-backs performed.

## Honesty rules (do not overclaim)

1. "No invariant broke" ≠ "the protocol is safe." State it as: *invariants X,Y,Z held under
   N sequences at C% coverage.*
2. Fuzzing is empirical, not a proof. For properties needing proof, note the **FV bridge**:
   Halmos/Kontrol run on the same Chimera harness and can attempt to prove (not just test)
   the invariant.
3. Every confirmed finding ships with a reproducing test. No test → not confirmed.
4. Report uncovered code and untested invariants as explicitly as you report bugs.

---

## Hardhat triage (the honest limitation)

On a Hardhat project, the executable reproducer story is weaker than Foundry. The Medusa broken
sequence is expressed against the Chimera **handlers** (clamped wrappers that use Foundry/HEVM
cheatcodes like `vm.prank`), which do not exist in a plain Hardhat/ethers runtime.

`fuzzpipe triage` on a Hardhat target therefore:
1. Writes `test/MedusaReproducers.repro.js` - a **best-effort ethers replay DRAFT**. It embeds
   the raw decoded Medusa sequence (method/args/sender/delays) as comments (the authoritative
   record) and a TODO scaffold to translate each handler into the underlying ethers calls. You
   MUST verify it and add the harm assertion - it is not a faithful auto-replay.
2. If `forge` is installed, ALSO writes `foundry-repro/MedusaReproducers.t.sol` - the byte-exact
   Foundry reproducer (run with `forge test` from the `foundry-repro/` context). This is the
   reliable PoC when Foundry is available.

**Recommendation:** if you have Foundry installed, use the `foundry-repro/` reproducer as the
PoC. Otherwise, translate the ethers DRAFT by hand using the embedded raw sequence.
