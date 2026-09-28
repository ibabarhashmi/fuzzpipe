# Guidance 01 - Identifying & Defining Meaningful Invariants

> Pipeline Stage 2 - the highest-leverage step; the whole campaign is capped by invariant
> quality. This is a **MANDATORY, GATED procedure**: run *every* derivation procedure below,
> then pass the **completeness gate** before presenting invariants for approval. Do NOT
> free-associate a handful of obvious properties - that is exactly how deep bugs (stranded
> value, dust, asymmetric flows) slip through a "passing" campaign.
> Read together with the `property-based-testing` and `entry-point-analyzer` skills.

## What an invariant is

A property that must hold true **after any sequence of valid contract calls**, no matter the
inputs or ordering. The fuzzer's job is to find a sequence that breaks it. If it can, you have
either a bug or a wrong invariant.

## Property taxonomy (the kinds of statements to aim for)

| Category | Asserts | Fuzzing shape |
|----------|---------|---------------|
| **Function-level** | exact before/after effect of one call | `property_*` reading `BeforeAfter` ghosts |
| **Valid-state (system)** | a relation holds in every reachable state | `property_*` over global state |
| **Stateful-sequence** | holds across any multi-call sequence | `property_*` over ghost accumulators |
| **High-level / solvency** | the system can always honor its obligations | `property_*` with ghost sums |
| **Anti-property** | a stated attacker goal is impossible | handler whose success ⇒ `t(false, "...")` |

## Step 0 (do FIRST) - bind the canonical invariant library

Before the open-ended procedures below, instantiate the curated backbone in
`guidance/09-invariant-library.md` (`templates/invariant-library.json`): detect the token
standards + protocol type(s), pull every matching `LIB-*` template plus the universal `*` ones,
bind each template's symbols to the target's real identifiers, and drop its reference `property`
into the harness. Skip any template that doesn't fit with a one-line reason. This gives you the
high-signal, compile-clean core (solvency, conservation, supply integrity, negative access
control, reentrancy oracle, ...) up front, so the procedures below only need to add what is
*protocol-specific*. Library-first is what keeps the set small and intuitive instead of a firehose
of bespoke, over-engineered formulas. **Then** run every procedure below on top.

## Derivation procedures - run EVERY one (log candidates, or a one-line waiver if none)

Finding the right properties is the whole game. Do not transcribe; **generalize** (a test
scenario "deposit 100 → 100 shares" becomes "for all amounts at rate 1, shares == amount").
Every candidate you emit (library or procedure/persona) must carry the **grounding** required by
`guidance/09`: a concrete code reference, its origin (`LIB-*` id / procedure # / persona), a
one-line harm, and a reference implementation that compiles (`fuzzpipe build` passes). Ungrounded,
harm-less, or non-compiling candidates are rejected at the approval checkpoint.

### Structural procedures (1-5)

**1. Per-variable interrogation.** For EVERY state variable, ask five questions:
- *Who may write it?* → a **negative access** property ("only `f`/`g` may change `X`").
- *Which direction may it move?* → a **monotonicity** property (only-increases index, timestamp).
- *What must move with it?* → a **coupling** candidate (when `X` changes, `Y` must change too).
- *What is its valid domain?* → a **range** invariant (`0 ≤ X ≤ cap`).
- *What holds at constructor exit?* → an **init** invariant.

```solidity
// "only allowed functions may change X" - implement as a per-handler ghost check:
function property_X_onlyChangesViaAllowed() public {
    // _before.x / _after.x snapshotted by updateGhosts; flag any handler that moved X
    // when it wasn't deposit/withdraw (encode the allow-list in the handler bodies).
}
```

**2. Coupling matrix.** Enumerate every pair of related accounting variables - per-user mapping ↔
total, shares ↔ assets, internal accounting ↔ `token.balanceOf(address(this))`, debt ↔ collateral.
For each pair pick the relation (`==`, `<=`, ratio) and decide **which side may drift safely**:
direct donations push the real balance *above* internal accounting, so solvency is `>=`, never `==`.

```solidity
function property_supply_integrity() public { eq(vault.totalSupply(), _sumShares(), "totalSupply == Σ balances"); }
function property_solvency() public { gte(vault.totalAssets(), _totalOwed(), "assets >= owed"); }
```

**3. Value-flow conservation (the no-stranded-value / completeness check - DON'T SKIP).**
List EVERY path value enters or leaves: deposit, withdraw, mint, burn, fees, **reward accrual +
claim**, skim, rescue, direct transfer. **Every path must cross ≥1 conservation property; a flow
path covered by no property is a red flag.** This is the class that catches *stranded value*:
- `Σ accrued == Σ claimed + Σ claimable` (nothing accrued is unreachable),
- the **last** claimant can drain the remainder (no dust permanently locked),
- a full distribution target (`rewardsMax`, fee pot) is **fully** distributable.

```solidity
// completeness: everything that was funded in must be claimable out
function property_rewards_fully_claimable() public {
    eq(ghostRewardsAccrued, ghostRewardsClaimed + _totalClaimable(),
       "rewards completeness: accrued == claimed + claimable (no stranded value)");
}
```

**4. State-machine extraction.** For every enum/phase flag (`paused`, `initialized`, auction
phase): draw the legal transition graph. Properties: no off-graph transition; terminal states
stay terminal; phase-gated functions revert outside their phase.

**5. Role × action matrix.** Roles (owner, admin, keeper, anyone) × privileged actions. Each cell
yields a **negative** property ("a non-owner cannot …") - the negative direction is what catches
bugs. Implement as an attacker handler whose success is a violation:

```solidity
function handler_attacker_setFee(uint256 fee) public {
    vm.prank(currentActor);                       // a non-privileged actor
    try target.setFee(fee) { t(false, "unauthorized setFee succeeded"); } catch {}
}
```

### Adversarial procedures (6-9)

**6. Anti-properties from the threat model.** Write attacker goals as plain sentences -
"withdraw more than deposited + earned", "make another user's withdraw revert", "strand value
that should be claimable", "change someone else's entitlement" - and convert each into a property
whose violation IS the exploit (third-party isolation):

```solidity
function property_no_third_party_loss() public {
    // for a victim not touched this sequence, entitlement must never decrease
    gte(_entitlementOf(victim), _victimEntitlementBefore, "third-party entitlement decreased");
}
```

**7. Round-trip pairs.** For every inverse pair (deposit∘withdraw, wrap∘unwrap,
convertToShares∘convertToAssets): the user never profits from a round trip (rounding favors the
protocol). Cheap and very productive against rounding-direction bugs.

**8. Docs / NatSpec mining.** Every "must / always / never / only / at most" sentence in the
README, NatSpec, or comments is a candidate - record the doc→property mapping. Where the code
contradicts the docs, do **not** encode the code's behavior as "correct" - flag the contradiction
as a finding candidate. *(This is also how a client/threat-model invariant list enters - feed it
here as HIGH-priority candidates.)*

**9. Protocol-type priors** (a prompt list, never a ceiling — detect the protocol type first, then
pull the matching row; more than one may apply):

| Type | High-value priors |
|------|-------------------|
| vault / staking (ERC-4626) | share price not inflatable by direct donation (inflation attack); first-depositor safety; `convertToShares∘convertToAssets` never profits the user; reward conservation (accrued == claimed + claimable) |
| lending / CDP | account stays healthy post-op; liquidation only when unhealthy and never leaves bad debt unaccounted; interest monotone non-negative; no self-liquidation profit |
| AMM / DEX | trading invariant (k) non-decreasing net of fees; fee accounting separate from reserves; LP share value not extractable by add/remove in one block |
| auction / timelock | highest-bid monotonicity; no acceptance after deadline; delay not bypassable; refund of outbid always available |
| perps / derivatives | total long PnL + total short PnL + fees == 0 (zero-sum); funding rate bounded; a position cannot be closed for more than its margin + PnL; insurance fund never negative |
| bridge / cross-chain messaging | minted-on-dest == locked-on-source (no mint without lock); a message cannot be replayed; only the canonical relayer/root can finalize; nonce monotonicity |
| NFT / ERC-721 | ownership is unique and total; approvals cleared on transfer; no mint past max supply; royalty/fee cannot be bypassed on transfer |
| governance / voting | voting power == snapshot balance (no double-count via transfer/delegate mid-vote); quorum/threshold enforced; a proposal cannot execute twice; timelock not bypassable |
| oracle-dependent | rejects stale/zero/extreme readings; single-block price move cannot be monetized; TWAP window respected |
| restaking / LRT | withdrawal queue conserves principal; slashing accounted before withdrawal; no double-withdraw of the same stake |
| intents / solver | a filled intent pays out exactly what was authorized; a solver cannot extract surplus beyond the stated fee; partial fills conserve the remainder |

For any type: also apply the token-standard library invariants (ERC-20/721/4626/7540) the protocol
declares in `standards` (Stage 0 config).

### Composition & economic procedures (10-11)

Procedures 1-9 mostly reason about *single variables* and *single calls*. The two highest-value
bug classes in modern DeFi - composition and economic manipulation - need their own passes.

**10. Cross-function / cross-contract composition (IR `scope: cross_contract`).** The coupling
matrix (procedure 2) pairs *variables*; this pass composes *calls*. Enumerate:
- **Reentrancy windows:** for every external call the contract makes (token transfer, receiver hook,
  arbitrary callback), is there a state update *after* it? An invariant must hold at that boundary,
  not only at rest. Property: "no callback can observe/exploit a mid-update state."
- **Callback ordering:** ERC-777/721/1155 hooks, `onFlashLoan`, `onERC721Received` - a handler that
  re-enters a different entry point must not break solvency.
- **Flash-loan-wrapped sequences:** any check that reads a balance/supply must still hold when that
  quantity is transiently enormous within one sequence (borrow -> act -> repay).
- **Multi-contract state coupling:** when two contracts share accounting (vault ↔ strategy, market ↔
  oracle), the cross-contract relation is an invariant even though neither contract enforces it
  alone.
Implement these as multi-call handler sequences whose success is a violation (like procedure 5's
attacker handlers, but composed across contracts).

**11. Economic / MEV / oracle invariants (IR `scope: economic`, forces `tier_hint >= 1`).** Target
the manipulation classes fuzzing-of-structure misses:
- **Price manipulation:** an op priced off an on-chain readable cannot profit when that readable is
  moved (within a block) vs. the same op at a fair value.
- **Sandwich resistance:** front/back-running a victim's sequence in the same block cannot extract
  protocol value beyond stated fees.
- **Oracle staleness / extremes:** the protocol is safe under zero / stale / max oracle readings
  (reverts or clamps - never misprices).
- **Fee & rounding direction:** every fee and rounding step favors the protocol, never a repeatable
  user gain (ties to procedure 7).

### Stage 2b - adversarial personas (run before the gate)

After procedures 1-11, run the **adversarial persona pass** in `guidance/07-adversarial-personas.md`:
seven attacker personas each generate anti-properties from the threat model, run **in parallel**,
then dedup/merge into the IR. This is what turns discovery from a checklist into a red-team. The
persona pass and procedures are complementary - procedures find what *should* hold; personas find
what an attacker would *break*.

## Prioritize (P0-P3) - this is also the auditor's prune list

| Tier | Covers |
|------|--------|
| **P0** | solvency, conservation, access control on fund-moving functions |
| **P1** | state-machine validity, monotonicity, third-party isolation |
| **P2** | round-trips / rounding direction, parameter bounds |
| **P3** | informational |

At the approval checkpoint the auditor prunes - only approved invariants become harness
`property_*` functions. Pruning P2/P3 (or seeds already covered) is how you cut campaign + token
budget **without** losing the P0/P1 depth. Pre-falsify P0/P1 candidates lightly (hand-trace one
fee path, one partial op, one zero/max boundary); the fuzzer is the real falsifier, so don't
over-invest - but a candidate that obviously can't hold gets refined or marked as a finding flag,
never silently dropped.

## Seed invariants (Stage 0 merge)

Auditor- or client-provided seeds (and any threat-model / spec md file) are recorded under
`## Seed (auditor, HIGH priority)` and are **additive**: tested first/with priority, but discovery
still runs all 9 procedures. Never treat seeds as the complete set.

## Semantic completeness gate + coverage critic - MANDATORY, pass before the approval checkpoint

The v0.2 gate was **honor-system** (self-assert the checklist). v2.2 enforces it two ways - a
machine check for *surface* coverage and an adversarial critic for *bug-class* coverage. Do NOT
present invariants (Stage 2 → approval) until both pass.

### 1. Machine-checkable surface gate - run it, don't assert it

```bash
fuzzpipe ir coverage-audit --target <t>     # exit 0 = pass; exit 2 = unwaived gap (loop back)
```

It scans the in-scope sources and fails (exit 2) if any of these is unmapped **and** unwaived:

- [ ] every state-mutating external/public **entry point** is referenced by ≥1 invariant
- [ ] every public **state variable** is referenced by ≥1 invariant
- [ ] every **privileged** function has ≥1 AUTHORIZATION / anti-property invariant

A genuine skip is recorded in `.fuzzpipe/coverage-waivers.json` as `{"name": "why it is safe"}` - a
waiver must carry a reason (an empty reason is ignored, so it cannot silently pass). This replaces
the free-text one-line waiver that was a free escape hatch. Still assert by hand the two the scanner
can't see: **every value-flow path crosses ≥1 conservation property** (procedure 3) and **every docs
"must/never/only" sentence** is mapped or flagged as a contradiction.

### 2. Coverage critic - the adversarial "what did we miss?" pass

Surface coverage ≠ bug-class coverage: you can reference every function and still have no invariant
about oracle staleness or reentrancy. Before approval, run one adversarial pass (attacker lens)
whose only job is to name **bug classes entirely unmodeled** by the current set. For each named
class, either add a candidate or record an explicit, justified waiver. See
`guidance/07` "Coverage critic". A gate failure - surface or semantic - means a whole class of bugs
is invisible to the campaign. Fix the gap before fuzzing.

## Writing a good invariant statement

- **One property per invariant.** Don't bundle.
- **Falsifiable & concrete.** "Funds are safe" is not an invariant. "`totalAssets()` never
  decreases except via `withdraw`/`redeem`" is.
- **Reference exact variables/functions** so Stage 3 can implement it directly.
- **Note the rounding tolerance** if exact equality is too strict (`approxEqAbs` / `±N wei`).

## Output format (write to `.fuzzpipe/invariants.md`)

| ID | Statement | Category | Priority | Derived via | Source | Constrains (entry points) | Tolerance |
|----|-----------|----------|----------|-------------|--------|---------------------------|-----------|
| INV-1 | totalAssets() >= Σ owed | system | P0 | proc 2 | discovered | deposit, withdraw | ±1 wei/user |
| INV-2 | Σ accrued == claimed + claimable (no stranded rewards) | sequence | P0 | proc 3 | discovered | accrue, claim | exact |
| INV-3 | shares round-trip ≤ input | sequence | P2 | proc 7 | discovered | deposit, redeem | ±1 wei |
| INV-4 | only owner can pause() | function | P0 | proc 5 | library | pause | exact |

Then record the completeness-gate result, and **STOP** - present this table to the auditor for
approval / prune before Stage 3.

## Result-driven refinement (loop-back enrichment, Stage 5 → Stage 2)

Discovery runs once, up front, **blind to what the fuzzer actually explored**. Don't leave it there.
After a campaign (Stage 5), mine the run for signals that *propose new invariants*, not just re-run
the old ones:

- **Coverage gaps** (`fuzzpipe coverage`, exit 2): a function the campaign never exercised is a
  harness gap AND a hint that no invariant drove the fuzzer there - add a property that references
  it, or a handler that reaches it.
- **High-coverage-but-no-break regions:** code the fuzzer hammered without ever failing a property
  is either genuinely safe or *unconstrained by any invariant*. Ask "is there really nothing that
  must hold here?" before calling it safe.
- **Near-misses in the corpus:** sequences that got close to a boundary (a balance approaching zero,
  a ratio approaching a cap) suggest a tighter invariant worth stating explicitly.
- **A CONFIRMED bug's neighborhood:** once one bug is found, generalize it - the same class often
  recurs on a sibling function (a rounding bug in `deposit` → check `mint`/`withdraw`/`redeem`).

Feed the new candidates back through the completeness gate and (if material) the approval checkpoint.
Record each enrichment loop in `state.json`.

## Common mistakes

- **Too weak:** an invariant that can never break (tests nothing). Ask "what realistic bug would
  this catch?"
- **Too strong:** breaks under legitimate behavior (false-positive churn).
- **Untestable as written:** depends on off-chain data the harness can't see → reformulate.
- **Only the theft direction:** covering "no user gains more than fair" but not "no value gets
  stranded / locked" - run procedure 3 and the gate to cover BOTH directions.
- **Implicitly assuming the bug is absent:** don't encode the buggy behavior as "correct."
