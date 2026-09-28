from __future__ import annotations
from pathlib import Path
from typing import Protocol, TypedDict, Literal
try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired


class CampaignConfig(TypedDict):
    target: Path
    depth: int
    limit: int
    budget_s: int
    corpus_dir: Path
    config_overrides: NotRequired[dict]


class RunResult(TypedDict):
    status: Literal["clean", "break_or_error", "untested"]
    rc: int
    output: str
    artifacts: dict


class FailingSequence(TypedDict):
    method: str
    sig: str
    types: list[str]
    values: list
    sender: str
    block_delay: int
    time_delay: int


class EngineAdapter(Protocol):
    name: str
    version: str
    required_binaries: tuple[str, ...]

    async def prepare(self, config: CampaignConfig) -> None: ...
    async def run(self, config: CampaignConfig) -> RunResult: ...
    def parse_results(self, corpus_dir: Path) -> list[tuple[str, list[FailingSequence]]]: ...
    def generate_config(self, config: CampaignConfig) -> Path: ...