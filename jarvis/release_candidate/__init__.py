"""jarvis.release_candidate — Jarvis Research Platform v1.0 Release Candidate (P40). **연구 보조만.**

**ARCHIVED (Phase1 STEP4, 2026-08-01):** 0 external callers, but is the root of an internal dead-end audit-tooling chain (imports security_audit + production_review which import system_integration/architecture_docs). Migration: archive together with that cluster; re-evaluate for full removal in a later phase.

v1.0 릴리스 후보를 준비한다: VERSION·릴리스 노트·아키텍처 요약·기능 인벤토리·테스트 요약·보안 요약·알려진 한계(release/).
릴리스 게이트로 무결성·보안·준비성·재현·의존성을 집계 검증한다.

**연구 시스템 완료. 라이브 실행 없음. 자율 거래 없음. 브로커 연결 없음. 배포 권한 없음. 연구 보조만.** RELEASE CANDIDATE
· NO LIVE EXECUTION · RESEARCH ASSISTANCE ONLY. 상위 계층은 READ ONLY. 새 원장·새 연구 지능·실행 권한 없음.
"""
from jarvis.release_candidate import gate, generator  # noqa: F401
from jarvis.release_candidate.models import (  # noqa: F401
    KNOWN_LIMITATIONS,
    PLATFORM_NAME,
    RELEASE_ARTIFACTS,
    RELEASE_GATES,
    STATUS_STATEMENTS,
    VERSION,
    artifact_hash,
    is_release_artifact,
)
