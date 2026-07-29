"""jarvis.access_governance — Access Governance & Operator Identity Layer (P9.10). **감사 전용.**

운영자/역할을 불변으로 등록하고 세션·접근요청(REQUESTED→REVIEWED→APPROVED→EXPIRED)·승인·접근
감사를 관리한다. append-only 해시체인·결정적·재현가능.

**실제 권한 부여 없음·permission 변경 없음·role escalation 없음·operator action 실행 없음·
execution/kill switch/broker/trading access grant 없음.** 기존 permission 시스템은 READ ONLY(정책
대조용). 물리 원장은 ag_ 접두사(기존 approvals 원장과 충돌 회피).
"""
from jarvis.access_governance.engine import AccessGovernanceEngine  # noqa: F401
from jarvis.access_governance.models import (  # noqa: F401
    APPROVED,
    CRITICAL,
    EXPIRED,
    INFO,
    REJECTED,
    REQUESTED,
    REVIEWED,
    WARNING,
    AccessApproval,
    AccessAuditReport,
    AccessFinding,
    AccessGovernanceReport,
    AccessRequest,
    ApprovalError,
    IllegalTransition,
    ImmutableOperatorError,
    ImmutableRoleError,
    OperatorIdentity,
    RoleMetadata,
    SessionRecord,
)
