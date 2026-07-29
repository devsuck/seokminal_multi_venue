"""jarvis.production_review — Production Readiness Review (P39). **배포 없음, 준비성 평가만.**

Jarvis 의 내부 프로덕션 준비성을 평가한다: 배포 체크리스트·환경 요구사항·설정 검토·복구 절차·백업 전략·모니터링 체크리스트·
실패 시나리오·운영 절차(production_review/ 8종). 재현성·복구성·관측성·유지보수성을 검증한다.

**프로덕션 배포 없음 — 준비성 평가만.** READINESS ≠ DEPLOYMENT · ASSESSMENT ≠ EXECUTION. 상위 계층은 READ ONLY.
새 원장·새 연구 지능·실행 권한 없음.
"""
from jarvis.production_review import assess, generator  # noqa: F401
from jarvis.production_review.models import (  # noqa: F401
    DEPLOYMENT_CHECKLIST,
    ENVIRONMENT_REQUIREMENTS,
    FAILURE_SCENARIOS,
    PRODUCTION_DOCS,
    READINESS_DIMENSIONS,
    doc_hash,
)
