"""jarvis.integrity — 원장·아티팩트 무결성 검증 (P15 Security & Compliance). **읽기 전용·완전 additive.**

해시체인·변조·중복 ID·무효 타임스탬프·고아 아티팩트·깨진 계보·replay 일관성을 검증하고, 생성 아티팩트(리포트·스냅샷·
벤치마크·그래프·시뮬레이션·연구 산출물)의 구조·불변 표식·체크섬을 검증한다. 원본 원장/모듈 불변. 실행 능력 없음.
"""
from jarvis.integrity.artifact import (  # noqa: F401
    validate_artifact,
    validate_artifacts,
    verify_benchmark,
    verify_checksum,
    verify_graph_export,
    verify_snapshot,
)
from jarvis.integrity.ledger import (  # noqa: F401
    content_hash,
    detect_broken_lineage,
    detect_duplicate_ids,
    detect_invalid_timestamps,
    detect_orphan_artifacts,
    detect_tamper,
    replay_consistency,
    verify_hash_chain,
    verify_ledger,
)
