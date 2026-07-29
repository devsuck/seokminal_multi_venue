"""jarvis.self_audit_intelligence — Research Self Audit Intelligence Layer (P10.24). **READ ONLY 감사 전용.**

전 연구 생태계(P9.8~P10.23)의 무결성을 검증하는 메타 감사 시스템이다. 전 계층 원장을 **READ ONLY** 로 검사
(파일 기반, import 없음)해 감사 레지스트리·감사 실행·무결성 점검·위반 기록·감사 리포트·감사 계보를 제공하며
깨진 해시체인·누락 부모·유효하지 않은 생명주기·미문서화 변경·누락 검증을 탐지한다.

**원장·정책·config·permission·strategy·model 을 수정/복구/적용/배포하지 않는다.** execution/broker/order/
portfolio execution/capital allocation/live trading/permission/risk controller import·호출 없음. repair/
modify/fix/apply/deploy 메서드 없음. AUDIT ≠ REPAIR · FINDING ≠ FIX · INSPECTION ≠ MODIFICATION · REPORT ≠
ACTION. append-only 해시체인·결정적·재현. 물리 원장은 sa_ 접두사(Self Audit).
"""
from jarvis.self_audit_intelligence.engine import ResearchSelfAuditEngine  # noqa: F401
from jarvis.self_audit_intelligence.models import (  # noqa: F401
    ARCHIVED,
    COMPLETED,
    CREATED,
    CRITICAL,
    PASS,
    RUNNING,
    WARNING,
    AuditArtifact,
    AuditDefinition,
    AuditReport,
    AuditRunEvent,
    AuditSummary,
    IllegalTransition,
    ImmutableAuditError,
    IntegrityCheck,
    InvalidCheckKind,
    UnknownRun,
    ViolationRecord,
)
