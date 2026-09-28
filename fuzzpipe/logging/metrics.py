from __future__ import annotations
from typing import Optional
try:
    from prometheus_client import Counter, Histogram
except ImportError:
    # Prometheus not available; provide no-op stubs
    class _Noop:
        def inc(self, *args, **kwargs): pass
        def observe(self, *args, **kwargs): pass
        def labels(self, *args, **kwargs): return self
    Counter = lambda *a, **k: _Noop()
    Histogram = lambda *a, **k: _Noop()

RUN_DURATION = Histogram("fuzzpipe_run_duration_seconds", "Run duration", ["engine", "tier"])
ENGINE_STATUS = Counter("fuzzpipe_engine_status_total", "Engine run status", ["engine", "status"])
VERDICT_OUTCOME = Counter("fuzzpipe_verdict_outcome_total", "Verdict outcome", ["verdict"])