# Guidance 09 — Canonical Invariant Library (Stage 2 backbone)

> Pipeline Stage 2, run **FIRST** — before the open-ended derivation procedures of `guidance/01`.
> The library is the high-signal backbone: a curated set of battle-tested invariants a skilled
> auditor writes on autopilot. Instantiating them first fixes the two failure modes of a pure
> procedure-checklist run: (a) **unintuitive, over-engineered invariants** (complex bespoke
> formulas that miss the obvious solvency/conservation property and often don't even compile), and
> (b) **coverage of the *invariant set* that looks broad but skips the canonical bug classes.**
> Machine-readable form: `templates/invariant-library.json` (30 templates).

## Why library-first

A pure 11-procedure + 7-persona run is a firehose. In batch/automated mode it tends to emit many
complex, low-signal candidates while the *canonical* ones (protocol solvency, value conservation,
supply integrity, negative access control) get buried or mis-implemented. The library inverts the
order: **bind the proven templates first, then let the procedures/personas add only what is
protocol-specific on top.** Result: fewer, simpler, grounded invariants that implement and compile
cleanly — which also removes a common SUSPECTED cause (the generated PoC didn't compile).

## The Stage-2 order (do these in sequence)

1. **Detect the target's token standards + protocol type(s).** ERC20/721/4626/7540; and
   vault/staking, lending/CDP, AMM/DEX, perps, bridge, oracle-dependent, governance, NFT, auction,
   restaking, intents. More than one may apply — a vault priced off an oracle pulls both rows.
2. **Pull every matching library template** (`protocol_types` includes `*` or your type;
   `token_standards` empty or matching). Always include the universal `*` templates: `LIB-SOLVENCY`,
   `LIB-CONSERVATION`, `LIB-SUPPLY-INTEGRITY`, `LIB-NO-UNDERFLOW-ACCOUNTING`, `LIB-ACCESS-NEGATIVE`,
   `LIB-THIRD-PARTY-ISOLATION`, `LIB-ROUNDTRIP-NO-PROFIT`, `LIB-REENTRANCY-STATE-AT-CALLBACK`.
3. **Bind each template's `binds` symbols to the target's real identifiers.** Map `asset` →
   the actual token, `protocol` → the deployed instance, `_totalObligations()` → the concrete sum
   over the protocol's user-owed mappings. Drop the template's reference `property` into
   `Properties.sol` and add its `ghosts` to `BeforeAfter.sol`. The implementation is meant to be
   near-mechanical — that is the point.
4. **If a template cannot be bound**, skip it with a one-line reason (e.g. "no reward path" →
   skip `LIB-REWARD-*`). Never force a template that doesn't fit; a forced invariant is a
   false-positive generator. Record the skip like a waiver.
5. **THEN run `guidance/01` procedures 1–11 + `guidance/07` personas** to add invariants the
   library can't know — protocol-specific couplings, bespoke state machines, novel attacker goals.
   The library is the floor, not the ceiling.
6. Run the completeness gate (`guidance/01` + `fuzzpipe ir coverage-audit`) over the **union**.

## Grounding requirement (every emitted invariant)

An invariant ships only if it carries, in its IR/`invariants.md` row:

- **A concrete code reference** — the exact state variable(s)/function(s) it constrains (so Stage 3
  can implement it directly and Stage 5 can attribute a break).
- **Its origin** — the `LIB-*` template id, or the `guidance/01` procedure number / `guidance/07`
  persona it came from. No free-associated invariant without a traceable source.
- **A one-line harm** — the concrete consequence if it breaks (who loses what). If you cannot state
  the harm, the invariant is probably too weak (tests nothing) — cut it.
- **A reference implementation that compiles** — reuse the template's `property`, or write the
  equivalent, and confirm `fuzzpipe build` passes before approval. An invariant whose property
  doesn't compile is not a candidate; it's a bug in the candidate.

Ungrounded, harm-less, or non-compiling candidates are rejected at the approval checkpoint — this
is what keeps the set small, intuitive, and high-signal.

## Template anatomy (`templates/invariant-library.json`)

| field | meaning |
|-------|---------|
| `id` | `LIB-*` stable id; becomes the IR `source` trace and the `property_LIB_*` name |
| `category` / `shape` / `priority` | map straight onto the typed IR fields |
| `protocol_types` / `token_standards` | selectors for step 2 (`*` = universal) |
| `binds` | the symbols you must map to the target — the only manual step |
| `statement` | the falsifiable property in plain terms |
| `property` | the reference `property_*` / attacker-handler implementation to drop in |
| `ghosts` | `BeforeAfter.sol` fields the property needs (add them once) |
| `tolerance` | when `>=`/`<=`/`approxEqAbs` is correct vs exact (avoids over-strong FP churn) |
| `harm` | the grounding one-liner (who loses what) |
| `derived_via` | the origin trace for the grounding requirement |

## Relationship to the rest of the pipeline

- Coverage of *code* is handled mechanically by `fuzzpipe gen-handlers` (complete ABI-driven call
  surface) + the `fuzzpipe coverage --gate` block — NOT by how many invariants you write. So the
  library exists purely to make the invariants themselves **correct, simple, and complete over the
  canonical bug classes**; you do not need extra invariants just to drive the fuzzer into a
  function (a handler already does that). See `guidance/02` and SKILL.md Stage 3–4.
- The library is additive to Stage-0 seed invariants and the auto threat model (`guidance/08`) —
  merge, dedup by `statement`, and keep the seed/threat-model priority.
