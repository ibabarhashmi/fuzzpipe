from __future__ import annotations
import time
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable

import structlog

_current_span: ContextVar[dict] = ContextVar("current_span", default={})
log = structlog.get_logger()


def traced(operation: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            span = {"operation": operation, "start": time.time()}
            token = _current_span.set(span)
            try:
                return await func(*args, **kwargs)
            finally:
                span["duration"] = time.time() - span["start"]
                log.info("span_complete", **span)
                _current_span.reset(token)
        return wrapper
    return decorator


def get_current_span() -> dict:
    return _current_span.get()