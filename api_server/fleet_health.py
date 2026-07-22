"""수집기 함대 헬스 — 순수 판정 로직(tmux/IO 없음, 테스트가능).

플랫폼은 tmux 수집기 여러 개가 24/7 데이터를 쓰는 데 의존한다. 하나가 조용히
죽으면 그 엣지가 소리없이 썩는다(발열/고아 사건 계열). `_tmux_process_status`가 준
상태 dict(running/session_exists/last_write/age_sec)를 받아 신선도 verdict를 매기고
함대 전체를 요약한다. 임계값은 수집기별 폴링주기에 따라 다르므로 오버라이드 가능.

verdict:
  dead   — 프로세스 죽음(pane에 python 없음) 또는 데이터 파일 자체 없음
  stale  — 살아있다 표시되나 마지막 write가 임계 초과(막힘/무입력 의심)
  fresh  — 최근 write 정상
"""
from __future__ import annotations

# 수집기별 신선도 임계(초). 미지정 시 DEFAULT. 폴링 5s류는 낮게, 스캔/느린류는 높게.
DEFAULT_STALE_AFTER_S = 900          # 15분
STALE_AFTER_S: dict[str, int] = {
    "polymarket_tick": 300,
    "hl_orderflow_tick": 300,
    "cross_venue_skew_tick": 300,
    "polymarket_whale_tick": 600,
    "polymarket_sharp_wallet_tick": 600,
    "polymarket_arb": 1800,          # 스캔류는 간헐적
    "polymarket_updown_arb": 1800,
}

_RANK = {"dead": 0, "stale": 1, "fresh": 2}


def stale_after(key: str) -> int:
    return STALE_AFTER_S.get(key, DEFAULT_STALE_AFTER_S)


def classify(key: str, status: dict) -> dict:
    """상태 dict → verdict 부착. status: {running, session_exists, last_write, age_sec}."""
    running = bool(status.get("running"))
    age = status.get("age_sec")
    thr = stale_after(key)
    if not running or age is None:
        verdict = "dead"
        reason = ("프로세스 없음(pane에 python 미검출)" if not running
                  else "데이터 파일 없음(write 흔적 0)")
    elif age > thr:
        verdict = "stale"
        reason = f"마지막 write {age}s 전 > 임계 {thr}s"
    else:
        verdict = "fresh"
        reason = f"최근 write {age}s 전"
    return {
        "key": key,
        "verdict": verdict,
        "reason": reason,
        "stale_after_s": thr,
        "running": running,
        "session_exists": bool(status.get("session_exists")),
        "last_write": status.get("last_write"),
        "age_sec": age,
    }


def fleet_summary(rows: list[dict]) -> dict:
    """분류된 수집기 rows → 함대 요약. worst_verdict + 카운트 + 정렬(나쁜 것 먼저)."""
    counts = {"fresh": 0, "stale": 0, "dead": 0}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    worst = min((r["verdict"] for r in rows), key=lambda v: _RANK[v], default="fresh")
    ordered = sorted(rows, key=lambda r: (_RANK[r["verdict"]], r["key"]))
    return {
        "ok": counts["dead"] == 0 and counts["stale"] == 0,
        "worst_verdict": worst,
        "counts": counts,
        "n_total": len(rows),
        "collectors": ordered,
    }
