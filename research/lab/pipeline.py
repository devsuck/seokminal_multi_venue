"""AI LAB 파이프라인 — 자체생각→검토→집행→학습 상태머신.

백그라운드 스레드가 가설 하나를 4스테이지로 처리하며 이벤트를 낸다(UI가 폴링).
가드레일: EXECUTE는 verdict 분류 + registry 기록까지만. live 매매 자동 실행 절대 없음.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone

from research.lab.evaluator import evaluate
from research.lab.hypotheses import SEED_QUEUE, Hypothesis, known_edges

STAGES = ["think", "review", "execute", "learn"]
_LOG_MAX = 140
_VERDICT_MAX = 30


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


class LabEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._by_id: dict[str, Hypothesis] = {}
        self._queue: list[str] = []
        self._log: deque[dict] = deque(maxlen=_LOG_MAX)
        self._verdicts: deque[dict] = deque(maxlen=_VERDICT_MAX)
        self.status = "idle"          # idle | thinking | reviewing | executing | learning
        self.stage = None
        self.progress = 0
        self.current: dict | None = None
        self.metrics: dict = {}
        self.autopilot = False
        self.live_guard = "disarmed"  # 항상 disarmed — 자동 live 매매 없음
        self.stats = {"processed": 0, "edges": 0, "rejects": 0, "blocked": 0, "pending": 0}
        self._seed()

    # ── 큐 관리 ──────────────────────────────────────────────
    def _seed(self) -> None:
        # 합성 데모 제거 → 실 이벤트 family(Auto-Research 실엔진) + 데이터게이트 예시 1개.
        from research.lab.hypotheses import real_event_queue
        seeds = real_event_queue() + [h for h in SEED_QUEUE if h.data_mode == "blocked"]
        for h in seeds:
            self._by_id[h.id] = h
        self._queue = [h.id for h in seeds]

    def _log_line(self, stage: str, msg: str, level: str = "info") -> None:
        self._log.append({"ts": _now(), "stage": stage, "level": level, "msg": msg})

    def busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    # ── 공개 제어 ────────────────────────────────────────────
    def start(self, hid: str | None = None, autopilot: bool = False) -> dict:
        with self._lock:
            if self.busy():
                return {"started": False, "reason": "already_running"}
            if not self._queue:
                self._seed()  # 데모 반복용 재시드
            if hid and hid in self._by_id and hid not in self._queue:
                self._queue.insert(0, hid)
            self.autopilot = autopilot
            first = hid if (hid and hid in self._queue) else (self._queue[0] if self._queue else None)
            if not first:
                return {"started": False, "reason": "empty_queue"}
            self._worker = threading.Thread(target=self._run_loop, args=(first,), daemon=True)
            self._worker.start()
            return {"started": True, "hypothesis_id": first, "autopilot": autopilot}

    def set_autopilot(self, on: bool) -> dict:
        with self._lock:
            self.autopilot = on
        if on and not self.busy():
            return self.start(autopilot=True)
        return {"autopilot": on}

    # ── 워커 루프 ────────────────────────────────────────────
    def _run_loop(self, first: str) -> None:
        hid: str | None = first
        while hid:
            self._process(hid)
            if not self.autopilot:
                break
            time.sleep(0.6)
            with self._lock:
                hid = self._queue[0] if self._queue else None
            if hid is None:
                with self._lock:
                    self.autopilot = False
                self._log_line("learn", "큐 소진 — 오토파일럿 정지. 사람 검토 대기.", "muted")
        with self._lock:
            self.status = "idle"
            self.stage = None
            self.progress = 0

    def _set(self, status: str, stage: str, progress: int) -> None:
        with self._lock:
            self.status = status
            self.stage = stage
            self.progress = progress

    def _process(self, hid: str) -> None:
        h = self._by_id.get(hid)
        if h is None:
            return
        with self._lock:
            if hid in self._queue:
                self._queue.remove(hid)
            self.current = h.public()
            self.metrics = {}

        # ── THINK ───────────────────────────────────────────
        self._set("thinking", "think", 5)
        self._log_line("think", f"가설 채택: {h.name} [{h.market}·{h.family}]", "accent")
        time.sleep(0.5)
        self._log_line("think", f"논지: {h.thesis}")
        self._set("thinking", "think", 45)
        time.sleep(0.6)
        self._log_line("think", f"진입 {h.entry} · 보유 {h.hold} · 비용 {h.cost_bps:.0f}bps · {h.universe}", "muted")
        self._log_line("think", f"사망조건(사전정의): {h.kill}", "warn")
        self._set("thinking", "think", 100)
        time.sleep(0.5)

        # ── REVIEW (진짜 수학) ──────────────────────────────
        self._set("reviewing", "review", 10)
        self._log_line("review", "검토 시작 — 데이터 audit", "accent")
        res = evaluate(h)   # 실제 계산(빠름)
        time.sleep(0.5)
        aud = res["audit"]
        if not aud.get("ok"):
            self._log_line("review", f"AUDIT 실패: {aud.get('note')}", "neg")
            for m in aud.get("missing", []):
                self._log_line("review", f"  없음: {m}", "neg")
            self._set("reviewing", "review", 100)
            time.sleep(0.4)
            self._finish(h, res)
            return
        self._log_line("review", f"audit OK — {aud.get('note')}", "pos")
        self._set("reviewing", "review", 35)
        time.sleep(0.6)

        bt = res["backtest"] or {}
        net = bt.get("strategy_net")
        with self._lock:
            self.metrics = {"net": net, "n_trades": bt.get("n_trades")}
        self._log_line("review", f"백테스트: 전략 net {net} (거래 {bt.get('n_trades')}건, 비용 {bt.get('cost_bps', h.cost_bps)}bps)")
        self._set("reviewing", "review", 60)
        time.sleep(0.7)

        rnd = res["random"] or {}
        with self._lock:
            self.metrics.update(percentile=rnd.get("percentile"), p=rnd.get("p_value"),
                                random_median=rnd.get("random_median"))
        self._log_line("review",
                       f"매칭 random {rnd.get('n_runs', '?')}회: 전략 {rnd.get('percentile')}pct · p={rnd.get('p_value')} (rand_med={rnd.get('random_median')})",
                       "accent")
        self._set("reviewing", "review", 82)
        time.sleep(0.7)

        wf = res["walk_forward"] or {}
        with self._lock:
            self.metrics.update(wf_first=wf.get("first"), wf_second=wf.get("second"))
        self._log_line("review", f"walk-forward: 전반 {wf.get('first')} / 후반 {wf.get('second')} → 양쪽양수 {wf.get('both_positive')}")
        self._set("reviewing", "review", 100)
        time.sleep(0.5)

        self._finish(h, res)

    def _finish(self, h: Hypothesis, res: dict) -> None:
        # ── EXECUTE (분류 + registry, live 자동 매매 없음) ───
        self._set("executing", "execute", 30)
        status = res["status"]
        self._log_line("execute", f"판정: {res['verdict']}",
                       "pos" if status.startswith(("watchlist", "candidate", "paper")) else
                       "accent" if status == "pending_bh" else
                       "warn" if status.startswith("blocked") else "neg")
        time.sleep(0.5)
        self._log_line("execute", "가드레일: live 매매 자동 실행 없음. paper→live는 사람 게이트.", "warn")
        if status.startswith(("watchlist", "candidate", "paper")):
            self._log_line("execute", "→ paper_candidate 후보로 표시(사람 승인 대기).", "pos")
        self._set("executing", "execute", 100)
        time.sleep(0.4)

        # ── LEARN ───────────────────────────────────────────
        self._set("learning", "learn", 40)
        with self._lock:
            self.stats["processed"] += 1
            if status == "pending_bh":
                self.stats["pending"] += 1
            elif status.startswith(("watchlist", "candidate", "paper")):
                self.stats["edges"] += 1
            elif status.startswith("blocked"):
                self.stats["blocked"] += 1
            else:
                self.stats["rejects"] += 1
            self._verdicts.appendleft({
                "id": h.id, "name": h.name, "family": h.family, "market": h.market,
                "status": status, "verdict": res["verdict"], "data_mode": res["data_mode"],
                "ts": _now(),
            })
        self._log_line("learn", f"학습: {h.family} family — '{h.name}' → {status}", "accent")
        time.sleep(0.5)
        self._set("learning", "learn", 100)
        time.sleep(0.3)
        with self._lock:
            self.current = None
            self.metrics = {}

    # ── 배치 되먹임 ──────────────────────────────────────────
    def reconcile_from_batch(self, status: dict | None = None) -> dict:
        """Auto-Research 배치 완료 후 되먹임 — 이미 emit된 pending_bh 판정을 배치
        결과로 확정(candidate/watchlist/reject_*). event_study 재계산 없이 classify
        재사용(단일 진실원). status=None이면 배치 status.json에서 읽음."""
        from research.scanner.verdict import classify
        if status is None:
            try:
                from research.autoresearch.engine import load_status
                status = load_status()
            except Exception:  # noqa: BLE001
                return {"reconciled": 0}
        entries = {e.get("cid"): e for e in (status or {}).get("leaderboard", [])}
        reconciled = 0
        with self._lock:
            for v in self._verdicts:
                if v.get("status") != "pending_bh":
                    continue
                hid = v.get("id", "")
                if not hid.startswith("real_"):
                    continue
                entry = entries.get(f"ev_{hid[len('real_'):]}")
                if not entry:
                    continue
                new_status, new_verdict = classify(
                    net=entry.get("net"), percentile=entry.get("percentile"), p=entry.get("p"),
                    wf_first=entry.get("wf_first"), wf_second=entry.get("wf_second"),
                    redteam_verdict=entry.get("redteam", "N/A"), bh_survivor=entry.get("bh_survivor"))
                if new_status == "pending_bh":
                    continue  # 배치도 미확정(정상 배치엔 bh_survivor bool이라 발생 안 함)
                self.stats["pending"] = max(0, self.stats["pending"] - 1)
                if new_status.startswith(("watchlist", "candidate", "paper")):
                    self.stats["edges"] += 1
                else:
                    self.stats["rejects"] += 1
                v["status"] = new_status
                v["verdict"] = new_verdict
                v["reconciled"] = True
                reconciled += 1
            if reconciled:
                self._log.append({"ts": _now(), "stage": "learn", "level": "accent",
                                  "msg": f"배치 되먹임: pending {reconciled}건 확정."})
        return {"reconciled": reconciled}

    # ── 스냅샷 ───────────────────────────────────────────────
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status,
                "stage": self.stage,
                "progress": self.progress,
                "busy": self.busy(),
                "autopilot": self.autopilot,
                "live_guard": self.live_guard,
                "current": self.current,
                "metrics": self.metrics,
                "stats": dict(self.stats),
                "log": list(self._log),
                "verdicts": list(self._verdicts),
                "queue": [self._by_id[i].public() for i in self._queue if i in self._by_id],
            }

    def knowledge(self) -> list[dict]:
        try:
            return known_edges()
        except Exception:  # noqa: BLE001
            return []


ENGINE = LabEngine()
