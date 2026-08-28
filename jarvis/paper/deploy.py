"""Lv3 — paper_candidate 자동 forward 배선.

paper_candidate 도달 전략을 forward-test에 자동 배포(paper_candidate→paper_active).
기존 forward 모듈(tsmom_forward/buyback_forward)에 배선, 없으면 내부 원장 generic.
자본 0. 사람 승인 불필요(여전히 페이퍼). config 동결 필수.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from jarvis.agents import PAPER_AGENT
from jarvis.audit import record
from jarvis.config import state_path
from jarvis.permissions import require
from jarvis.registry import Status, StrategyRegistry

_DEPLOY = "forward_deployments.jsonl"

# registry strategy_id → forward 러너(dotted path의 generate) + 규칙.
RUNNER_REGISTRY: dict[str, dict] = {
    "futures_tsmom_32mkt": {"runner": "research.paper.tsmom_forward:generate",
                            "rules": {"cadence": "monthly", "envelope": "backtest_envelope",
                                      "compare": ["sharpe", "max_drawdown", "avg_turnover"]}},
    "futures_tsmom": {"runner": "research.paper.tsmom_forward:generate",
                      "rules": {"cadence": "monthly", "envelope": "backtest_envelope",
                                "compare": ["sharpe", "max_drawdown"]}},
    "kr_dart_buyback_drift_v1": {"runner": "research.paper.buyback_forward:generate",
                                 "rules": {"cadence": "per_event", "hold_days": 20,
                                           "compare": ["cohort_mean", "cohort_median", "right_tail"]}},
    "kr_turn_of_month_v1_PORTFOLIO": {"runner": "research.paper.tom_forward:generate",
                                      "rules": {"cadence": "monthly", "hold_days": 4,
                                                "envelope": "backtest_envelope",
                                                "compare": ["cohort_mean", "win_rate"]}},
    "fac_kr_size_smb_v1": {"runner": "research.paper.factor_forward:generate_kr_size_smb",
                           "rules": {"cadence": "monthly", "envelope": "backtest_envelope",
                                     "compare": ["monthly_mean", "monthly_std"]}},
    "fac_kr_amihud_illiq_v1": {"runner": "research.paper.factor_forward:generate_kr_amihud_illiq",
                               "rules": {"cadence": "monthly", "envelope": "backtest_envelope",
                                         "compare": ["monthly_mean", "monthly_std"]}},
    "fac_kr_turnover_neglect_v1": {"runner": "research.paper.factor_forward:generate_kr_turnover_neglect",
                                   "rules": {"cadence": "monthly", "envelope": "backtest_envelope",
                                             "compare": ["monthly_mean", "monthly_std"]}},
}
_GENERIC = {"runner": "generic", "rules": {"cadence": "manual", "ledger": "internal"}}

_DEPLOYABLE = {Status.PAPER_CANDIDATE.value, Status.PAPER_CANDIDATE_FWD.value}


def _deployments() -> list[dict]:
    p = state_path(_DEPLOY)
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def deployment_of(strategy_id: str) -> dict | None:
    rows = [d for d in _deployments() if d.get("strategy_id") == strategy_id]
    return rows[-1] if rows else None


def first_deployment_of(strategy_id: str) -> dict | None:
    """최초 배포 레코드(paper_start_date 용) — deployment_of() 는 최신 행(현재 러너/설정)을 준다."""
    rows = [d for d in _deployments() if d.get("strategy_id") == strategy_id]
    return rows[0] if rows else None


def all_deployments() -> list[dict]:
    """전략별 최신 배포(중복 제거)."""
    latest: dict = {}
    for d in _deployments():
        latest[d.get("strategy_id")] = d
    return list(latest.values())


def deploy(strategy_id: str) -> dict:
    """전제조건 검사 → paper_candidate→paper_active 전이 + forward 배포 기록."""
    require(PAPER_AGENT, "promote_to_paper_active", strategy_id)
    reg = StrategyRegistry()
    st = reg.state(strategy_id)
    if st is None:
        return {"strategy_id": strategy_id, "deployed": False, "reason": "not_registered"}
    if st["status"] == Status.PAPER_ACTIVE.value:
        return {"strategy_id": strategy_id, "deployed": False, "reason": "already_paper_active"}
    if st["status"] not in _DEPLOYABLE:
        return {"strategy_id": strategy_id, "deployed": False, "reason": f"not_paper_candidate({st['status']})"}
    if not st.get("frozen"):
        return {"strategy_id": strategy_id, "deployed": False, "reason": "config_not_frozen"}

    wiring = RUNNER_REGISTRY.get(strategy_id, _GENERIC)
    dep = {
        "strategy_id": strategy_id, "runner": wiring["runner"], "rules": wiring["rules"],
        "config_hash": st.get("config_hash"), "capital": "paper", "live": "disabled",
        "deployed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    os.makedirs(os.path.dirname(state_path(_DEPLOY)), exist_ok=True)
    with open(state_path(_DEPLOY), "a") as f:
        f.write(json.dumps(dep, ensure_ascii=False, default=str) + "\n")
    reg.transition(strategy_id, Status.PAPER_ACTIVE, "auto forward 배선",
                   evidence={"runner": wiring["runner"], "rules": wiring["rules"]})
    record({"layer": "paper_deploy", "action": "deploy_forward", "strategy_id": strategy_id,
            "runner": wiring["runner"], "result": "paper_active"})
    return {"strategy_id": strategy_id, "deployed": True, "runner": wiring["runner"], "rules": wiring["rules"]}


def auto_deploy_all() -> dict:
    """registry의 모든 paper_candidate → forward 자동 배포."""
    reg = StrategyRegistry()
    targets = [r["strategy_id"] for r in reg.all_current() if r["status"] in _DEPLOYABLE]
    out = [deploy(sid) for sid in targets]
    deployed = [o for o in out if o.get("deployed")]
    return {"candidates": len(targets), "deployed": len(deployed), "results": out}


def run_forward(strategy_id: str) -> dict:
    """배포된 forward 러너 실행(실데이터 필요 → 실패는 우아하게)."""
    dep = deployment_of(strategy_id)
    if dep is None:
        return {"strategy_id": strategy_id, "available": False, "reason": "not_deployed"}
    runner = dep["runner"]
    if runner == "generic":
        from jarvis.paper.ledger import PaperLedger
        return {"strategy_id": strategy_id, "available": True, "runner": "generic",
                "ledger": PaperLedger().summary(strategy_id)}
    mod, fn = runner.split(":")
    try:
        import importlib
        gen = getattr(importlib.import_module(mod), fn)
        report = gen(write=False)
        return {"strategy_id": strategy_id, "available": True, "runner": runner, "report": report}
    except Exception as exc:  # noqa: BLE001
        return {"strategy_id": strategy_id, "available": False, "runner": runner,
                "reason": f"러너 실행불가(데이터/연결 필요): {exc}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.paper.deploy")
    ap.add_argument("--strategy", default=None, help="특정 전략만(없으면 전체 자동배포)")
    args = ap.parse_args(argv)
    res = deploy(args.strategy) if args.strategy else auto_deploy_all()
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
