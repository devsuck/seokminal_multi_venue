"""jarvis.documentation — 문서 검증·API 자동생성 (P16 Documentation & Architecture). **읽기 전용·완전 additive.**

P16 문서 트리(top-level `documentation/`)의 완전성·마크다운 유효성·내부 링크·다이어그램·API 커버리지를 검증하고, 공개
패키지 API 참조를 인트로스펙션으로 자동 생성한다. 코드를 실행하지 않으며 기존 P9~P15 모듈/원장/문서를 변경하지 않는다.
거래·집행·배포 능력 없음.
"""
from jarvis.documentation.apidoc import (  # noqa: F401
    cli_inventory,
    generate_reference,
    introspect_package,
    write_reference,
)
from jarvis.documentation.manifest import (  # noqa: F401
    CORE_DOCUMENTED_PACKAGES,
    MERMAID_DOCS,
    REQUIRED_DOCS,
    discover_packages,
    doc_root,
    repo_root,
)
from jarvis.documentation.validate import (  # noqa: F401
    check_api_coverage,
    check_completeness,
    validate_all,
    validate_diagram,
    validate_links,
    validate_markdown,
)
