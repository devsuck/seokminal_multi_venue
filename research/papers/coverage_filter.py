"""자산커버리지 필터 — v1은 equity_intraday만 코드생성 대상.

순수함수. 통과 못 한 스펙 기록(rejected.jsonl)은 호출측(run_paper_ingest.py)
책임 — 이 모듈은 판정만 한다."""
from __future__ import annotations

SUPPORTED_ASSET_CLASSES = {"equity_intraday"}


def is_covered(spec: dict) -> bool:
    return spec.get("asset_class") in SUPPORTED_ASSET_CLASSES


def rejection_reason(spec: dict) -> str | None:
    if is_covered(spec):
        return None
    return f"자산군 미지원: {spec.get('asset_class')!r} (v1 지원: {sorted(SUPPORTED_ASSET_CLASSES)})"
