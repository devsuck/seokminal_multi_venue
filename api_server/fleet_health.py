"""수집기 함대 헬스 — 순수 판정 로직(tmux/IO 없음, 테스트가능).

플랫폼은 tmux 수집기 여러 개가 24/7 데이터를 쓰는 데 의존한다. 하나가 조용히
죽으면 그 엣지가 소리없이 썩는다(발열/고아 사건 계열). `_tmux_process_status`가 준
상태 dict(running/session_exists/last_write/age_sec)를 받아 신선도 verdict를 매기고
함대 전체를 요약한다. 임계값은 수집기별 폴링주기에 따라 다르므로 오버라이드 가능.

verdict:
  dead   — 프로세스 죽음(pane에 python 없음) 또는 데이터 파일 자체 없음
  stuck  — 살아있다 표시되나 마지막 write가 임계의 STUCK_MULTIPLIER배 초과
           (polymarket_event_divergence가 9시간 stale로 방치됐던 사건 재발 방지 —
           stale은 워치독이 기본적으로 손대지 않는 상태라 방치되면 티가 안 남)
  stale  — 살아있다 표시되나 마지막 write가 임계 초과(막힘/무입력 의심)
  fresh  — 최근 write 정상

restart_count_24h/flapping: /lab/collectors/{key}/restart 호출마다 남기는 로그
(api_server/lab_api.py의 restart_log)에서 최근 24h 카운트를 받아 붙인다. dead→재기동을
계속 반복 중인 수집기(근본원인 안 고쳐진 채 워치독이 매번 가려주는 중)를 눈에 띄게 하기 위함
— verdict 자체(지금 이 순간 살아있나)는 안 바꾸고 별도 플래그로만 노출한다."""
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
    "polymarket_event_divergence": 1800,
}

STUCK_MULTIPLIER = 4                 # 임계의 4배 넘게 stale이면 stuck(장시간 방치 의심)
FLAPPING_THRESHOLD = 3               # 24h 내 재기동 3회 이상이면 flapping

_RANK = {"dead": 0, "stuck": 1, "stale": 2, "fresh": 3}


def stale_after(key: str) -> int:
    return STALE_AFTER_S.get(key, DEFAULT_STALE_AFTER_S)


def classify(key: str, status: dict, restart_count_24h: int = 0) -> dict:
    """상태 dict → verdict 부착. status: {running, session_exists, last_write, age_sec}.
    restart_count_24h: 최근 24h /collectors/{key}/restart 호출 횟수(lab_api가 채워줌)."""
    running = bool(status.get("running"))
    age = status.get("age_sec")
    thr = stale_after(key)
    if not running or age is None:
        verdict = "dead"
        reason = ("프로세스 없음(pane에 python 미검출)" if not running
                  else "데이터 파일 없음(write 흔적 0)")
    elif age > thr * STUCK_MULTIPLIER:
        verdict = "stuck"
        reason = f"마지막 write {age}s 전 >> 임계 {thr}s의 {STUCK_MULTIPLIER}배 — 장시간 방치 의심"
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
        "restart_count_24h": restart_count_24h,
        "flapping": restart_count_24h >= FLAPPING_THRESHOLD,
    }


def fleet_summary(rows: list[dict]) -> dict:
    """분류된 수집기 rows → 함대 요약. worst_verdict + 카운트 + 정렬(나쁜 것 먼저)."""
    counts = {"fresh": 0, "stale": 0, "dead": 0, "stuck": 0}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    worst = min((r["verdict"] for r in rows), key=lambda v: _RANK[v], default="fresh")
    ordered = sorted(rows, key=lambda r: (_RANK[r["verdict"]], r["key"]))
    return {
        "ok": counts["dead"] == 0 and counts["stale"] == 0 and counts["stuck"] == 0
              and not any(r["flapping"] for r in rows),
        "worst_verdict": worst,
        "counts": counts,
        "n_total": len(rows),
        "collectors": ordered,
    }


def count_restarts_by_key(events: list[dict], now_ts: float, window_s: float = 86400.0) -> dict[str, int]:
    """restart_log 이벤트([{"key":.., "ts": float}, ...]) → window_s 내 key별 카운트."""
    counts: dict[str, int] = {}
    for e in events:
        if now_ts - e["ts"] <= window_s:
            counts[e["key"]] = counts.get(e["key"], 0) + 1
    return counts


DISK_WARN_FREE_GB = 20.0
DISK_CRITICAL_FREE_GB = 8.0


def classify_disk(free_gb: float, total_gb: float,
                   warn_gb: float = DISK_WARN_FREE_GB, critical_gb: float = DISK_CRITICAL_FREE_GB) -> dict:
    """디스크 여유공간 → verdict(ok/warn/critical). 수집기들이 계속 write하는 볼륨이
    꽉 차면 전 함대가 한꺼번에 dead로 떨어지므로 사전 경보."""
    if free_gb < critical_gb:
        verdict, reason = "critical", f"여유 {free_gb:.1f}GB < 임계 {critical_gb}GB"
    elif free_gb < warn_gb:
        verdict, reason = "warn", f"여유 {free_gb:.1f}GB < 임계 {warn_gb}GB"
    else:
        verdict, reason = "ok", f"여유 {free_gb:.1f}GB"
    return {"verdict": verdict, "reason": reason, "free_gb": round(free_gb, 1), "total_gb": round(total_gb, 1)}
