"""Jarvis 파이프라인 오케스트레이터 — research→datagate→backtest→critic→registry.

핵심 가드: **BH-FDR 다중검정 예산.** 배치로 여러 가설을 검정하면 우연히 p<0.05 나옴.
그래서 paper_candidate 승격은 critic 통과 + **BH-FDR 생존** 둘 다 필요.
결정적·감사가능. LLM 없음(아이디어 생성만 CLI/스케줄이 담당).
"""
from __future__ import annotations

import argparse
import json

from jarvis.agents import backtest, critic, datagate, research
from jarvis.permissions import Level, Principal, require
from jarvis.registry import Status, StrategyRegistry
from research.validation.multiple_testing import benjamini_hochberg

# 오케스트레이터 principal — BACKTEST_ONLY(watchlist/paper_candidate까지만, live 불가).
PIPELINE = Principal("pipeline_orchestrator", Level.BACKTEST_ONLY)


def run_hypothesis(spec: dict) -> dict:
    """단일 가설: propose→datagate→(pass면)backtest→critic. registry 전이 커밋.

    반환: 스테이지 결과 + p_value(있으면). 승격 결정은 run_batch가 BH-FDR로."""
    sid = spec["id"]
    reg = StrategyRegistry()

    draft = research.propose(
        sid, spec.get("name", sid), rationale=spec.get("thesis", ""),
        required_data=spec.get("required_data", ["daily_ohlcv", "market_cap"]),
        expected_edge_type=spec.get("family", "event"),
        known_risks=spec.get("known_risks", ["small_sample"]),
        keywords=spec.get("keywords", [sid]))

    gate = datagate.check(sid, spec.get("required_data", ["daily_ohlcv", "market_cap"]), commit=True)
    if gate["status"] != "DATA_GATE_PASS":
        return {"strategy_id": sid, "stage": "data_gate", "gate": gate,
                "backtest": None, "critic": None, "p_value": None, "draft": draft}

    bt = backtest.run(sid, spec=spec if "edge_bps" in spec else None, commit=True)
    metrics = bt["metrics"]
    cr = critic.review(sid, metrics)
    return {"strategy_id": sid, "stage": "critic", "gate": gate, "backtest": bt,
            "critic": cr, "p_value": metrics.get("empirical_p"), "draft": draft}


def _redteam_gate(specs: list[dict], sid: str, run_result: dict) -> dict:
    """레드팀 통제 게이트. spec 특성 → 필요 통제 vs 실제 증거 → verdict.
    합성 파이프는 random·WF만 실행 → 실통제(cost_stress·survivorship·lookahead 등) 미실행 → BLOCKED."""
    from jarvis.redteam.review import review_strategy
    spec = next((s for s in specs if s.get("id") == sid), {})
    rt_spec = {"market": spec.get("market", ""), "family": spec.get("family", ""),
               "entry": spec.get("entry", ""), "event_type": spec.get("event_type", "")}
    m = (run_result.get("backtest") or {}).get("metrics") or {}
    pct = m.get("random_percentile")
    wf1, wf2 = m.get("wf_first"), m.get("wf_second")
    ev = {
        "random_baseline": "passed" if (pct is not None and pct >= 95) else "failed",
        "walk_forward": "passed" if (wf1 is not None and wf2 is not None and wf1 > 0 and wf2 > 0) else "failed",
        # 합성 파이프는 나머지 통제 미실행 = missing → 게이트가 정직하게 막음
    }
    return review_strategy(rt_spec, ev)


def run_batch(specs: list[dict], alpha: float = 0.1, auto_deploy: bool = True) -> dict:
    """배치 실행 + BH-FDR 예산. paper_candidate = critic 추천 AND BH 생존.

    auto_deploy=True면 승격된 paper_candidate를 즉시 forward-test에 자동 배선(paper_active)."""
    results = [run_hypothesis(s) for s in specs]

    # BH-FDR: 백테스트까지 간(p 있는) 가설만 대상
    tested = [r for r in results if r.get("p_value") is not None]
    pvals = [r["p_value"] for r in tested]
    bh = benjamini_hochberg(pvals, alpha=alpha)
    survivor = {tested[i]["strategy_id"]: bh["survivors"][i] for i in range(len(tested))}

    reg = StrategyRegistry()
    decisions = []
    for r in results:
        sid = r["strategy_id"]
        st = reg.state(sid)
        if st is None:
            continue
        status = st["status"]
        if status == Status.BLOCKED_BY_DATA.value:
            decisions.append({"strategy_id": sid, "final": "blocked_by_data", "bh_survivor": None})
            continue
        cr = r.get("critic") or {}
        rec = cr.get("recommendation", "rejected")

        if status != Status.BACKTESTED.value:
            decisions.append({"strategy_id": sid, "final": status, "bh_survivor": survivor.get(sid)})
            continue

        if rec == "rejected":
            require(PIPELINE, "register_rejected_strategy", sid)
            reg.transition(sid, Status.REJECTED, "critic: rejected", evidence=cr)
            final = "rejected"
        else:
            require(PIPELINE, "promote_to_watchlist", sid)
            reg.transition(sid, Status.WATCHLIST, f"critic: {rec}", evidence=cr)
            surv = survivor.get(sid, False)
            if rec == "paper_candidate" and surv:
                # 레드팀 게이트 — 필요 통제 전부 통과해야 paper. 합성 = 실통제 미실행 → BLOCKED.
                rt = _redteam_gate(specs, sid, r)
                if rt["verdict"] == "CLEARED":
                    require(PIPELINE, "promote_to_paper_candidate", sid)
                    reg.transition(sid, Status.PAPER_CANDIDATE, "critic+BH-FDR+레드팀 통과",
                                   evidence={"critic": cr, "p": r["p_value"], "redteam": rt})
                    final = "paper_candidate"
                else:
                    final = f"watchlist (레드팀 {rt['verdict']}: {','.join(rt['missing'] + rt['failed'])})"
            elif rec == "paper_candidate" and not surv:
                final = "watchlist (BH-FDR 예산 미통과)"
            else:
                final = "watchlist"
        decisions.append({"strategy_id": sid, "final": final, "bh_survivor": survivor.get(sid),
                          "p_value": r["p_value"], "critic_rec": rec})

    # Lv3: 승격된 paper_candidate 자동 forward 배선(paper_active)
    deployments = []
    if auto_deploy:
        from jarvis.paper.deploy import deploy
        for d in decisions:
            if d["final"] == "paper_candidate":
                deployments.append(deploy(d["strategy_id"]))

    return {
        "n_hypotheses": len(specs),
        "n_tested": len(tested),
        "bh_fdr": {"alpha": alpha, "n_survivors": bh["n_survivors"], "threshold": bh["threshold"]},
        "decisions": decisions,
        "forward_deployments": deployments,
    }


def _demo_specs() -> list[dict]:
    """데모 배치 — AI LAB 시드 가설을 스펙으로(CB/BW·PEAD·오버나잇)."""
    from research.lab.hypotheses import SEED_QUEUE
    rd_blocked = ["daily_ohlcv", "cb_bw_release_linkage", "remaining_convertible_balance"]
    rd_ok = ["daily_ohlcv", "market_cap", "disclosure_event_dates"]
    specs = []
    for h in SEED_QUEUE:
        s = {"id": h.id, "name": h.name, "family": h.family, "market": h.market,
             "thesis": h.thesis, "cost_bps": h.cost_bps,
             "required_data": rd_blocked if h.data_mode == "blocked" else rd_ok}
        if h.data_mode == "synthetic_demo":
            s.update(edge_bps=h.edge_bps, n_trades=h.n_trades,
                     hold=h.holding[0] if h.holding else 20, seed=h.seed)
        specs.append(s)
    return specs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("run-batch")
    b.add_argument("--alpha", type=float, default=0.1)
    b.add_argument("--specs", default=None, help="specs JSON 파일(없으면 데모)")
    args = ap.parse_args(argv)
    if args.cmd == "run-batch":
        import os
        specs = json.load(open(args.specs)) if (args.specs and os.path.exists(args.specs)) else _demo_specs()
        print(json.dumps(run_batch(specs, alpha=args.alpha), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
