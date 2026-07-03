"""AI LAB — 자율 리서치 루프 서빙.

상태 폴링(/lab/state) + 실행 제어(/lab/run, /lab/autopilot). live 매매 자동 실행 없음.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from research.lab.pipeline import ENGINE

router = APIRouter(prefix="/lab", tags=["lab"])


@router.get("/state")
def state() -> dict:
    snap = ENGINE.snapshot()
    snap["knowledge"] = ENGINE.knowledge()
    return snap


class RunReq(BaseModel):
    hypothesis_id: str | None = None
    autopilot: bool = False


@router.post("/run")
def run(req: RunReq) -> dict:
    return ENGINE.start(hid=req.hypothesis_id, autopilot=req.autopilot)


class AutopilotReq(BaseModel):
    on: bool


@router.post("/autopilot")
def autopilot(req: AutopilotReq) -> dict:
    return ENGINE.set_autopilot(req.on)


@router.get("/jarvis")
def jarvis_status() -> dict:
    """Jarvis Quant OS 거버넌스 상태 — 자율레벨·live 차단·전략 생애주기 요약."""
    import jarvis
    from jarvis.registry import StrategyRegistry
    reg = StrategyRegistry()
    rows = reg.all_current()
    counts: dict = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {**jarvis.status(), "registry_counts": counts, "registry_total": len(rows)}


_tasks_cache: dict = {"ts": 0.0, "data": None}


def _task_forward(runner: str | None) -> dict | None:
    """페이퍼 전략 forward 러너 → 정규화(진입/청산규칙·통계·월별수익). 실패는 None."""
    if not runner:
        return None
    try:
        if "tsmom_forward" in runner:
            from research.paper.tsmom_forward import generate
            r = generate(write=False)
            env = r.get("backtest_envelope", {})
            fm = r.get("forward_months", {}) or {}
            monthly = [{"period": k, "return": v, "n": None} for k, v in sorted(fm.items())]
            return {"entry": "월 리밸런스", "exit": "월 리밸런스(신호전환)", "cost_bps": None,
                    "stats": {"sharpe": env.get("sharpe"), "max_drawdown": env.get("max_drawdown"),
                              "n_months": env.get("n_months")}, "monthly": monthly}
        if "buyback_forward" in runner:
            from research.paper.buyback_forward import generate
            r = generate(write=False)
            ov = r.get("overall", {})
            co = r.get("cohorts", {}) or {}
            monthly = [{"period": m, "return": c.get("median"), "n": c.get("n")} for m, c in sorted(co.items())]
            return {"entry": "공시 익일 시가", "exit": "20거래일 종가",
                    "cost_bps": (r.get("config_frozen") or {}).get("cost_base"),
                    "stats": {"n_trades": ov.get("n"), "mean_return": ov.get("mean"),
                              "median_return": ov.get("median"), "win_rate": ov.get("win_rate")},
                    "monthly": monthly}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"forward 러너 데이터 필요: {exc}"}
    return None


@router.get("/tasks")
def lab_tasks() -> dict:
    """페이퍼 전략(task) 목록 — 가벼움(상태·러너·규칙). 상세 P&L은 포트폴리오/봇 카드."""
    import time
    if _tasks_cache["data"] is not None and time.time() - _tasks_cache["ts"] < 60:
        return _tasks_cache["data"]
    from jarvis.paper.deploy import deployment_of
    from jarvis.registry import StrategyRegistry
    reg = StrategyRegistry()
    live_paper = ("paper_active", "paper_candidate", "paper_candidate_forward_test_required")
    tasks = []
    for r in reg.all_current():
        if r["status"] not in live_paper:
            continue
        dep = deployment_of(r["strategy_id"])
        runner = dep["runner"] if dep else None
        # 무거운 generate() 안 부름 — 배포 규칙만(가벼움). 상세는 포트폴리오/봇 카드.
        fw = None
        if dep:
            rules = dep.get("rules") or {}
            # 청산 규칙은 전략마다 다른 키 사용 — envelope(tsmom)·hold_days(per-event)·ledger(generic).
            if rules.get("envelope"):
                exit_rule = rules["envelope"]
            elif rules.get("hold_days"):
                exit_rule = f"{rules['hold_days']}거래일 종가"
            elif rules.get("ledger"):
                exit_rule = f"{rules['ledger']} 원장"
            else:
                exit_rule = "-"
            fw = {"entry": rules.get("cadence") or "-", "exit": exit_rule,
                  "cost_bps": None, "stats": {}, "monthly": []}
        tasks.append({"strategy_id": r["strategy_id"], "status": r["status"],
                      "runner": runner, "deployed": dep is not None, "forward": fw})
    data = {"tasks": tasks, "count": len(tasks)}
    _tasks_cache.update(ts=time.time(), data=data)
    return data


_book_cache: dict = {"ts": 0.0, "data": None}


@router.get("/portfolio")
def lab_portfolio() -> dict:
    """멀티엣지 포트폴리오 북 — TSMOM+buyback 조합, 상관·조합 통계·월별 곡선."""
    import time
    if _book_cache["data"] is not None and time.time() - _book_cache["ts"] < 300:
        return _book_cache["data"]
    try:
        from research.run_portfolio_book import build_book
        data = build_book()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"포트폴리오 계산 실패(데이터 필요): {exc}") from exc
    _book_cache.update(ts=time.time(), data=data)
    return data


@router.get("/status")
def lab_status() -> dict:
    """모바일 상태 보드 — 서버·DART봇·AI루프·congress 한눈에."""
    import datetime as _dt
    out: dict = {"server": "ok", "now": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    # DART 자동봇
    try:
        from api_server.dart_autobot import _load, _recent_log
        cfg = _load()
        log = _recent_log(5)
        out["dart_bot"] = {"running": True, "enabled": cfg.get("enabled", False),
                           "last_run": cfg.get("last_run"), "interval_sec": cfg.get("interval_sec"),
                           "acted": len(cfg.get("acted", [])), "recent": log}
    except Exception as exc:  # noqa: BLE001
        out["dart_bot"] = {"running": False, "error": str(exc)[:60]}

    # AI LAB / Jarvis
    try:
        import jarvis
        from research.lab.pipeline import ENGINE
        snap = ENGINE.snapshot()
        js = jarvis.status()
        out["ai_lab"] = {"engine_status": snap["status"], "busy": snap["busy"],
                         "autopilot": snap["autopilot"], "processed": snap["stats"]["processed"],
                         "continuous_loop": "stopped_manual",  # 크론 정지됨
                         "autonomy_level": js["autonomy_level"], "live_execution": js["live_execution"]}
    except Exception as exc:  # noqa: BLE001
        out["ai_lab"] = {"error": str(exc)[:60]}

    # 서버사이드 리서치 서비스(D)
    try:
        from research.lab.service import SERVICE
        out["research_service"] = SERVICE.status()
    except Exception as exc:  # noqa: BLE001
        out["research_service"] = {"error": str(exc)[:60]}

    # congress = 온디맨드 피드(상시봇 아님)
    out["congress"] = {"type": "on_demand_feed", "note": "페이지 열 때 가져옴(상시봇 아님)"}
    return out


class ServiceToggle(BaseModel):
    on: bool


@router.get("/service")
def service_status() -> dict:
    from research.lab.service import SERVICE
    return SERVICE.status()


@router.post("/service/toggle")
def service_toggle(req: ServiceToggle) -> dict:
    from research.lab.service import SERVICE
    return SERVICE.set_enabled(req.on)


_v2_cache: dict = {"ts": 0.0, "data": None}


@router.get("/v2shadow")
def lab_v2shadow() -> dict:
    """buyback v2(레짐 필터) shadow — in-sample vs forward(OOS) 비교."""
    import time
    if _v2_cache["data"] is not None and time.time() - _v2_cache["ts"] < 300:
        return _v2_cache["data"]
    try:
        from research.paper.buyback_v2_forward import generate
        data = generate(write=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"v2 계산 실패: {exc}") from exc
    _v2_cache.update(ts=time.time(), data=data)
    return data


@router.get("/scanner")
def scanner_results() -> dict:
    """이벤트 family 스캐너 라이브 — 전 family를 진행상태(완료/pull완/대기)로 표시."""
    from research.agents.experiment_registry import load_all
    from research.data.kr_dart_events import load_events
    from research.scanner.families import FAMILIES

    done: dict = {}
    for e in load_all():
        hid = e.get("hypothesis_id", "")
        if hid.startswith("scan_"):
            done[hid.replace("scan_", "")] = e

    fams, current = [], None
    for fid, fam in FAMILIES.items():
        if fid in done:
            e = done[fid]
            fams.append({"family": fid, "status": "완료", "n": e.get("n"), "net": e.get("net"),
                         "percentile": e.get("percentile"), "p": e.get("p"),
                         "wf_first": e.get("wf_first"), "wf_second": e.get("wf_second"),
                         "redteam": e.get("redteam"), "direction": fam["direction"], "thesis": fam["thesis"]})
        else:
            n_ev = len(load_events(fid))
            status = "백테스트 대기" if n_ev > 0 else "pull 대기/중"
            if current is None:
                current = fid
            fams.append({"family": fid, "status": status, "n": n_ev or None, "net": None,
                         "percentile": None, "p": None, "wf_first": None, "wf_second": None,
                         "redteam": None, "direction": fam["direction"], "thesis": fam["thesis"]})

    cleared = sum(1 for f in fams if f["redteam"] == "CLEARED")
    return {"families": fams, "count": len(fams), "done": len(done), "cleared": cleared,
            "current": current, "total": len(FAMILIES)}


@router.get("/redteam")
def redteam_audit() -> dict:
    """Red-team 통제 감사 — 통제층 verdict vs 사람 판단(오늘 검증)."""
    from jarvis.redteam.review import audit_registry
    from jarvis.redteam.controls import CONTROLS
    a = audit_registry()
    a["controls_catalog"] = CONTROLS
    return a


@router.get("/buyback-bot")
def buyback_bot() -> dict:
    """검증된 buyback 엣지 페이퍼 봇 — 포지션·페이퍼 P&L. 실주문 없음."""
    from jarvis.paper.buyback_bot import summary, sync
    s = summary()
    if s["total"] == 0:   # 첫 로드 = lazy sync(서비스 틱 전이라도 채움)
        try:
            s = sync()
        except Exception:  # noqa: BLE001
            pass
    return s


@router.get("/execution")
def execution_console() -> dict:
    """집행 콘솔 — 검증된 buyback 엣지의 라이브 준비 상태 한 화면.
    동결 config + 정직한 기대치 + 페이퍼 손익 + 실전제약 + arm 게이트(사람만).
    실주문 없음. 라이브 arm/집행은 사람 ADMIN + autonomy>=MIN_LIVE."""
    import datetime as _dt
    import jarvis
    from research.paper import buyback_config as CFG
    from jarvis.paper.buyback_bot import summary, sync
    from jarvis.execution.arm import arm_state, check_micro_live_eligible

    sid = CFG.VERSION            # "kr_buyback_drift_v1" — 표시/config 버전
    reg_id = "kr_dart_buyback_drift_v1"  # registry/deploy/arm FSM id(별개)
    paper = summary()
    if paper["total"] == 0:
        try:
            paper = sync()
        except Exception:  # noqa: BLE001
            pass

    # 페이퍼 관찰 기간(동결 시점부터)
    try:
        frozen = _dt.date.fromisoformat(CFG.FROZEN_AT)
        paper_months = round((_dt.date.today() - frozen).days / 30.0, 1)
    except Exception:  # noqa: BLE001
        paper_months = 0.0

    js = jarvis.status()
    armed = arm_state(reg_id)
    elig = check_micro_live_eligible(reg_id, paper_months)

    return {
        "strategy_id": sid, "registry_id": reg_id, "status": CFG.STATUS, "frozen_at": CFG.FROZEN_AT,
        "config": {"event": CFG.EVENT, "markets": CFG.MARKETS, "entry": CFG.ENTRY,
                   "hold_days": CFG.HOLD_DAYS, "cost_bps": CFG.COST_BASE_BPS},
        "edge": {  # 정직한 기대치 — 평균 아닌 중앙값(팻테일 경고)
            "net_mean": CFG.BASELINE["net_mean"], "net_median": CFG.BASELINE["net_median"],
            "trimmed10": CFG.BASELINE["trimmed10"], "win_rate": CFG.BASELINE["win_rate"],
            "p_median": CFG.BASELINE["p_median"], "wf_first": CFG.BASELINE["wf_first"],
            "wf_second": CFG.BASELINE["wf_second"], "trade_count": CFG.BASELINE["trade_count"],
            "honest_note": "평균 +1.73%는 팻테일(상위5% 114% 기여). 기대치=중앙값/trimmed(+0.2~0.8%). 수익 lumpy → 분산 필수.",
        },
        "live_readiness": CFG.LIVE_READINESS,
        "paper": {"total": paper.get("total"), "open": paper.get("open"), "closed": paper.get("closed"),
                  "paper_pnl_mean": paper.get("paper_pnl_mean"), "paper_win_rate": paper.get("paper_win_rate"),
                  "cum_paper_pnl": paper.get("cum_paper_pnl"), "recent_closed": paper.get("recent_closed", [])[:5]},
        "arm_gate": {
            "armed": bool(armed and armed.get("armed")),
            "autonomy_level": js.get("autonomy_level"), "min_live_level": 6,
            "live_execution": js.get("live_execution"),
            "eligible": elig["eligible"], "reasons": elig.get("reasons", []),
            "paper_months": paper_months, "min_paper_months": CFG.MIN_OBSERVATION_MONTHS,
            "human_action": "라이브 소액 = 사람 ADMIN이 arm() + autonomy>=6. 현재 BLOCKED(안전). AI 자가 arm 불가.",
        },
        "forbidden": CFG.FORBIDDEN,
    }


@router.get("/execution/edge")
def execution_edge() -> dict:
    """엣지 생존 모니터 — OOS vs 동결 envelope. series 로드 무거움 → buyback_edge
    캐시(service가 배경 워밍). 콘솔과 분리(프로그레시브). 첫 콜(캐시 콜드)만 느림."""
    from research.paper.buyback_edge import edge_status
    return edge_status(read_only=True)  # 계산 안 함 — service 워밍한 캐시만. 없으면 warming.


@router.get("/jarvis/detail")
def jarvis_detail(audit_n: int = 40) -> dict:
    """생애주기 전략 목록 + forward 배포 + 감사 로그 tail(파이프라인 시각화용)."""
    import jarvis
    from jarvis.audit import tail
    from jarvis.paper.deploy import all_deployments
    from jarvis.registry import StrategyRegistry
    rows = StrategyRegistry().all_current()
    return {
        "strategies": [{"strategy_id": r["strategy_id"], "status": r["status"],
                        "frozen": r.get("frozen", False), "flags": r.get("flags", [])} for r in rows],
        "deployments": all_deployments(),
        "audit": tail(audit_n),
    }


# ── Auto-Research (karpathy/autoresearch 정직 이식: 배치 BH-FDR 게이트) ──
import threading as _threading
_AR_LOCK = _threading.Lock()


@router.get("/autoresearch")
def autoresearch_status() -> dict:
    """마지막 배치 리더보드 + 대기 엔진 상태."""
    from research.autoresearch.engine import load_status
    return load_status()


@router.post("/autoresearch/run")
def autoresearch_run() -> dict:
    """1회 배치 실행(후보 생성 → 검증 → 배치 BH-FDR → 레드팀 → 리더보드).
    동시 실행 방지. 캐시된 실데이터 대상이라 수초 내 완료."""
    from research.autoresearch.engine import run_batch, load_status
    if not _AR_LOCK.acquire(blocking=False):
        return {**load_status(), "busy": True}
    try:
        return {**run_batch(), "busy": False}
    finally:
        _AR_LOCK.release()


@router.get("/buyback-analysis")
def buyback_analysis() -> dict:
    """손실 포지션 진단 + 청산룰 시뮬(v1 동결 → 섀도 평가). 결정적.
    캐시 즉시 반환. 없으면 백그라운드 계산(_series 빌드 ~80s) + pending."""
    from jarvis.paper.buyback_analysis import load_cached, refresh
    c = load_cached()
    if c is not None:
        return {**c, "pending": False}
    if not _AR_LOCK.acquire(blocking=False):   # 재사용 락: 중복 계산 방지
        return {"pending": True, "losers": [], "exit_sim": {}, "note": "계산 중… (가격 시리즈 빌드 ~80s)"}

    def _bg():
        try:
            refresh()
        finally:
            _AR_LOCK.release()

    _threading.Thread(target=_bg, daemon=True).start()
    return {"pending": True, "losers": [], "exit_sim": {}, "note": "계산 시작… 잠시 후 새로고침(가격 시리즈 빌드 ~80s)"}
