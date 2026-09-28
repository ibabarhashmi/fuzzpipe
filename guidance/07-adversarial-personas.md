# Guidance 07 - Adversarial Personas (Stage 2b - red-team the invariant SET)

> Pipeline Stage 2b - run AFTER the 9 structural/adversarial procedures in `guidance/01`,
> BEFORE the completeness gate and approval checkpoint. This is the step that turns a
> single-pass checklist into an adversarial search. The 9 procedures ask "what should hold?";
> the personas ask "if I were paid to break this, what would I try, and what property would
> catch me?" Every persona output is an **anti-property** whose violation *is* the exploit.

## Why this exists

The v0.2/v2.1 discovery pass was honor-system: run 9 procedures once, self-grade a completeness
gate. It is strong on *structural* properties (per-variable, coupling, conservation) but **average
on the properties a motivated attacker would target** - MEV, oracle manipulation, cross-contract
composition, privileged-key abuse, griefing. Those are exactly the classes that produce critical
findings. This file makes attacker reasoning a first-class, parallelizable step.

## How to run it (parallel by default)

Run each persona as an **independent generation pass** - they are blind to each other on purpose
(diversity beats redundancy). In an agent context, fan them out concurrently (one sub-agent per
persona), then **dedup + merge** their candidates into the IR before the completeness gate. Each
persona emits IR entries with `source: threat-model`, `category: anti-property` (or the closest
fit), and a `derived_via: "persona:<name>"` tag so the SUMMARY can report attack-surface coverage.

Feed every persona the auto- or auditor-supplied **threat model** (`guidance/08`) plus the contract
surface. A persona with nothing to attack is a signal the threat model is thin - go widen it.

## The persona matrix

For each persona: **goal in one sentence -> the anti-property whose violation proves the goal**.

### 1. MEV / sandwich searcher
*Goal:* "Extract value by ordering my transactions around a victim's within the same block."
- Price/observable state a user relies on cannot be moved against them by an unprivileged call in
  the same block (`property_no_sandwich_extraction`).
- A swap/mint/redeem at a manipulated spot price cannot profit vs. the same op at a fair price.
- First-in-block and last-in-block orderings of the same sequence yield the same protocol solvency.

### 2. Malicious admin / compromised privileged key
*Goal:* "With a privileged role, drain or brick the protocol beyond my legitimate powers."
- A privileged setter cannot move user funds or retroactively change accrued entitlements
  (`property_admin_cannot_touch_user_funds`).
- Pausing/upgrading cannot strand already-owed withdrawals (users can always exit what they earned).
- No privileged action can push the system into an unrecoverable/insolvent state.
- (Also emit the **negative access** properties from procedure 5 for every role x action cell.)

### 3. Flash-loan attacker
*Goal:* "Borrow unbounded capital for one transaction to satisfy a check I could not otherwise pass."
- Any invariant that reads a *balance* or *supply* still holds when that quantity is transiently
  enormous within a single call sequence (`property_holds_under_flashloan_scale`).
- Collateral/health/price checks cannot be satisfied by within-tx inflated balances that unwind.
- A round-trip that borrows -> acts -> repays in one sequence leaves the attacker no better off.

### 4. Griefer / DoS
*Goal:* "Make another user's legitimate action revert or become permanently stuck - I don't profit,
they lose access."
- A third party's `withdraw`/`claim`/`exit` cannot be made to revert by an unrelated actor's
  sequence (`property_no_griefing_of_exit`).
- No unprivileged sequence can permanently lock a phase/flag so a needed function is unreachable.
- Dust / rounding cannot accumulate into a permanently unclaimable remainder (ties to procedure 3).

### 5. First-depositor / rounding exploiter
*Goal:* "Deposit 1 wei, donate directly, and inflate share price so the next depositor's rounding
loss is my gain."
- Share price cannot be inflated by a direct token donation (the ERC-4626 inflation attack)
  (`property_share_price_not_donation_inflatable`).
- A round trip (deposit -> redeem) never profits the user; rounding always favors the protocol
  (ties to procedure 7).
- The first depositor gets no structural advantage over later depositors.

### 6. Cross-contract / reentrancy composer
*Goal:* "Chain calls across contracts, or re-enter mid-call, so an intermediate inconsistent state
becomes observable/exploitable."
- No external callback (ERC-777/ERC-721 hooks, arbitrary token, receiver) can re-enter and observe
  or exploit a mid-update state (`property_no_reentrancy_window`).
- An invariant holds not just at rest but at every external-call boundary within a sequence.
- (Emit these with IR `scope: cross_contract`; see procedure 10 in `guidance/01`.)

### 7. Oracle manipulator
*Goal:* "Feed a stale, manipulated, or extreme oracle value so the protocol misprices."
- The protocol rejects or is safe under stale / zero / extreme oracle readings
  (`property_safe_under_bad_oracle`).
- A single-block price move (spot manipulation) cannot be converted into protocol loss.
- (Emit with IR `scope: economic`; see procedure 11 in `guidance/01`.)

## Merging into the IR (dedup rule)

After the personas return, dedup by *semantic target*, not by wording: two candidates that both say
"a non-owner cannot move funds" collapse to one, keeping the stronger/more-specific statement. A
candidate that overlaps a structural invariant from procedure 1-9 is **not** discarded silently -
prefer the version with the concrete predicate and record the other as covered. Keep every candidate
that a persona produced which no structural procedure reached: that delta is the whole point of this
step.

## Coverage critic (the "what did we miss?" pass)

Before the completeness gate, run one final adversarial pass whose only job is to name **bug classes
that are entirely unmodeled** by the current set - "there is no invariant about oracle staleness",
"nothing covers cross-contract reentrancy", "no property targets the fee path". Each named class
becomes either a new candidate or an explicit, justified waiver. This is the semantic complement to
the machine-checkable `fuzzpipe ir coverage-audit` (which enforces surface coverage). See
`guidance/01` "Semantic completeness gate + coverage critic".

## Reducing false positives — MANDATORY (a persona candidate is a HYPOTHESIS, not a finding)

Personas are optimized for *recall* — they invent plausible anti-properties. Plausible ≠ correct: an
anti-property can be **too strong** (asserts more than the protocol actually promises), and the fuzzer
will happily "break" it. That break is a **false positive** — a *bad invariant*, not a bug. A
reproducing counterexample is necessary but **NOT sufficient**. Every persona candidate passes these
five filters before it is approved, and the last one before it is ever called CONFIRMED.

> Worked example (a real FP this protocol produced): the first-depositor persona proposed "every
> nonzero sell returns > 0 output." Medusa broke it — but only for **~1e-8 of a token** (dust), which
> is expected integer-rounding behavior every AMM has. It is grounded in no spec and the harm is
> negligible → **BAD-INVARIANT**, not a finding. Contrast the docs-mined "there is always a fee > 0",
> which the code's *own comment* promises → a real (documented-intent) violation.

### 1. Grounding — reject any anti-property that cannot cite its basis
Each candidate MUST name at least one of:
- **Spec/docs:** a NatSpec/README/comment "must / never / always / at most" sentence it enforces.
  (This is why docs-mined invariants are the most reliable — the code contradicts its *own* stated
  intent.)
- **Conservation/accounting law:** value-in == value-out ± fees; a real balance vs. an accounting sum.
- **Known bug-class pattern** from the protocol-type priors (donation inflation, reentrancy window,
  oracle staleness, first-depositor) — not an invented universal.
- **Economic-materiality bound** (filter 3).
A candidate grounded in NONE of these is **speculative**: keep it as a note, do not promote it.

### 2. State it two-sided, with an explicit tolerance
Most FPs are strict statements that forbid legitimate rounding. Prefer
"redeem ≤ fairValue **+ 1 wei**" over "redeem never exceeds fairValue"; "a sell **above the minimum
tradeable size** returns > 0" over "every nonzero sell returns > 0". Integer-math protocols round — an
invariant that forbids expected rounding is a bad invariant by construction.

### 3. Materiality / dust gate (rounding, fee, and output classes especially)
Require the counterexample to be **material**: the loss must exceed a threshold (a few basis points of
the trade, or an absolute dust bound), not merely be nonzero at 1 wei. If a break reproduces ONLY at
dust scale, auto-classify it **BAD-INVARIANT**. Bake the threshold into the property (assert the
materiality bound, not the strict inequality) so the fuzzer never wastes budget on dust.

This filter has **mechanical teeth** — run the sweep instead of eyeballing it:
```bash
fuzzpipe materiality --target <t> --test <fn> --min 1 --max 1e24 --material <smallest_meaningful_amount>
```
Write `<fn>` to read the per-run amount from `FUZZPIPE_SWEEP_AMOUNT`
(`uint256 amount = vm.envOr("FUZZPIPE_SWEEP_AMOUNT", uint256(1));`), reach the state where the bug
lives, run the exploit at `amount`, and assert the invariant (a revert = broken). The command replays
it across log-spaced scales and **exits 2 with a `DUST-ONLY` verdict when the invariant breaks only
below `--material`** — the signature of a bad invariant. (Validated on the "a nonzero sell returns 0"
candidate: it only breaks below ~1e-4 of a token, so the command flags it DUST-ONLY.)

### 4. Adversarial refutation before approval (spawn skeptics; default to REFUTED)
For each surviving candidate, run a **refuter pass** — one or more sub-agents whose ONLY job is to
argue it is a *bad invariant*: "Is the violation just expected/permissionless behavior? Does the spec
actually promise this or did the persona over-claim? Is there a legitimate call path that violates it
by design? Is the harm material?" Default to **refuted** when uncertain. Approve only what survives.
This is the same adversarial-verify discipline the verdict gate applies to *findings*, moved earlier —
onto the *invariant itself*. Run refuters with **diverse lenses** (spec-literalist, economic, "is this
just how AMMs work") rather than N identical skeptics.

### 5. Classify-before-confirm — reproduction is not confirmation
A reproducing counterexample is a **candidate**, classified exactly once as **real bug / bad invariant
/ bad harness** (`guidance/04`) with a written justification, BEFORE it is ever labeled CONFIRMED. The
verdict gate proves *reproduction*; it does not prove the invariant is legitimate — that is human/
analytical judgment. The strongest confirmation is **external**: a matching documented finding or
audit. Treat anything you "found" that a real audit did not as unproven until you have refuted the
"bad invariant" hypothesis yourself.

**Net:** personas widen the net (good for recall); these five filters restore precision. Skipping them
turns the persona pass from an asset into an FP generator.
