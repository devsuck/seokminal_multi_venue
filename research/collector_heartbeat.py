"""수집기 생존 하트비트.

함대 헬스는 데이터 파일 mtime으로 신선도를 잰다. 그런데 이벤트가 있을 때만 쓰는
수집기(예: options_uoa — 미장 마감 후엔 이상옵션거래가 아예 안 잡힘)는 정상 폴링
중에도 파일 mtime이 안 움직여 stale/stuck로 오탐된다.

폴링이 성공할 때마다 `<data_dir>/.heartbeat`를 touch해서 "살아서 돌고 있음"과
"데이터가 나왔음"을 분리한다. 확장자를 .jsonl로 하지 않는 이유는 분석 스크립트들이
data_dir의 *.jsonl을 이벤트로 읽어가기 때문 — 하트비트가 섞이면 안 된다.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

HEARTBEAT_FILENAME = ".heartbeat"


def touch_heartbeat(data_dir: str | Path) -> Path:
    """폴링 1회 성공 표시. 내용은 사람이 읽을 UTC 타임스탬프(판정은 mtime으로 함)."""
    p = Path(data_dir)
    p.mkdir(parents=True, exist_ok=True)
    hb = p / HEARTBEAT_FILENAME
    hb.write_text(dt.datetime.now(dt.timezone.utc).isoformat())
    return hb
