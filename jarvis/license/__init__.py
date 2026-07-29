"""jarvis.license — 라이선스 감사 (P15 Security & Compliance). **읽기 전용·완전 additive.**

라이선스 인벤토리·배포 호환성 리포트·서드파티 고지문을 결정적으로 생성한다. SPDX 유사 식별자를 카테고리로 분류하고
프로젝트 라이선스와의 호환성을 규칙 기반으로 판정한다. 네트워크·실행·거래 능력 없음. 기존 모듈/원장 불변.
"""
from jarvis.license.audit import (  # noqa: F401
    LicenseEntry,
    build_inventory,
    categorize,
    compatibility_report,
    normalize_license,
    third_party_notice,
)
