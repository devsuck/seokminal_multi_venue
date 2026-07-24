"""jarvis.security_audit — Security Hardening & Audit Layer (P38). **감사 전용, 실행 권한 없음.**

최종 보안 감사: 원장 보안(해시체인·변조 탐지·재현)·아키텍처 보안(금지 import·권한 경계·소유권 위반)·런타임 보안(불안전
실행 경로·숨은 배포 능력·우발적 거래 메서드). 보안 감사 리포트·검증 스크립트를 소유한다.

**엔진은 execute/trade/deploy/allocate/approve 를 노출하지 않는다.** execution/broker/live_trading/
portfolio_execution import·호출 없음. AUDIT ≠ EXECUTION · VALIDATION ≠ MUTATION. 불변·append-only·해시체인·결정적·
재현. 원장 secaud_ 접두사. 새 원장 연구 지능 없음.
"""
from jarvis.security_audit.engine import SecurityAuditEngine  # noqa: F401
from jarvis.security_audit.models import (  # noqa: F401
    AUDIT_DIMENSIONS,
    AUDIT_TARGETS,
    FORBIDDEN_ENGINE_METHODS,
    ArtifactRecord,
    AuditRecord,
    AuditSummary,
    SecurityFindingRecord,
    SecurityReportRecord,
    verify_hash_records,
)
