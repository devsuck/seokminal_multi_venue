"""jarvis.execution_readiness — Execution Readiness Certification Layer (P7.7).

모든 통제 레이어(P7.4~P7.6 + 프로덕션/리스크/브로커/시장데이터) 집계 →
ExecutionReadinessCertificate(READY/BLOCKED). P8 Live Execution 전 최종 인증 경계.
**이 인증서는 거래 허가가 아니다** — "시스템이 프리플라이트 검사를 통과했다"만 진술.
집행 게이트웨이 import 금지·브로커 주문 없음·게이트웨이 호출 없음·자본 배치 없음.
하위 레이어 읽기전용·append-only 감사·결정적·재현가능. 신규 권한 없음.
"""
from jarvis.execution_readiness.engine import ExecutionReadinessEngine  # noqa: F401
from jarvis.execution_readiness.models import (  # noqa: F401
    BLOCKED,
    READY,
    ExecutionReadinessCertificate,
    ReadinessCheck,
)
