"""Research Ingestion 원장 (P53) — 1개 append-only SHA256 해시체인(수집 감사). **삭제/수정 없음.**

물리 파일 ring_ 접두사(Research INGestion). 실험/실패 저장은 기존 원장(expt_/rmi_)이 담당 — 이 원장은 **수집 이벤트
감사(중복 탐지·해시 검증)만** 기록한다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path

INGESTIONS = ("ring_ingestions.jsonl", "ingestion_id")

ALL_LEDGERS = (INGESTIONS,)


def _append(filename, record) -> None:
    p = state_path(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename) -> list[dict]:
    p = state_path(filename)
    if not os.path.exists(p):
        return []
    out: list[dict] = []
    with open(p) as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except (ValueError, json.JSONDecodeError):
                continue
    return out


def _head(filename):
    recs = read_jsonl(filename)
    return recs[-1] if recs else None


def append_ingestion(rec) -> None:
    _append(INGESTIONS[0], rec)


def read_ingestions() -> list[dict]:
    return read_jsonl(INGESTIONS[0])


def ingestions_head():
    return _head(INGESTIONS[0])


def ingestion_exists(iid) -> bool:
    return any(r.get("ingestion_id") == iid for r in read_ingestions())


def ingestion_by_id(iid):
    return next((r for r in read_ingestions() if r.get("ingestion_id") == iid), None)
