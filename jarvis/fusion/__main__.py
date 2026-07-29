"""`python -m jarvis.fusion <cmd>` — CLI 검증/실행.

  schemes                 스킴 목록 + 구현상태
  validate [--scheme X]   결정적 속성검사(통과=exit 0)
  run [--scheme X] [--write]  검증전략 신호 수집 → 합성 → 출력(선택 원장기록)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cmd_schemes() -> int:
    from jarvis.fusion.weighting import SCHEMES
    rows = [{"scheme": n, "implemented": s.implemented} for n, s in SCHEMES.items()]
    print(json.dumps({"schemes": rows}, ensure_ascii=False, indent=2))
    return 0


def _cmd_validate(scheme: str) -> int:
    from jarvis.fusion.validate import validate_scheme
    res = validate_scheme(scheme)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["passed"] else 1


def _cmd_run(scheme: str, write: bool, normalize: bool, norm_method: str) -> int:
    from jarvis.fusion.fusion import FusionEngine
    from jarvis.fusion.performance import perf_for
    from jarvis.fusion.providers import collect_signals
    as_of = _now()
    signals, skipped = collect_signals(as_of)
    if not signals:
        print(json.dumps({"as_of": as_of, "scheme": scheme, "fusion_signals": [],
                          "note": "fusion-eligible 신호 없음(어댑터 미배선 — 정직한 현주소)",
                          "skipped": skipped}, ensure_ascii=False, indent=2))
        return 0
    if normalize:
        from jarvis.fusion.normalize import normalize_signals
        signals = normalize_signals(signals, norm_method)
    perfs = {s.strategy_id: perf_for(s.strategy_id) for s in signals}
    fused = FusionEngine(scheme).fuse(signals, perfs, as_of)
    out = {"as_of": as_of, "scheme": scheme, "n_signals": len(signals),
           "normalized": normalize, "norm_method": norm_method if normalize else None,
           "skipped": skipped, "fusion_signals": [f.to_dict() for f in fused]}
    if write:
        from jarvis.fusion.ledger import write_signals
        out["written"] = write_signals(fused, scheme)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_diagnose() -> int:
    from jarvis.fusion.diagnostics import adapter_status, buyback_freshness
    as_of = _now()
    out = {"as_of": as_of, "adapters": adapter_status(as_of),
           "buyback_freshness": buyback_freshness(as_of)}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def _cmd_backtest(scheme: str) -> int:
    from jarvis.fusion.backtest import compare_performance
    from jarvis.fusion.performance import assemble_returns
    from jarvis.fusion.providers import eligible_strategy_ids
    returns = {}
    for sid in eligible_strategy_ids():
        r, _src = assemble_returns(sid)
        if len(r) >= 2:
            returns[sid] = r
    rep = compare_performance(returns)
    rep["as_of"] = _now()
    rep["note"] = ("융합 분산지표는 수익률 있는 전략 ≥2 필요. "
                   "현재 실데이터 커버리지: " + ", ".join(returns) if returns else "실수익률 전략 없음")
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jarvis.fusion")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schemes")
    v = sub.add_parser("validate")
    v.add_argument("--scheme", default="v1_risk_adjusted")
    r = sub.add_parser("run")
    r.add_argument("--scheme", default="v1_risk_adjusted")
    r.add_argument("--write", action="store_true")
    r.add_argument("--no-normalize", dest="normalize", action="store_false")
    r.add_argument("--norm-method", default="rank")
    sub.add_parser("diagnose")
    b = sub.add_parser("backtest")
    b.add_argument("--scheme", default="v1_risk_adjusted")
    args = ap.parse_args(argv)
    if args.cmd == "schemes":
        return _cmd_schemes()
    if args.cmd == "validate":
        return _cmd_validate(args.scheme)
    if args.cmd == "run":
        return _cmd_run(args.scheme, args.write, args.normalize, args.norm_method)
    if args.cmd == "diagnose":
        return _cmd_diagnose()
    if args.cmd == "backtest":
        return _cmd_backtest(args.scheme)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
