# Guidance 06 - Authoring the typed Invariant IR

> Pipeline Stage 2. After the 9-procedure derivation fills the human `invariants.md` table, emit the
> **typed Invariant IR** (`.fuzzpipe/invariants.json`) - the machine contract the harness generator
> and the verdict gate consume. The table stays for auditors; the IR is for the tooling. Both
> describe the same invariants.

## Why a typed artifact

The Markdown table is for humans; it cannot be validated or consumed programmatically without
guessing. The IR gives every invariant a stable `id`, a machine-checkable `category`/`shape`/`scope`,
a `predicate`, a `tier_hint`, and a `status`. That lets the CLI: map each `property_*` back to its
invariant, stage a per-invariant campaign, and attribute a break to the right invariant at the gate.

## The fields

| Field | Meaning |
|-------|---------|
| `id` | `^INV-[A-Z0-9-]+$`, unique. Also the marker embedded in the PoC's harm assertion. |
| `statement` | plain-English, falsifiable ("assets >= liabilities at all times"). |
| `category` | function \| valid-state \| stateful-sequence \| solvency \| anti-property. |
| `shape` | SAFETY \| LIVENESS \| CORRECTNESS \| AUTHORIZATION. |
| `scope` | guard \| global \| cross_contract \| economic. |
| `predicate` | `{"expr": "assets >= owed", "helpers": [...]}` - the checkable form. |
| `priority` | P0..P3 (P0 = threat-model / must-hold). |
| `targets` | entry points it constrains (`["Vault.deposit", ...]`). |
| `tolerance` | acceptable slack (`"±1 wei/user"`). |
| `derived_via` | which of the 9 procedures produced it. |
| `source` | seed \| discovered \| library \| threat-model. |
| `severity_if_broken` | critical \| high \| medium \| low \| informational. |
| `tier_hint` | 0..3 - the ladder tier this invariant expects (0 forge, 1 fuzz, 2 symbolic). |
| `status` | candidate → approved → CONFIRMED / SUSPECTED / NO-CE-IN-BUDGET / PROVEN-IN-BOUND-K / UNTESTED. |

## Cross-field rules (enforced by `fuzzpipe ir validate`)

- ids match `^INV-[A-Z0-9-]+$` and are unique.
- `category`/`shape`/`scope`/`severity_if_broken`/`status` are from their allowed sets.
- `scope == economic` ⇒ `tier_hint >= 1` (economic invariants need stateful fuzzing, not just a smoke test).
- `tier_hint >= 2` ⇒ **critical, bounded, non-economic SAFETY/CORRECTNESS** only (Tier-2 symbolic is
  expensive and eval-gated; it is not for economic or best-effort properties).

A validation failure blocks progress - fix the IR before Stage 3.

## Example

```json
{
  "invariants": [
    {
      "id": "INV-SOLVENCY",
      "statement": "vault assets always cover liabilities",
      "category": "solvency",
      "shape": "SAFETY",
      "scope": "global",
      "predicate": {"expr": "assets >= owed", "helpers": ["totalOwed()"]},
      "priority": "P0",
      "targets": ["Vault.deposit", "Vault.withdraw", "Vault.donate"],
      "tolerance": "0",
      "derived_via": "procedure-3 value-flow conservation",
      "source": "discovered",
      "severity_if_broken": "critical",
      "tier_hint": 1,
      "status": "candidate"
    }
  ]
}
```

## Workflow

```bash
fuzzpipe ir put   --target <t> --file ir.json     # validates, then stores
fuzzpipe ir validate --target <t>                 # re-check the stored IR
fuzzpipe ir list  --target <t>                    # one line per invariant
fuzzpipe ir candidates --target <t>               # only status=candidate (pre-approval)
```

Only `status: approved` invariants (post human checkpoint) become harness `property_*` functions and
are eligible for the ladder. Set the status at approval time; the gate writes back the final verdict
(CONFIRMED/SUSPECTED/NO-CE-IN-BUDGET/PROVEN-IN-BOUND-K/UNTESTED).
