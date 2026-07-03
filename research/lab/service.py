"""D — 서버사이드 상시 리서치 서비스. 크론이 Claude 부르는 방식 대체.

백그라운드 스레드가 주기적으로:
  - research_queue pending 있으면 run_pending(BH-FDR 검증) — 아이디어는 대화/수동 제출로 채워짐.
  - pending 없으면 그냥 대기(스프레이 없음, 죽은연못 자동생성 안 함).
안전: live 절대 없음(Jarvis 강제). $0(맥·무료 데이터). 아이디어 생성 = 우리 대화($0).
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone

from jarvis.config import state_path

_CFG = "research_service.json"
_DEFAULT = {"enabled": True, "interval_sec": 180}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ResearchService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = False
        self.last_run: str | None = None
        self.last_result: dict | None = None
        self.processed_total = 0
        self.ticks = 0
        self._last_refresh_ts = 0.0
        self.last_refresh: str | None = None
        self.refresh_added_total = 0
        self._last_autoresearch_ts = 0.0
        self.last_autoresearch: str | None = None
        self.autoresearch_candidates = 0
        self.autoresearch_reconciled = 0
        self._last_edge_ts = 0.0
        self.last_edge_warm: str | None = None
        self.edge_status_cache: str | None = None
        self.arm_decision: str | None = None

    def _load(self) -> dict:
        p = state_path(_CFG)
        if os.path.exists(p):
            try:
                return {**_DEFAULT, **json.load(open(p))}
            except Exception:  # noqa: BLE001
                pass
        return dict(_DEFAULT)

    def _save(self, cfg: dict) -> None:
        os.makedirs(os.path.dirname(state_path(_CFG)), exist_ok=True)
        json.dump(cfg, open(state_path(_CFG), "w"))

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running():
            return
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop:
            cfg = self._load()
            interval = int(cfg.get("interval_sec", 180))
            if cfg.get("enabled", True):
                try:
                    self._tick()
                except Exception as exc:  # noqa: BLE001
                    self.last_result = {"error": str(exc)[:80]}
            # interval 동안 stop 신호 감지하며 대기
            for _ in range(max(1, interval // 2)):
                if self._stop:
                    return
                time.sleep(2)

    def _refresh_buyback(self) -> None:
        """24시간 스로틀 buyback 증분갱신 → v2 forward(OOS) 자동 축적."""
        if time.time() - self._last_refresh_ts < 86400:
            return
        self._last_refresh_ts = time.time()
        try:
            from research.data.kr_dart_events import refresh_events
            n = refresh_events("buyback", days=120)
            self.refresh_added_total += n
            self.last_refresh = _now()
        except Exception:  # noqa: BLE001
            pass
        # 검증된 buyback 엣지 페이퍼 봇 sync(포지션 갱신). 실주문 없음.
        try:
            from jarvis.paper.buyback_bot import sync
            sync()
        except Exception:  # noqa: BLE001
            pass
        # 손실 진단 + 청산룰 시뮬 캐시 갱신(series warm 상태서). 엔드포인트 즉응.
        try:
            from jarvis.paper.buyback_analysis import refresh
            refresh()
        except Exception:  # noqa: BLE001
            pass

    def _autoresearch_batch(self) -> None:
        """24시간 스로틀 Auto-Research 배치 — 후보 재검증 + 배치 BH-FDR 리더보드 갱신.
        데이터가 갱신되면(refill/refresh) 새 family 편입 → 밤새 자동으로 잘 건짐."""
        if time.time() - self._last_autoresearch_ts < 86400:
            return
        self._last_autoresearch_ts = time.time()
        try:
            from research.autoresearch.engine import run_batch
            s = run_batch()
            self.last_autoresearch = _now()
            self.autoresearch_candidates = s.get("n_candidates", 0)
            # 되먹임 순환: 배치 확정 결과를 lab의 pending_bh 판정에 반영.
            try:
                from research.lab.pipeline import ENGINE
                self.autoresearch_reconciled = ENGINE.reconcile_from_batch(s).get("reconciled", 0)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def _warm_edge(self) -> None:
        """6시간 스로틀 buyback 엣지 생존 캐시 워밍 — 프론트 /execution/edge가 즉시
        응답하도록(series 로드 무거움 → 배경서 미리 계산). OOS 월은 느리게 변해 6h 충분."""
        if time.time() - self._last_edge_ts < 21600:
            return
        self._last_edge_ts = time.time()
        try:
            from research.paper.buyback_edge import edge_status
            s = edge_status(force=True)
            self.last_edge_warm = _now()
            self.edge_status_cache = s.get("status")
            # 사전등록 arm/kill 판정도 status에 노출 — KILL이 뜨면 이게 알림 채널(/status 폰 접근).
            import datetime as _dt
            from research.paper import buyback_config as CFG
            from jarvis.execution.arm_criteria import evaluate as arm_eval
            months = (_dt.date.today() - _dt.date.fromisoformat(CFG.FROZEN_AT)).days / 30.0
            self.arm_decision = arm_eval(s, round(months, 1)).get("decision")
        except Exception:  # noqa: BLE001
            pass

    def _tick(self) -> None:
        self.ticks += 1
        self._refresh_buyback()
        self._autoresearch_batch()
        self._warm_edge()
        from jarvis.research_queue import pending, run_pending
        if not pending():
            self.last_run = _now()
            self.last_result = {"pending": 0, "action": "idle_no_queue"}
            return
        res = run_pending(alpha=0.1)
        self.processed_total += res.get("ran", 0)
        self.last_run = _now()
        self.last_result = {"ran": res.get("ran", 0),
                            "decisions": [d["final"] for d in (res.get("report") or {}).get("decisions", [])]}

    def set_enabled(self, on: bool) -> dict:
        cfg = self._load()
        cfg["enabled"] = bool(on)
        self._save(cfg)
        if on:
            self.start()
        return self.status()

    def status(self) -> dict:
        cfg = self._load()
        return {
            "running": self.running(), "enabled": cfg.get("enabled", True),
            "interval_sec": cfg.get("interval_sec", 180),
            "last_run": self.last_run, "last_result": self.last_result,
            "processed_total": self.processed_total, "ticks": self.ticks,
            "last_buyback_refresh": self.last_refresh, "buyback_added_total": self.refresh_added_total,
            "last_autoresearch": self.last_autoresearch, "autoresearch_candidates": self.autoresearch_candidates,
            "autoresearch_reconciled": self.autoresearch_reconciled,
            "last_edge_warm": self.last_edge_warm, "edge_status": self.edge_status_cache,
            "arm_decision": self.arm_decision,
            "note": "pending 큐 + buyback 24h 갱신 + Auto-Research 24h 배치 + lab 되먹임 + 엣지 6h 워밍. live 불가. $0.",
        }


SERVICE = ResearchService()
