# Guidance 08 - Auto Threat-Model Generation (Stage 0, active)

> Pipeline Stage 0 - was *passive* (ingest an auditor's threat model if one exists, otherwise
> "Auto mode" with nothing to draw on). Now *active*: when no threat model is supplied, **generate
> one** from the contract surface so procedure 6 and the adversarial personas (`guidance/07`) always
> have real attacker goals to work from instead of degrading to ad-hoc brainstorming.
> An auditor-supplied threat model still takes priority and is **additive** - generation augments
> it, never replaces it.

## When to run

Always, at Stage 0. If the auditor provided a threat model / spec, parse it first (its "must /
never / only" sentences are HIGH-priority seeds - see `guidance/01` procedure 8). Then run
generation to fill the gaps the auditor may not have written down. Persist the merged result to
`.fuzzpipe/threatmodel.md`.

## What to extract from the contract surface

Read the in-scope sources (the same set `fuzzpipe ir coverage-audit` scans: `src/` or `contracts/`,
excluding test/lib/mocks). Build the model from five surfaces:

1. **Assets & value flows.** Every token/ETH balance the contract holds or accounts for, and every
   function that moves value in or out (deposit, withdraw, mint, burn, claim, skim, rescue, fees,
   reward accrual). *Attacker goal template:* "withdraw/claim more than my fair share", "strand
   value that should be claimable".
2. **Privileged roles & powers.** Every `onlyOwner`/`onlyRole`/access-gated function and what it can
   change. *Attacker goal template:* "as a non-privileged actor, perform this privileged action",
   "as the admin, exceed my legitimate powers and touch user funds".
3. **External calls & callbacks.** Every call to an address the protocol doesn't control (arbitrary
   ERC-20/721/777, receiver hooks, oracle reads, router calls). *Attacker goal template:* "re-enter
   through this callback", "return a hostile value from this external call".
4. **Price / oracle dependencies.** Every read of a price, rate, or supply used in a value
   calculation. *Attacker goal template:* "manipulate this input within a block", "feed a stale or
   extreme value".
5. **State machine & lifecycle.** Pause/upgrade/init hooks, phase flags, deadlines.
   *Attacker goal template:* "act outside the allowed phase", "brick a needed transition",
   "strand funds across a pause/upgrade".

## Output format (write to `.fuzzpipe/threatmodel.md`)

```markdown
# Threat model (auto-generated; merge with auditor input)

## Actors
- unprivileged user, third-party victim, privileged admin/keeper, external-contract counterparty

## Assets at risk
- <token/ETH balances, accounted totals, per-user entitlements>

## Attacker goals (each becomes an anti-property)
| # | Goal (one sentence) | Surface | Maps to persona (guidance/07) | Priority |
|---|---------------------|---------|-------------------------------|----------|
| G1 | withdraw more than deposited + earned | value flow | first-depositor / flash-loan | P0 |
| G2 | a non-owner calls setFee | privileged | malicious admin | P0 |
| G3 | inflate share price via direct donation | value flow | first-depositor | P0 |
| G4 | re-enter withdraw via token callback | external call | reentrancy composer | P0 |
| G5 | profit from same-block price move | oracle | MEV / oracle | P1 |
| ... | ... | ... | ... | ... |

## Trust assumptions (things NOT fuzzed, with why)
- <e.g. "the oracle is honest" — if the protocol assumes it, record it here and DON'T waste a
  campaign on it; but flag it as a residual risk in the SUMMARY>
```

## How it feeds the pipeline

- Each **attacker goal** row is an input to procedure 6 and to the matching persona in
  `guidance/07`, which turns it into a concrete `property_*` (or a `## NOT fuzzable` entry with a
  reason).
- **Trust assumptions** are recorded, not tested - but they must surface in `output/SUMMARY.md` as
  residual risk, so a "passing" campaign never implies an untested assumption is safe.
- The generated model is a **floor, not a ceiling**: the personas and the coverage critic still hunt
  for goals the surface scan didn't suggest.

## Honesty rule

An auto-generated threat model is a *hypothesis about attacker intent*, not ground truth. Never
present it to the auditor as "the" threat model - present it as "here is what the surface suggests an
attacker would target; confirm/extend before approval." The human checkpoint (Stage 2) is where the
auditor prunes and adds.
