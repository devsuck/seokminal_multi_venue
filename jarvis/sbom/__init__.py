"""jarvis.sbom — SBOM 생성 (P15 Security & Compliance). **읽기 전용·완전 additive.**

package·version·license·hash·source·dependency graph 를 포함한 결정적 SBOM 을 생성·검증한다. 직렬 번호는 내용 지문
(타임스탬프 무관)이라 재현 가능하다. 네트워크·설치·실행·거래 능력 없음. 기존 P9~P14 모듈/원장 불변.
"""
from jarvis.sbom.generate import (  # noqa: F401
    SBOM_FORMAT,
    SBOM_SPEC_VERSION,
    Component,
    component_hash,
    generate_sbom,
    make_component,
    sbom_from_dependencies,
    verify_sbom,
)
