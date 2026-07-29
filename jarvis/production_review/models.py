"""Production Readiness Review 자료형 (P39) — 내부 프로덕션 준비성 평가. **배포 없음, 평가만.**

Jarvis 가 내부 프로덕션 사용에 준비되었는지 검증한다: 배포 체크리스트·환경 요구사항·설정 검토·복구 절차·백업 전략·모니터링
체크리스트·실패 시나리오·운영 절차. 재현성·복구성·관측성·유지보수성을 검증한다. **프로덕션 배포 없음 — 준비성 평가만.**
READINESS ≠ DEPLOYMENT · ASSESSMENT ≠ EXECUTION. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

import hashlib
import json

# ── 생성 문서(8종) ──
PRODUCTION_DOCS = (
    "01_deployment_checklist.md",
    "02_environment_requirements.md",
    "03_configuration_review.md",
    "04_recovery_procedures.md",
    "05_backup_strategy.md",
    "06_monitoring_checklist.md",
    "07_failure_scenarios.md",
    "08_operational_procedures.md",
)

# ── 준비성 평가 차원 ──
READINESS_DIMENSIONS = ("REPRODUCIBILITY", "RECOVERABILITY", "OBSERVABILITY", "MAINTAINABILITY")

# ── 배포 체크리스트 항목 ──
DEPLOYMENT_CHECKLIST = (
    "모든 원장 append-only·SHA256 해시체인 검증 통과",
    "전체 회귀 테스트 통과 (0 regressions)",
    "보안 감사 통과 (0 failed findings)",
    "결정적 재현 검증 통과",
    "소유권 경계 유일성 확인",
    "금지 import·실행 메서드 부재 확인",
    "실행/거래/배포 권한 부재 확인",
    "환경 변수·설정 검토 완료",
)

# ── 환경 요구사항 ──
ENVIRONMENT_REQUIREMENTS = (
    "Python 3.11+",
    "pytest (테스트 실행)",
    "쓰기 가능한 _state/ 디렉터리 (append-only JSONL 원장)",
    "네트워크 불필요 (오프라인 결정적 동작)",
    "브로커·거래 연결 불필요·금지",
)

# ── 실패 시나리오 ──
FAILURE_SCENARIOS = (
    "원장 파일 손상 → verify_chain 이 변조·체인 단절 탐지 → 복구 절차",
    "부분 쓰기 → append-only 이므로 마지막 유효 레코드까지 재생 가능",
    "상위 원장 부재 → source_count 0 반환(안전), 이상 탐지 기록",
    "중복 genesis → duplicate_integrity 탐지",
    "디스크 부족 → 쓰기 실패(원자적), 기존 원장 불변 유지",
)


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def doc_hash(content) -> str:
    return _digest({"content": content})
