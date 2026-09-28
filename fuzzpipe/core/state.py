from __future__ import annotations
from typing import Optional
import json
import datetime
from pathlib import Path

STATE_DIR_NAME = ".fuzzpipe"


def state_dir(target: Path) -> Path:
    return target / STATE_DIR_NAME


def load_state(target: Path) -> dict:
    f = state_dir(target) / "state.json"
    return json.loads(f.read_text()) if f.exists() else {}


def save_state(target: Path, state: dict) -> None:
    sd = state_dir(target)
    sd.mkdir(parents=True, exist_ok=True)
    state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (sd / "state.json").write_text(json.dumps(state, indent=2))


def set_stage(target: Path, stage: str, **extra: Any) -> None:
    st = load_state(target)
    st["stage"] = stage
    st.setdefault("history", []).append(
        {"stage": stage, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(), **extra})
    st.update(extra)
    save_state(target, st)