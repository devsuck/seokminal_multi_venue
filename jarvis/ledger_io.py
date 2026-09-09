"""JSONL append-only 원장 저수준 I/O — jarvis/*/ledger.py 전체가 재구현하던 파일 쓰기/읽기
로직 하나로 통합. 각 도메인 ledger.py는 이 4개 함수 위에 자기 이름의 얇은 공개 API만 얹는다.
"""
from __future__ import annotations

import json
import os

from jarvis.config import state_path


def append(filename: str, record: dict, resolver=state_path) -> None:
    p = resolver(filename)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_jsonl(filename: str, resolver=state_path) -> list[dict]:
    p = resolver(filename)
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


def head(filename: str, resolver=state_path) -> dict | None:
    recs = read_jsonl(filename, resolver=resolver)
    return recs[-1] if recs else None


def exists(filename: str, id_field: str, rid: str, resolver=state_path) -> bool:
    return any(r.get(id_field) == rid for r in read_jsonl(filename, resolver=resolver))
