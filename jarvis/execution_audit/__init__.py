"""jarvis.execution_audit — Execution Audit & Attestation Layer (P8.6). **AUDIT-ONLY.**

Request(P8.1)+Lifecycle(P8.2)+Reconciliation(P8.3)+Cost(P8.4)+Risk(P8.5) →
ExecutionAuditCertificate. "모든 것이 내부적으로 일관됨"만 진술 — **거래를 승인하지 않는다.**
15개 교차검증 검사·append-only 해시체인·결정적 재현. 읽기전용.

집행 게이트웨이/live/paper/risk거버너 import 없음·주문/집행/브로커 호출 없음·상태 변경 없음.
하위 원장은 데이터 파일로만 읽음. 신규 권한 없음.
"""
from jarvis.execution_audit.engine import ExecutionAuditEngine  # noqa: F401
from jarvis.execution_audit.models import (  # noqa: F401
    FAILED,
    PASS,
    WARNING,
    AuditCheck,
    ExecutionAuditCertificate,
)
