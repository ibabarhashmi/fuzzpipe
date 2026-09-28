# fuzzpipe

Verified-before-confirmed EVM/Solidity invariant fuzzing. CLI orchestrates Foundry, Medusa, Echidna, Halmos. Skill does the reasoning.

![version](https://img.shields.io/badge/version-v2.2-blue)
![tests](https://img.shields.io/badge/tests-127%20passing-brightgreen)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

## What it does

- Discovers invariants (11 procedures + 7 adversarial personas + auto threat model)
- Generates a complete Chimera harness (`gen-handlers` wires every mutating entry point)
- Runs tiered ladder: Forge → Medusa/Echidna (parallel, per-invariant shards) → Halmos (eval-gated)
- Every break goes through verdict gate: compiles → re-executes specific break → asserts harm
- CONFIRMED only with re-executing PoC. Everything else = SUSPECTED.

**Engines fuzz. This tool decides what to fuzz, why, and what results mean.**

## Quickstart

```bash
export PATH="$(pwd)/cli:$PATH"
fuzzpipe doctor

# with the agent (Claude/Cursor):
# /fuzzpipe-fuzzing "fuzz <solidity project>"

# or CLI directly (forge-only golden fixture):
T=examples/vulnerable-vault
fuzzpipe init             --target $T
fuzzpipe ir put           --target $T --file $T/ir.json
fuzzpipe ir coverage-audit --target $T
fuzzpipe run              --target $T --engine foundry
fuzzpipe verify --target $T --ce INV-SOLVENCY \
  --poc test/recon/CryticToFoundry.sol --test test_repro_INV_SOLVENCY --marker INV-SOLVENCY
```

## Architecture

Two layers, one contract. Skill reasons, CLI executes. Never cross wires.

```
AUDITOR: contracts + docs + optional threat model
    │
Stage 0: threat model + seeds (auto if none)
Stage 1: scaffold → Chimera recon/ skeleton
Stage 2: derive invariants → TABLE + typed IR
         └─► AUDITOR APPROVAL (mandatory)
Stage 3: generate harness → fill recon/ (Setup/Targets/Properties/BeforeAfter)
Stage 4: run ladder → Forge → Medusa‖Echidna (parallel) → Halmos*
         CE at any tier short-circuits ▼
Stage 5: verdict gate → lower CE → forge build → forge test → harm assert
Stage 6: report → CONFIRMED findings + honest SUMMARY
* Halmos eval-gated (FUZZPIPE_SYMBOLIC=1), critical SAFETY/CORRECTNESS only.
```

State lives in `<target>/.fuzzpipe/`: `state.json`, `invariants.md`, `invariants.json`, `threatmodel.md`, `runs/`, `corpus/`, `poc/`, `findings/`.

## CLI

```bash
fuzzpipe doctor          [-t <t>]         # toolchain check (never crashes)
fuzzpipe init            -t <t>           # create .fuzzpipe/
fuzzpipe scaffold        -t <t> [--offline]
fuzzpipe verify-harness  -t <t>           # preflight: engine sees harness
fuzzpipe build           -t <t>           # forge build (+ hardhat compile)
fuzzpipe ir  put|get|list|validate|candidates|coverage-audit -t <t> [--file]
fuzzpipe run             -t <t> [--max-tier N] [--engine E] [--budget S] [--jobs N] [--workers N] [--no-parallel]
fuzzpipe triage          -t <t>           # lower breaks + verdict gate
fuzzpipe verify          -t <t> --poc <f> --test <name> --marker <INV-ID>
fuzzpipe materiality     -t <t> --test <fn> --material <amt>
fuzzpipe coverage        -t <t> -e medusa # exit 2 = uncovered
fuzzpipe status          -t <t>
fuzzpipe selftest        [-v]             # regression suite (zero deps)
```

## Environment

| Variable | Effect |
|----------|--------|
| `FUZZPIPE_SYMBOLIC` | `=1` enables Halmos (Tier-2). Off by default. |
| `FUZZPIPE_SWEEP_AMOUNT` | set by `materiality` sweep. |
| `FUZZPIPE_LOG` | `=json` for machine-readable logs. |

Read in one place. `test_consistency` enforces docs = code.

## Install

CLI = Python 3.11+, stdlib only. Engines optional per `fuzzpipe doctor`.

```bash
# engines (forge required for verdict gate)
curl -L https://foundry.paradigm.xyz | bash && ~/.foundry/bin/foundryup
brew install medusa echidna
pip install 'crytic-compile>=0.4' slither-analyzer
# pip install halmos  # Tier-2

export PATH="$(pwd)/cli:$PATH"
fuzzpipe doctor
```

## Repository layout

```
├── cli/                    # fuzzpipe (Python, stdlib only)
│   ├── app.py             # Typer entry point
│   └── commands/          # 14 subcommands
├── fuzzpipe/              # core packages
│   ├── proc/              # async runner, real timeouts
│   ├── ir/                # typed Invariant IR + validation
│   ├── verdict/           # three-gate verdict
│   ├── engines/           # adapter protocol + registry
│   ├── harness/           # scaffold, handlers, config
│   ├── core/              # pipeline, state
│   └── logging/           # structlog + metrics
├── guidance/              # methodology (01-09)
├── examples/vulnerable-vault/  # golden fixture (4 bugs)
├── templates/             # finding.md, fuzzpipe.config.json
├── skill/fuzzpipe-fuzzing/   # orchestrator skill
├── tests/                 # 127 tests, 7 skipped
└── .github/workflows/selftest.yml
```

## Support matrix

`fuzzpipe doctor` prints the truth. Summary: `python3.11+` · `forge` required · `medusa`+`crytic-compile` / `echidna` optional (Tier-1) · `halmos` optional (Tier-2, eval-gated) · `slither` optional (dictionary seeds) · Node/`npx` for Hardhat only. Hardhat v2 and v3 supported (v3 needs `crytic-compile >= 0.4`).

## License

MIT — see `LICENSE`.
