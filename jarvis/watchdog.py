"""감시견 — 돈길 상태 변화 감지(결정적, LLM 아님). 카운트다운 경비병.

감시 대상(전부 이미 계산되는 값 — 새 계산 없음):
  - buyback edge status (no_oos_yet/accumulating/drifting/confirmed)
  - arm 판정 (GO/WAIT/KILL, arm_criteria_v1)
  - 이벤트 레벨 p_worse < 0.05 (소멸 조기경보)
  - OOS 월 카운트 증가 (카운트다운 진행)
  - TSMOM forward 최신 월 envelope 이탈

변화 있을 때만 이벤트 기록 = 스팸 없음. service가 워밍 직후 observe() 호출.
이벤트는 /lab/status·/status(폰)에 노출 — 화면 안 열어도 변화가 남는 구조.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from jarvis.config import state_path

_STATE = "watchdog.json"
_MAX_EVENTS = 50

# 심각도: 돈길 악화 = critical(폰에서 눈에 띄게), 진전 = good, 그 외 = info
_SEVERITY = {
    ("arm", "KILL"): "critical",
    ("arm", "GO"): "good",
    ("edge", "drifting"): "critical",
    ("edge", "confirmed"): "good",
    ("p_worse_alert", True): "critical",
    ("tsmom_out_of_env", True): "critical",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load() -> dict:
    p = state_path(_STATE)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:  # noqa: BLE001
            pass
    return {"snapshot": {}, "events": []}


def _save(st: dict) -> None:
    json.dump(st, open(state_path(_STATE), "w"), ensure_ascii=False)


def _describe(key: str, old, new) -> str:
    labels = {
        "edge": "엣지 생존", "arm": "ARM 판정", "oos_months": "OOS 월",
        "p_worse_alert": "이벤트레벨 소멸 조기경보", "tsmom_out_of_env": "TSMOM envelope",
    }
    name = labels.get(key, key)
    if key == "p_worse_alert":
        return f"{name} {'발령 — arm 금지, 콘솔 확인' if new else '해제'}"
    if key == "tsmom_out_of_env":
        return f"{name} {'이탈 — 최신 월 envelope 밖' if new else '복귀'}"
    if key == "oos_months":
        return f"{name} {old} → {new} (카운트다운 진행)"
    return f"{name} {old} → {new}"


def observe(snapshot: dict) -> list[dict]:
    """현재 스냅샷을 이전과 비교, 변한 키만 이벤트로 기록. 반환 = 새 이벤트들.

    snapshot 키: edge(str) · arm(str) · oos_months(int) · p_worse_alert(bool) ·
    tsmom_out_of_env(bool). None 값은 '아직 모름'으로 비교 제외(워밍 전 오탐 방지).
    """
    st = _load()
    prev = st["snapshot"]
    events = []
    for key, new in snapshot.items():
        if new is None:
            continue
        old = prev.get(key)
        if old == new:
            continue
        sev = _SEVERITY.get((key, new), "info")
        # 첫 관측(old=None)은 baseline 기록만, 이벤트 안 만듦 — 단 critical은 첫 관측도 알림
        if old is None and sev != "critical":
            prev[key] = new
            continue
        events.append({"ts": _now(), "key": key, "old": old, "new": new,
                       "severity": sev, "msg": _describe(key, old, new)})
        prev[key] = new
    if events:
        st["events"] = (st["events"] + events)[-_MAX_EVENTS:]
    _save(st)
    return events


def recent_events(n: int = 10) -> list[dict]:
    return _load()["events"][-n:]


def has_critical(n: int = 10) -> bool:
    return any(e["severity"] == "critical" for e in recent_events(n))
