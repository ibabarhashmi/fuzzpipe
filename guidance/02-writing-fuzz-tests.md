# Guidance 02 - Writing Effective Fuzz / Invariant Tests (Chimera harness)

> Pipeline Stage 3. Read together with the `harness-writing` and `fuzzing-dictionary`
> skills. Goal: turn approved invariants into a Chimera harness that runs unchanged on
> Foundry + Medusa + Echidna.

## The Chimera scaffold (write-once, run-everywhere)

`create-chimera-app` / the Recon Handler Builder produce this `recon/` structure. You fill
it in; the same files run on all engines.

| File | Purpose | You write |
|------|---------|-----------|
| `Setup.sol` | Deploy contracts, create actors, fund balances | deployment + actor setup |
| `TargetFunctions.sol` | Handlers the fuzzer calls (one per entry point) | clamped wrappers |
| `Properties.sol` | The invariants as boolean checks | one function per invariant |
| `BeforeAfter.sol` | Snapshot ghost state before/after each call | `__before`/`__after` vars |
| `CryticTester.sol` | Echidna/Medusa entrypoint | usually generated, leave as-is |
| `CryticToFoundry.sol` | Foundry entrypoint + reproducers | add repro tests here |

## TargetFunctions - the handlers

Each state-changing entry point gets a handler. Handlers shape raw fuzzer input into valid
calls and keep campaigns alive.

```solidity
function handler_deposit(uint256 assets) public {
    // 1. CLAMP raw input to a realistic range (bound() / modulo)
    assets = between(assets, 1, type(uint96).max);
    // 2. pick/limit actor (the fuzzer chooses among a small actor set)
    // 3. call the SUT
    vault.deposit(assets, currentActor);
    // 4. (optional) record an action for sequence-aware invariants
}
```

Rules:
- **Clamp every input** to a sane range - unbounded values waste the campaign on reverts.
  Use `fuzzing-dictionary` tokens for meaningful constants (caps, decimals, magic values).
- **Revert-tolerant:** a handler reverting on genuinely-invalid input is fine; don't
  `require` so hard that the fuzzer can never make a valid call. Configure the engine's
  `fail_on_revert` deliberately (usually false for handlers, true for properties).
- **Small actor set** (e.g. 3 actors) so the fuzzer can build multi-actor sequences.
- **One handler per entry point** the auditor approved as in-scope.

## Properties - the invariants

Each approved invariant becomes one boolean function. Naming convention engines recognize:

```solidity
// system-level: checked after every call sequence
function property_solvency() public view returns (bool) {
    return vault.totalAssets() >= sumUserDeposits();   // INV-1
}

// sequence/round-trip: uses BeforeAfter snapshots
function property_no_free_value() public returns (bool) {
    return __after.actorEquity <= __before.actorEquity + legitimateYield;  // INV-2
}
```

- Map each `property_*` back to its invariant ID in a comment.
- Use tolerance helpers (`approxEqAbs`) where exact equality is too strict (note tolerance
  came from `invariants.md`).
- View properties for stateless checks; stateful properties read `BeforeAfter` ghosts.

## BeforeAfter - ghost variables

Track values across a call so sequence invariants can compare. Example for ERC-4626:

```solidity
struct Vars { uint256 totalShares; uint256 totalAssets; uint256 actorEquity; }
Vars internal __before;
Vars internal __after;

modifier updateGhosts() {
    __before = _snapshot();
    _;
    __after  = _snapshot();
}
```

Apply `updateGhosts` to handlers whose effects a sequence invariant needs to observe. The
classic ghost: sum of all LP shares to check `Σ shares == totalSupply`.

## Setup - deployment & actors

- Deploy the protocol exactly as production (use real init params).
- Create a fixed small set of actors and fund them.
- Register the target contracts/selectors so the fuzzer knows what to call.
- Keep setup deterministic (no real timestamps/randomness baked in).

## Coverage-first mindset

A harness that compiles but never reaches the interesting code finds nothing. After the
first run, use `coverage-analysis` (Stage 5) to see what's uncovered, then come back and:
- relax over-tight clamps, add missing handlers, or apply `fuzzing-obstacles` for blockers
  (checksums, access gates, magic-value `require`s).

## Build before you run

Compile via `cli/fuzzpipe build`. Fix all compile errors before Stage 4 - a broken harness
wastes a campaign.

## Standard-library shortcut

If the protocol implements ERC20/721/4626/7540, import the ToB property library set
(see `property-based-testing/references/libraries.md`) instead of re-writing those
properties by hand - then add only the protocol-specific ones.

---

# Harness Pattern Library (reusable recipes)

> These are battle-tested shapes for `TargetFunctions` / `Setup` on real protocols. Pick the
> patterns that match the target and adapt - they make Stage 3 faster and more consistent.

## Pattern A - Multi-actor model

Always fuzz with a small fixed set of actors (3-5) so the fuzzer can build multi-user attacks
(one user grieves another, first-vs-later depositor, etc.).

```solidity
address[3] internal actors = [address(0xA11CE), address(0xB0B), address(0xCA201)];
address internal currentActor;
function _useActor(uint256 seed) internal { currentActor = actors[seed % actors.length]; }
```
Every handler takes a `uint256 actorSeed` as its first param and calls `_useActor(actorSeed)`.

## Pattern B - Clamping inputs (keep campaigns productive)

Unbounded inputs waste the campaign on reverts. Clamp every numeric arg with `between()`:

```solidity
assets = between(assets, 1, 100_000e18);     // realistic range, not 0..2^256
shares = between(shares, 1, vault.balanceOf(currentActor)); // bound to what's possible
```
Use realistic upper bounds (token caps, supply). For "dust vs whale" bugs, run separate
handlers with different ranges (e.g. `between(x,1,1e6)` and `between(x,1e6,1e24)`).

## Pattern C - Approvals + prank (ERC20 flows)

Token-moving handlers must set allowance and impersonate the actor:

```solidity
vm.prank(currentActor); token.approve(address(target), amount);
vm.prank(currentActor);
try target.deposit(amount) { ghostDeposited += amount; } catch {}
```
Wrap the external call in `try/catch` so an expected revert doesn't kill the sequence.

## Pattern D - Access-controlled handlers (roles)

For admin/role functions, prank as the *authorized* address in one handler (to exercise the
happy path) AND as a random actor in another (to prove unauthorized callers are rejected):

```solidity
function handler_admin_setFee(uint256 fee) public {
    fee = between(fee, 0, MAX_FEE);
    vm.prank(admin); target.setFee(fee);          // authorized path
}
function handler_attacker_setFee(uint256 fee) public {
    vm.prank(currentActor);
    try target.setFee(fee) { t(false, "unauthorized setFee succeeded"); } catch {} // must revert
}
```

## Pattern E - Multi-token / multi-market

Index assets by a fuzzed selector so the fuzzer explores all markets:

```solidity
IERC20[] internal tokens;  // set up in Setup
function _token(uint256 seed) internal view returns (IERC20) { return tokens[seed % tokens.length]; }
function handler_supply(uint256 tokenSeed, uint256 amt) public {
    IERC20 tok = _token(tokenSeed); ...
}
```

## Pattern F - Donation / direct-transfer primitive (CRITICAL - don't forget)

The demo proved a "passing" campaign was a false sense of safety because the harness had no
donation handler. For ANY balance-based accounting (vaults, AMMs, lending), add:

```solidity
function handler_donate(uint256 actorSeed, uint256 amount) public {
    _useActor(actorSeed);
    amount = between(amount, 1, 100_000e18);
    if (token.balanceOf(currentActor) < amount) return;
    vm.prank(currentActor); token.transfer(address(target), amount); // bypasses deposit accounting
}
```
This is the inflation/first-depositor attack primitive. Omitting it hides a whole bug class.

## Pattern G - Ghost accounting for conservation invariants

Mirror real flows in ghost variables so you can assert conservation (`Σin - Σout == balance`):

```solidity
uint256 internal ghostDeposited;
uint256 internal ghostRedeemed;
// update inside handlers ONLY on success (inside the try block)
```

## Pattern H - Time / block advancement

For interest, vesting, rewards, cooldowns - let the fuzzer move time:

```solidity
function handler_warp(uint256 secs) public { vm.warp(block.timestamp + between(secs, 1, 365 days)); }
```

## Anti-patterns (avoid)

- **Over-tight `require` in handlers** → fuzzer can never make a valid call → 0 coverage.
- **Minting tokens for free inside a handler** → creates impossible states → false positives.
- **Single actor** → misses all multi-user attacks.
- **No donation handler on balance-based accounting** → hides inflation bugs (Pattern F).
- **Forgetting `try/catch`** → first expected revert ends the sequence early.

## Always run `fuzzpipe coverage` after the first campaign

If any in-scope entry point shows `MISS`, the harness is incomplete - add/loosen the relevant
handler before trusting any "passed" result. This is the Stage 5 → Stage 3 loop-back.
