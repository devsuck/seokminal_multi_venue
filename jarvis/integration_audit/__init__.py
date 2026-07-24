"""jarvis.integration_audit — Existing Architecture Integration (P41). **읽기전용 정적 분석.**

기존 Jarvis 시스템(P1~P40+)을 스캔·분석해 모듈 인벤토리·의존성 그래프·중복/미사용 분석·통합 제안·로드맵을 만든다.
docs/integration_audit/ 에 결정적 마크다운을 렌더한다.

**기존 원장·레코드·코드는 절대 변경하지 않는다(READ ONLY). 추가만, 마이그레이션·덮어쓰기 없음. 새 지능 계층 없음.**
거래·집행·배포 기능 없음. 기능이 이미 있으면 INTEGRATE(중복 금지).
"""
from jarvis.integration_audit.engine import IntegrationAuditEngine  # noqa: F401
from jarvis.integration_audit.models import (  # noqa: F401
    CATEGORIES,
    AuditReport,
    DependencyStats,
    DuplicateCluster,
    IntegrationProposal,
    ModuleInfo,
    categorize,
    family_of,
)
