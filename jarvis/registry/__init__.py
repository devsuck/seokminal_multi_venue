"""Strategy Registry — 불변 상태전이 장부. 불법전이 거부, config 동결, rejected 보존."""
from jarvis.registry.lifecycle import (  # noqa: F401
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    STATUSES,
    Status,
    StrategyRegistry,
    config_hash,
)
