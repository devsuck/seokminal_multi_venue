"""스로틀 타임스탬프가 프로세스 재기동을 생존하는지 — 2026-09-03 api_watchdog.log에서
재기동↔health실패가 5~10분 간격으로 반복되는 패턴 실측. 원인: ResearchService.__init__이
_last_*_ts를 하드코딩 0.0으로 초기화해 매 재기동마다 24h/6h 스로틀 배치(autoresearch,
krx pull 등 무거운 작업)가 "마지막 실행 후 86400초 지남" 판정으로 첫 tick에 몰아쳐 실행되며
메모리를 다시 터뜨려 재재기동을 유발함. _touch()로 디스크에 영구화해 재기동해도 스로틀이
유지되는지 검증."""
from __future__ import annotations

import os
import time

import pytest

from research.lab.service import ResearchService


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    import importlib
    monkeypatch.setattr(importlib.import_module("research.lab.service"), "state_path", sp)
    return tmp_path


def test_touch_survives_a_fresh_instance(monkeypatch):
    monkeypatch.setattr(
        "jarvis.execution.live_router.route_all",
        lambda as_of="": {"as_of": as_of, "routed": [], "blocked": [], "skipped": []},
    )
    svc1 = ResearchService()
    svc1._execution_check()  # 스로틀 없음(신규) → 실행 + 디스크 반영
    assert svc1._last_execution_ts > 0

    # "재기동" 시뮬 — 완전히 새 인스턴스(프로세스 재시작과 동일 상황)
    svc2 = ResearchService()
    assert svc2._last_execution_ts == svc1._last_execution_ts  # 디스크에서 복원됨

    calls = []
    monkeypatch.setattr(
        "jarvis.execution.live_router.route_all",
        lambda as_of="": calls.append(1) or {"as_of": as_of, "routed": [], "blocked": [], "skipped": []},
    )
    svc2._execution_check()
    assert calls == []  # 재기동 직후에도 6h 스로틀 유지 — 다시 실행되지 않음


def test_expired_throttle_still_runs_after_restart(monkeypatch, tmp_path):
    import json
    # 6h(21600s)보다 오래 전 실행 기록을 디스크에 직접 심어둠
    old_ts = time.time() - 999999
    json.dump({"enabled": True, "interval_sec": 180, "last_execution_ts": old_ts},
              open(os.path.join(tmp_path, "research_service.json"), "w"))

    svc = ResearchService()
    assert svc._last_execution_ts == old_ts

    calls = []
    monkeypatch.setattr(
        "jarvis.execution.live_router.route_all",
        lambda as_of="": calls.append(1) or {"as_of": as_of, "routed": [], "blocked": [], "skipped": []},
    )
    svc._execution_check()
    assert calls == [1]  # 스로틀 만료됐으면 재기동 후에도 정상 실행
