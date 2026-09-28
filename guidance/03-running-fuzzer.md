# Guidance 03 - Configuring & Executing the Fuzzing Framework

> Pipeline Stage 4. Mostly mechanical - driven by `cli/fuzzpipe run`. This file documents
> what the CLI wraps and how to tune campaigns.

## Engine selection

| Engine | Command (via CLI) | Use for | Notes |
|--------|-------------------|---------|-------|
| **Foundry** | `fuzzpipe run --engine foundry` | quick smoke test | fast; **no coverage report for invariants** |
| **Medusa** | `fuzzpipe run --engine medusa` (DEFAULT) | deep stateful campaign | Go, parallel, coverage-guided; shrinking still maturing |
| **Echidna** | `fuzzpipe run --engine echidna` | targeted property cross-check | best shrinking; mature |

Recommended pipeline: smoke with Foundry → deep run with Medusa → cross-check key
properties with Echidna. Same Chimera harness, no rewrites.

## Two campaign dimensions

- **runs / test_limit** - how many call sequences are generated.
- **depth / sequence length** - how many calls per sequence.

Deeper sequences find deeper stateful bugs but cost time. Start moderate, increase depth if
coverage plateaus or you suspect long-sequence bugs.

## Config files the CLI manages

### `foundry.toml` (invariant section)
```toml
[invariant]
runs = 256
depth = 64
fail_on_revert = false        # handlers tolerate reverts
call_override = false
```

### `medusa.json` (key fields)
```json
{
  "fuzzing": {
    "workers": 8,
    "testLimit": 100000,
    "sequenceLength": 100,
    "corpusDirectory": ".fuzzpipe/corpus/medusa",
    "coverageEnabled": true
  },
  "testing": { "assertionTesting": { "enabled": true },
               "propertyTesting": { "enabled": true, "testPrefix": "property_" } }
}
```

### `echidna.yaml` (key fields)
```yaml
testMode: assertion
testLimit: 100000
seqLen: 100
corpusDir: .fuzzpipe/corpus/echidna
coverage: true
```

## Corpus reuse (big speedup)

Point each engine at a persistent `corpusDirectory`/`corpusDir` under `.fuzzpipe/corpus/`.
A saved corpus seeds later runs, so coverage compounds across sessions. The CLI sets this
up; don't delete it between runs unless the harness changed materially.

## Running

```bash
cli/fuzzpipe run --engine medusa            # default deep run
cli/fuzzpipe run --engine medusa --depth 200 --limit 500000   # heavier
cli/fuzzpipe run --engine echidna --property property_solvency # focus one property
```

The CLI streams progress and writes raw output + any broken-sequence artifacts to
`.fuzzpipe/runs/<engine>/`.

## When the campaign is "stuck"

Symptoms: coverage flat, no new corpus entries, properties never tested.
Fixes (apply, then re-run):
1. **Coverage check** (`coverage-analysis`) - find which code is unreached.
2. **Loosen clamps** in `TargetFunctions` so valid calls actually happen.
3. **`fuzzing-dictionary`** - feed magic constants the fuzzer can't guess.
4. **`fuzzing-obstacles`** - patch checksum gates, hardcoded addresses, time locks,
   global-state barriers that block progress.
5. **Add missing handlers** for entry points that gate the interesting state.

## Cloud / long runs (optional)

For multi-hour campaigns, Recon Pro's cloud runner (or CloudExec) can offload the job.
Out of scope for the local CLI v1, but the config files are compatible - note it as an
available scale path.

## Stop conditions

- A property breaks → stop, go to Stage 5 (triage). One real break is enough to act on.
- `testLimit` reached with no breaks → record coverage; a clean run is NOT proof of safety
  (see guidance 04).
- Coverage too low to trust the result → fix harness (Stage 3), don't report "safe."

## Time budgets (rules of thumb)

| Goal | testLimit | seqLen | typical time |
|------|-----------|--------|--------------|
| Smoke | 10k | 50 | seconds-minutes |
| Standard | 100k | 100 | minutes-~1h |
| Deep | 500k+ | 200+ | hours (consider cloud) |

---

## Hardhat projects (v2)

The pipeline supports Hardhat v2 in addition to Foundry. The project type is auto-detected
(`hardhat.config.{js,ts,cjs}` → Hardhat); override with `--project-type hardhat`.

**How it works:** Medusa/Echidna compile via crytic-compile, which needs a Foundry layer to
resolve the Chimera `@chimera/*` imports. `fuzzpipe scaffold` adds this automatically:
`foundry.toml` (required by the hardhat-foundry plugin), `lib/chimera`, `remappings.txt`, and
`@nomicfoundation/hardhat-foundry` (loaded into `hardhat.config.*`, original backed up). The
harness lives in **`contracts/recon/`** (Hardhat only compiles `contracts/`). After that, the
standard Foundry run path applies unchanged - `medusa.json` still targets
`contracts/recon/CryticTester.sol`.

- `fuzzpipe build` runs `npx hardhat compile` + `forge build`.
- `fuzzpipe run --engine medusa|echidna` works identically to Foundry.
- The `foundry` engine is unavailable on Hardhat (it needs Foundry test wiring) - use medusa/echidna.

**Hardhat version handling:** both v2 and v3 are supported.
- **Hardhat 2** works with any recent crytic-compile.
- **Hardhat 3** requires **crytic-compile ≥ 0.4** (it reads HH3's split `.json` + `.output.json`
  build-info). The tool auto-detects the Hardhat version and, on v3, sets `useSlither: false` in
  the generated `medusa.json` to avoid a slither↔crytic-compile version-pin conflict (slither only
  seeds the fuzzing dictionary - fuzzing is unaffected). If your crytic-compile is < 0.4, `fuzzpipe`
  warns you to upgrade (`pip install --upgrade 'crytic-compile>=0.4'`).
