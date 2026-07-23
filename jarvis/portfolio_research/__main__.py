"""`python -m jarvis.portfolio_research <cmd>` — 포트폴리오 연구 인텔리전스 CLI. **연구 전용.**

  portfolio  --portfolio-id --name --author --objective [--description] [--version V --method M] [--commit]
  hypothesis --portfolio-id --version --statement [--rationale] [--commit]
  construct  --portfolio-id --version --method --weights-json [--rebalance ...] [--commit]
  backtest   --study-id --sharpe --return --volatility --max-drawdown --turnover [--commit]
  risk       --study-id --max-weight --n-holdings --concentration --var95 [--commit]
  compare    --portfolio-a --portfolio-b [--commit]
  report / verify / summary / replay

실제 자본배분·주문·portfolio mutation·live trading·자동배포 없음 — 연구 기록·분석만. VALIDATED≠deployment.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _p(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _eng():
    from jarvis.portfolio_research.engine import PortfolioResearchEngine
    return PortfolioResearchEngine()


def _split(s: str) -> list:
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def _cmd_portfolio(a) -> int:
    eng = _eng()
    p = eng.register_portfolio(a.portfolio_id, a.name, a.description or "", a.author,
                               a.objective, _now(), commit=a.commit)
    if a.version:
        eng.create_version(a.portfolio_id, a.version, a.author, a.method or "equal_weight",
                           [], {}, "", _now(), commit=a.commit)
    _p({"committed": a.commit, "portfolio": p.to_dict()})
    return 0


def _cmd_hypothesis(a) -> int:
    h = _eng().create_hypothesis(a.portfolio_id, a.version, a.statement, a.rationale or "",
                                 _now(), commit=a.commit)
    _p({"committed": a.commit, "hypothesis": h.to_dict()})
    return 0


def _cmd_construct(a) -> int:
    weights = json.loads(a.weights_json)
    r = _eng().record_construction(a.portfolio_id, a.version, a.method, weights,
                                   a.rebalance or "monthly", _now(), commit=a.commit)
    _p({"committed": a.commit, "construction": r.to_dict(),
        "note": "이론적 가중치 — 실제 자본 배분 아님"})
    return 0


def _cmd_backtest(a) -> int:
    r = _eng().record_backtest(a.study_id, total_return=a.total_return, volatility=a.volatility,
                               sharpe=a.sharpe, max_drawdown=a.max_drawdown, turnover=a.turnover,
                               now=_now(), commit=a.commit)
    _p({"committed": a.commit, "backtest": r.to_dict()})
    return 0


def _cmd_risk(a) -> int:
    metrics = {"max_weight": a.max_weight, "n_holdings": a.n_holdings,
               "concentration": a.concentration, "var_95": a.var95}
    r = _eng().record_risk_analysis(a.study_id, metrics, _now(), commit=a.commit)
    _p({"committed": a.commit, "risk_analysis": r.to_dict()})
    return 0


def _cmd_compare(a) -> int:
    r = _eng().compare_portfolios(a.portfolio_a, a.portfolio_b, _now(), commit=a.commit)
    _p({"committed": a.commit, "comparison": r.to_dict(), "note": "추천 기록만 — 자동 선택 아님"})
    return 0


def _cmd_report(a) -> int:
    _p(_eng().generate_portfolio_report(_now()).to_dict())
    return 0


def _cmd_verify(a) -> int:
    from jarvis.portfolio_research.verify import verify_chain
    res = verify_chain()
    _p(res)
    return 0 if res["ok"] else 1


def _cmd_replay(a) -> int:
    from jarvis.portfolio_research.verify import replay
    _p(replay(_eng(), _now()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.portfolio_research")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("portfolio")
    for f in ("portfolio-id", "name", "author", "objective"):
        p.add_argument(f"--{f}", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--version", default="")
    p.add_argument("--method", default="equal_weight")
    p.add_argument("--commit", action="store_true")
    h = sub.add_parser("hypothesis")
    for f in ("portfolio-id", "version", "statement"):
        h.add_argument(f"--{f}", required=True)
    h.add_argument("--rationale", default="")
    h.add_argument("--commit", action="store_true")
    c = sub.add_parser("construct")
    for f in ("portfolio-id", "version", "method", "weights-json"):
        c.add_argument(f"--{f}", required=True)
    c.add_argument("--rebalance", default="monthly")
    c.add_argument("--commit", action="store_true")
    b = sub.add_parser("backtest")
    b.add_argument("--study-id", required=True)
    for f in ("total-return", "volatility", "sharpe", "max-drawdown", "turnover"):
        b.add_argument(f"--{f}", type=float, default=0.0)
    b.add_argument("--commit", action="store_true")
    r = sub.add_parser("risk")
    r.add_argument("--study-id", required=True)
    r.add_argument("--max-weight", type=float, default=0.0)
    r.add_argument("--n-holdings", type=int, default=0)
    r.add_argument("--concentration", type=float, default=0.0)
    r.add_argument("--var95", type=float, default=0.0)
    r.add_argument("--commit", action="store_true")
    cm = sub.add_parser("compare")
    cm.add_argument("--portfolio-a", required=True)
    cm.add_argument("--portfolio-b", required=True)
    cm.add_argument("--commit", action="store_true")
    sub.add_parser("report")
    sub.add_parser("verify")
    sub.add_parser("summary")
    sub.add_parser("replay")
    args = ap.parse_args(argv)
    disp = {"portfolio": _cmd_portfolio, "hypothesis": _cmd_hypothesis, "construct": _cmd_construct,
            "backtest": _cmd_backtest, "risk": _cmd_risk, "compare": _cmd_compare,
            "report": _cmd_report, "verify": _cmd_verify, "summary": _cmd_report,
            "replay": _cmd_replay}
    return disp[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
