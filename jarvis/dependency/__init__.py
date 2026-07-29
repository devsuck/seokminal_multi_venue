"""jarvis.dependency — 의존성 감사 (P15 Security & Compliance). **읽기 전용·완전 additive.**

pyproject 의존성 스캔·중복/미사용/구버전 탐지·의존성 그래프·리포트를 결정적으로 생성한다. 설치·업그레이드·네트워크·
실행을 하지 않으며, 기존 P9~P14 모듈/원장을 변경하지 않는다. 거래·집행·배포 능력 없음.
"""
from jarvis.dependency.audit import (  # noqa: F401
    DependencyFinding,
    build_report,
    dependency_graph,
    detect_duplicates,
    detect_outdated,
    detect_unused,
    scan_dependencies,
)
from jarvis.dependency.manifest import (  # noqa: F401
    Requirement,
    canonicalize,
    parse_pyproject,
    parse_requirement,
)
