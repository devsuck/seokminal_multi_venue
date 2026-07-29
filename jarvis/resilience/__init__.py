"""jarvis.resilience — 복구·크래시 진단 (P14 Production Hardening). **원본 원장 불변, 완전 additive.**

해시체인 원장(P9~P13 형식)을 읽어 손상 지점을 진단하고 유효 프리픽스까지 부분 replay 로 복구한다. 크래시 복구·체크
포인트 검증·복구 가능성 검증·부분 replay·스냅샷 복구·손상 진단을 제공한다. **원본을 절대 수정/삭제하지 않으며** 복구본은
별도 파일에 기록한다. recovery_control(P9.4)과는 독립적인 additive 유틸리티다. 실행 능력 없음.
"""
from jarvis.resilience.recover import (  # noqa: F401
    ScanResult,
    content_hash,
    diagnose_corruption,
    partial_replay,
    recover_to_copy,
    scan_ledger,
    snapshot_recovery,
    validate_checkpoint,
    verify_recoverable,
)
