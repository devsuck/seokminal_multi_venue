"""jarvis.research_compliance — Research Compliance & Integrity Governance Layer (P10.19). **관찰 전용.**

P9.8~P10.18 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 연구 산출물이 거버넌스 기준을 준수하도록
컴플라이언스 규칙 레지스트리·연구 무결성 점검·증거 레지스트리·컴플라이언스 검토·위반 기록·시정 권고·감사
리포트·컴플라이언스 계보를 제공한다. 규칙 준수·증거 가용성·재현성 요건·연구 무결성 리스크·감사 이력을 추적한다.

**위반 자동 수정·연구 산출물 수정·배포 승인·permission 변경·실행 상태 변경 없음.** execution/broker/order/
portfolio execution/capital allocation/live trading/permission/risk controller import·호출 없음. COMPLIANCE
CHECK ≠ APPROVAL · VIOLATION DETECTION ≠ CORRECTION · RECOMMENDATION ≠ ACTION · AUDIT RESULT ≠ DEPLOYMENT
PERMISSION. append-only 해시체인·결정적·재현. 물리 원장은 rc_ 접두사.
"""
from jarvis.research_compliance.engine import ResearchComplianceEngine  # noqa: F401
from jarvis.research_compliance.models import (  # noqa: F401
    ACCEPT,
    ARCHIVED,
    AT_RISK,
    COMPLIANT,
    DETECTED,
    FAIL,
    NON_COMPLIANT,
    PASS,
    REJECT,
    REQUEST_CHANGE,
    RESOLVED,
    REVIEWED,
    RULE_CATEGORIES,
    WARNING,
    AuditReport,
    ComplianceArtifact,
    ComplianceCheck,
    ComplianceRule,
    ComplianceSummary,
    EvidenceRecord,
    IllegalTransition,
    ImmutableCheckError,
    ImmutableEvidenceError,
    ImmutableRuleError,
    InvalidCheckResult,
    InvalidReviewDecision,
    InvalidRuleCategory,
    InvalidViolationCategory,
    MissingReviewer,
    RemediationRecommendation,
    ReviewRecord,
    UnknownRule,
    UnknownViolation,
    ViolationEvent,
)
