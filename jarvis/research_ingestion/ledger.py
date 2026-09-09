"""Research Ingestion 원장 (P53) — 1개 append-only SHA256 해시체인(수집 감사). **삭제/수정 없음.**

물리 파일 ring_ 접두사(Research INGestion). 실험/실패 저장은 기존 원장(expt_/rmi_)이 담당 — 이 원장은 **수집 이벤트
감사(중복 탐지·해시 검증)만** 기록한다.
"""
from __future__ import annotations


from jarvis.config import state_path
from jarvis.ledger_io import append as _append, read_jsonl, head as _head

INGESTIONS = ("ring_ingestions.jsonl", "ingestion_id")

ALL_LEDGERS = (INGESTIONS,)


def append_ingestion(rec) -> None:
    _append(INGESTIONS[0], rec, resolver=state_path)


def read_ingestions() -> list[dict]:
    return read_jsonl(INGESTIONS[0], resolver=state_path)


def ingestions_head():
    return _head(INGESTIONS[0], resolver=state_path)


def ingestion_exists(iid) -> bool:
    return any(r.get("ingestion_id") == iid for r in read_ingestions())


def ingestion_by_id(iid):
    return next((r for r in read_ingestions() if r.get("ingestion_id") == iid), None)
