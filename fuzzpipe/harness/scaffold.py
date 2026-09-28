from __future__ import annotations
from typing import Optional
import json
import shutil
from pathlib import Path

from fuzzpipe.proc.runner import run_bounded
from fuzzpipe.core.state import state_dir, load_state, save_state, set_stage
from fuzzpipe.engines.sharding import _tester_rel_path, _disable_slither_for_hh3, _hardhat_major


def _compile_harness(target: Path, pt: str, timeout: int = 600) -> int:
    if pt == "hardhat" and shutil.which("npx"):
        run_bounded(["npx", "hardhat", "compile"], timeout, cwd=str(target), stream=False)
    if shutil.which("forge"):
        code, _ = run_bounded(["forge", "build"], timeout, cwd=str(target), stream=False)
        return code
    print(f"[warn] forge not installed - the engines need the Foundry compile layer. Install: {TOOLS['forge'][1]}")
    from fuzzpipe.proc.runner import RC_MISSING
    return RC_MISSING


DEFAULT_MEDUSA_WORKERS = 8

TOOLS = {
    "forge": ("forge", "curl -L https://foundry.paradigm.xyz | bash && foundryup"),
    "medusa": ("medusa", "go install github.com/crytic/medusa@latest"),
    "echidna": ("echidna", "see https://github.com/crytic/echidna/releases (download binary)"),
    "crytic-compile": ("crytic-compile", "pip install 'crytic-compile>=0.4'"),
    "halmos": ("halmos", "pip install halmos"),
    "slither": ("slither", "pip install slither-analyzer"),
    "node": ("node", "https://nodejs.org"),
    "npx": ("npx", "bundled with Node.js"),
}

CORE_FOR = {
    "scaffold": ["forge"], "build": ["forge"],
    "run-medusa": ["medusa", "crytic-compile"], "run-echidna": ["echidna", "crytic-compile"],
    "run-foundry": ["forge"], "run-halmos": ["halmos"], "triage": [],
    "scaffold-hardhat": ["forge", "npx"], "build-hardhat": ["forge"],
    "run-medusa-hardhat": ["medusa", "crytic-compile"], "run-echidna-hardhat": ["echidna", "crytic-compile"],
    "triage-hardhat": ["npx"],
}


def _detect_project_type(target: Path) -> Optional[str]:
    has_foundry = (target / "foundry.toml").exists()
    has_hardhat = any((target / ("hardhat.config." + ext)).exists() for ext in ("js", "ts", "cjs"))
    if has_hardhat and not has_foundry:
        return "hardhat"
    if has_hardhat and has_foundry:
        st = load_state(target)
        if st.get("project_type"):
            return st["project_type"]
        return "foundry"
    if has_foundry:
        return "foundry"
    return None


def _project_type(target: Path, override: Optional[str] = None) -> Optional[str]:
    if override:
        st = load_state(target)
        st["project_type"] = override
        save_state(target, st)
        return override
    st = load_state(target)
    if st.get("project_type"):
        return st["project_type"]
    pt = _detect_project_type(target)
    if pt:
        st["project_type"] = pt
        save_state(target, st)
    return pt


def _recon_dir(target: Path, pt: str) -> Path:
    if pt == "hardhat":
        return target / "contracts" / "recon"
    return target / "test" / "recon"


def _hardhat_config_path(target: Path) -> Path | None:
    for ext in ("ts", "cjs", "js"):
        p = target / ("hardhat.config." + ext)
        if p.exists():
            return p
    return None


def _crytic_compile_version() -> Optional[str]:
    from fuzzpipe.proc.runner import run_probe
    code, out = run_probe(["crytic-compile", "--version"])
    if code == 0 and out.strip():
        return out.strip().split()[-1]
    return None


def _ensure_chimera_lib(target: Path, offline: bool = False) -> bool:
    have_lib = (target / "lib" / "chimera").exists()
    if not have_lib:
        if offline:
            return (target / "lib" / "chimera").exists()
        if shutil.which("forge"):
            code, _ = run_bounded(["forge", "install", "Recon-Fuzz/chimera", "--no-git"], 120, cwd=str(target))
            if code != 0:
                code, _ = run_bounded(["forge", "install", "Recon-Fuzz/chimera"], 120, cwd=str(target))
        else:
            code, _ = run_bounded(["git", "clone", "--depth", "1", "https://github.com/Recon-Fuzz/chimera", "lib/chimera"], 120, cwd=str(target))
        if code != 0 or not (target / "lib" / "chimera").exists():
            return False
    if not (target / "lib" / "setup-helpers").exists() and not offline:
        if shutil.which("forge"):
            run_bounded(["forge", "install", "Recon-Fuzz/setup-helpers", "--no-git"], 120, cwd=str(target))
        else:
            run_bounded(["git", "clone", "--depth", "1", "https://github.com/Recon-Fuzz/setup-helpers", "lib/setup-helpers"], 120, cwd=str(target))
    return True


def _ensure_remappings(target: Path) -> None:
    remap = target / "remappings.txt"
    lines = remap.read_text().splitlines() if remap.exists() else []
    wanted = [("@chimera/", "@chimera/=lib/chimera/src/"),
              ("@recon/", "@recon/=lib/setup-helpers/src/"),
              ("forge-std/", "forge-std/=lib/forge-std/src/")]
    for prefix, line in wanted:
        if not any(l.startswith(prefix) for l in lines):
            lines.append(line)
    remap.write_text("\n".join(lines) + "\n")


def _write_recon_stubs(recon: Path, force: bool, include_foundry_repro: bool = True) -> None:
    recon.mkdir(parents=True, exist_ok=True)
    stubs = {
        "Setup.sol": _stub_setup(),
        "TargetFunctions.sol": _stub_targets(),
        "Properties.sol": _stub_properties(),
        "BeforeAfter.sol": _stub_beforeafter(),
        "CryticTester.sol": _stub_crytictester(),
    }
    if include_foundry_repro:
        stubs["CryticToFoundry.sol"] = _stub_crytictofoundry()
    for fname, content in stubs.items():
        fp = recon / fname
        if not fp.exists() or force:
            fp.write_text(content)


def _stub_setup() -> str:
    return ('// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n'
            'import {BaseSetup} from "@chimera/BaseSetup.sol";\n\n'
            '// Stage 3 (skill) fills this: deploy the protocol, create actors, fund balances.\n'
            'abstract contract Setup is BaseSetup {\n'
            '    function setup() internal virtual override {\n'
            '        // TODO(skill): deploy target contracts + mock assets, register actors.\n'
            '    }\n}\n')


def _stub_targets() -> str:
    return ('// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n'
            'import {BaseTargetFunctions} from "@chimera/BaseTargetFunctions.sol";\n'
            'import {Properties} from "./Properties.sol";\n\n'
            '// Stage 3: run `fuzzpipe gen-handlers` to AUTO-GENERATE the complete ABI-driven call\n'
            '// surface (TargetFunctionsAuto.sol). The skill only tunes clamps/Setup and adds\n'
            '// invariant-asserting handlers here; a handler_* named the same as a generated one\n'
            '// wins (MANUAL-OVERRIDE) so there is no duplicate-definition conflict.\n'
            'abstract contract TargetFunctions is BaseTargetFunctions, Properties {\n'
            '    // function handler_deposit(uint256 assets) public { ... }\n}\n')


def _stub_properties() -> str:
    return ('// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n'
            'import {BeforeAfter} from "./BeforeAfter.sol";\n'
            'import {Asserts} from "@chimera/Asserts.sol";\n\n'
            '// Stage 3 (skill) fills this: one boolean property_* per approved invariant (mapped to its IR id).\n'
            'abstract contract Properties is BeforeAfter, Asserts {\n'
            '    // function property_INV_SOLVENCY() public returns (bool) { ... }\n}\n')


def _stub_beforeafter() -> str:
    return ('// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n'
            'import {Setup} from "./Setup.sol";\n\n'
            '// Stage 3 (skill) fills this: ghost-variable snapshots before/after each call.\n'
            'abstract contract BeforeAfter is Setup {\n'
            '    struct Vars { uint256 placeholder; }\n'
            '    Vars internal _before;\n    Vars internal _after;\n\n'
            '    modifier updateGhosts() {\n        __snapshot(_before);\n        _;\n'
            '        __snapshot(_after);\n    }\n\n'
            '    function __snapshot(Vars storage v) internal {\n        v.placeholder = 0;\n    }\n}\n')


def _stub_crytictester() -> str:
    return ('// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n'
            'import {TargetFunctions} from "./TargetFunctions.sol";\n'
            'import {CryticAsserts} from "@chimera/CryticAsserts.sol";\n\n'
            '// Echidna/Medusa entrypoint. Usually left as-is.\n'
            'contract CryticTester is TargetFunctions, CryticAsserts {\n'
            '    constructor() payable {\n        setup();\n    }\n}\n')


def _stub_crytictofoundry() -> str:
    return ('// SPDX-License-Identifier: MIT\npragma solidity ^0.8.20;\n\n'
            'import {Test} from "forge-std/Test.sol";\n'
            'import {TargetFunctions} from "./TargetFunctions.sol";\n'
            'import {FoundryAsserts} from "@chimera/FoundryAsserts.sol";\n\n'
            '// Foundry entrypoint + home for reproducer tests (Stage 5 verdict gate writes here).\n'
            'contract CryticToFoundry is Test, TargetFunctions, FoundryAsserts {\n'
            '    function setUp() public {\n        setup();\n    }\n}\n')


def load_state(target: Path) -> dict:
    f = state_dir(target) / "state.json"
    return json.loads(f.read_text()) if f.exists() else {}


def save_state(target: Path, state: dict) -> None:
    sd = state_dir(target)
    sd.mkdir(parents=True, exist_ok=True)
    import datetime
    state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (sd / "state.json").write_text(json.dumps(state, indent=2))


def set_stage(target: Path, stage: str, **extra: Any) -> None:
    st = load_state(target)
    st["stage"] = stage
    st.setdefault("history", []).append(
        {"stage": stage, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(), **extra})
    st.update(extra)
    save_state(target, st)


import datetime


def scaffold(target: Path, project_type: Optional[str] = None, force: bool = False, offline: bool = False) -> int:
    """Generate Chimera harness. Returns 0 on success."""
    pt = _project_type(target, project_type)
    if pt == "hardhat":
        return _scaffold_hardhat(target, force, offline)
    if pt is None:
        print("[warn] No project type detected; assuming Foundry. Pass --project-type hardhat for Hardhat.")
    return _scaffold_foundry(target, force, offline)


def _scaffold_foundry(target: Path, force: bool, offline: bool) -> int:
    missing = [t for t in CORE_FOR["scaffold"] if not shutil.which(TOOLS[t][0])]
    if missing and not offline:
        print(f"[error] cannot scaffold - missing tools: {', '.join(missing)}")
        for m in missing:
            print(f"  install {m}: {TOOLS[m][1]}")
        return 1
    recon = _recon_dir(target, "foundry")
    if recon.exists() and not force:
        print(f"[warn] recon harness already exists at {recon} (use --force to regenerate)")
        set_stage(target, "1-scaffold", harness=str(recon), project_type="foundry")
        return 0
    print("[fuzzpipe] Scaffolding Chimera harness (Foundry)...")
    lib_ok = _ensure_chimera_lib(target, offline)
    _ensure_remappings(target)
    _write_recon_stubs(recon, force, include_foundry_repro=True)
    set_stage(target, "1-scaffold", harness=str(recon), project_type="foundry", chimera=lib_ok)
    print(f"[ok] Chimera harness skeleton created at {recon}")
    if not lib_ok:
        print("[warn] lib/chimera not vendored yet - `build` will fail until you install it (see above). "
             "The skeleton is written so you can vendor + build when ready.")
    print("[fuzzpipe] Stubs: Setup, TargetFunctions, Properties, BeforeAfter, CryticTester, CryticToFoundry.")
    print("[fuzzpipe] Next: `verify-harness` (preflight), then Stage 2 (invariant discovery).")
    return 0


def _scaffold_hardhat(target: Path, force: bool, offline: bool) -> int:
    missing = [t for t in CORE_FOR["scaffold-hardhat"] if not shutil.which(TOOLS[t][0])]
    if missing and not offline:
        print(f"[error] cannot scaffold (Hardhat) - missing tools: {', '.join(missing)}")
        for m in missing:
            print(f"  install {m}: {TOOLS[m][1]}")
        return 1
    recon = _recon_dir(target, "hardhat")
    if recon.exists() and not force:
        print(f"[warn] recon harness already exists at {recon} (use --force to regenerate)")
        set_stage(target, "1-scaffold", harness=str(recon), project_type="hardhat")
        return 0
    print("[fuzzpipe] Scaffolding Chimera harness (Hardhat: adding a Foundry compile layer)...")
    lib_ok = _ensure_chimera_lib(target, offline)
    _ensure_remappings(target)
    ftoml = target / "foundry.toml"
    if not ftoml.exists() or force:
        ftoml.write_text('[profile.default]\nsrc = "contracts"\nout = "out"\n'
                         'libs = ["lib"]\ntest = "contracts"\n')
        print("[fuzzpipe] wrote foundry.toml (src=contracts) - required by hardhat-foundry")
    if not offline and _ensure_hardhat_foundry_plugin(target) != 0:
        print("[warn] hardhat-foundry plugin not fully wired - see messages above. Scaffold continues.")
    _write_recon_stubs(recon, force, include_foundry_repro=False)
    repro_dir = target / "foundry-repro"
    repro_dir.mkdir(parents=True, exist_ok=True)
    repro_file = repro_dir / "CryticToFoundry.sol"
    if not repro_file.exists() or force:
        repro_file.write_text(_stub_crytictofoundry())
    set_stage(target, "1-scaffold", harness=str(recon), project_type="hardhat", chimera=lib_ok)
    print(f"[ok] Chimera harness skeleton created at {recon}")
    print("[fuzzpipe] Next: `verify-harness` (preflight), then Stage 2 (invariant discovery).")
    return 0


def _ensure_hardhat_foundry_plugin(target: Path) -> int:
    if (target / "pnpm-lock.yaml").exists():
        install = ["pnpm", "add", "-D", "@nomicfoundation/hardhat-foundry@^1.1.0"]
    elif (target / "yarn.lock").exists():
        install = ["yarn", "add", "-D", "@nomicfoundation/hardhat-foundry@^1.1.0"]
    else:
        install = ["npm", "install", "--save-dev", "@nomicfoundation/hardhat-foundry@^1.1.0"]
    if not (target / "node_modules" / "@nomicfoundation" / "hardhat-foundry").exists():
        code, _ = run_bounded(install, 120, cwd=str(target))
        if code != 0:
            print("[warn] could not install @nomicfoundation/hardhat-foundry. Install manually:")
            print("  " + " ".join(install))
            return 1
    cfg = _hardhat_config_path(target)
    if not cfg:
        print("[warn] no hardhat.config.* found to wire the plugin into.")
        return 1
    text = cfg.read_text()
    if "hardhat-foundry" in text:
        return 0
    bak = cfg.with_suffix(cfg.suffix + ".bak")
    if not bak.exists():
        bak.write_text(text)
    line = ('import "@nomicfoundation/hardhat-foundry";\n'
            if cfg.suffix == ".ts" or "export default" in text or "import " in text
            else 'require("@nomicfoundation/hardhat-foundry");\n')
    cfg.write_text(line + text)
    print(f"[fuzzpipe] loaded hardhat-foundry in {cfg.name} (backup: {bak.name})")
    return 0