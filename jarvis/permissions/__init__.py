"""Permission system — 에이전트/행위별 명시 권한. AI는 자기 권한 확장 불가."""
from jarvis.permissions.policy import (  # noqa: F401
    ACTION_PERMISSIONS,
    FORBIDDEN,
    Level,
    PermissionDenied,
    Principal,
    check,
    require,
)
