"""KR 횡단면 팩터 forward-test — shadow 원장 + 월간 리포트 (모니터링/리포팅 자동화만).

engines_factor.py(동결·튜닝 금지)의 private 헬퍼를 그대로 재사용(읽기 전용, 수정 안 함).
engines_factor._panel()은 날짜를 노출 안 해서, 월별 L-S 수익을 날짜와 함께 뽑는
_panel_dated()만 로컬로 복제(다른 로직은 전부 원본 재사용). tsmom_forward.py와
동일 패턴(envelope/forward_months/envelope_deviation) — 3개 팩터를 fid로 파라미터화한
단일 공유 모듈(factor_config.CANDIDATES 3개 전부 동일 계산 구조라 개별 모듈 불필요).

CLI: PYTHONPATH=. python3 research/paper/factor_forward.py --fid kr_size_smb [--since YYYY-MM]
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import statistics as _st

import numpy as np

from research.autoresearch.engines_factor import FACTORS, COST_M, STRESS_M, _WIN, _MIN_STOCKS, _MIN_MONTHS, _month_ends, _signal_at
from research.paper import factor_config as CFG

_DIR = os.path.dirname(__file__)


def _ledger_path(fid: str) -> str:
    return os.path.join(_DIR, f"factor_forward_{fid}_ledger.jsonl")


def _report_path(fid: str) -> str:
    return os.path.join(_DIR, f"factor_forward_{fid}_report.md")


def _series():
    from research.scanner.event_study import load_series
    return load_series()


def _panel_dated(fid: str, series: dict) -> list[tuple[str, list, list]]:
    """engines_factor._panel()과 동일 로직 + 월(e1) 라벨. 원본은 날짜 미노출이라 복제
    (원본 수정 금지 — 동결 모듈)."""
    kind = FACTORS[fid]["signal"]
    ends = _month_ends(series)
    if len(ends) < _MIN_MONTHS + 1:
        return []
    out = []
    for mi in range(len(ends) - 1):
        e0, e1 = ends[mi], ends[mi + 1]
        sigs, fwds = [], []
        for code, s in series.items():
            ds = s["dates"]
            j0 = bisect.bisect_right(ds, e0) - 1
            if j0 < _WIN or ds[j0][:7] != e0[:7]:
                continue
            j1 = bisect.bisect_right(ds, e1) - 1
            if j1 <= j0 or ds[j1][:7] != e1[:7]:
                continue
            c0, c1 = s["close"][j0], s["close"][j1]
            if c0 <= 0 or c1 <= 0:
                continue
            sig = _signal_at(kind, s, j0)
            if sig is None:
                continue
            sigs.append(sig)
            fwds.append(c1 / c0 - 1.0)
        if len(sigs) >= _MIN_STOCKS:
            out.append((e1[:7], sigs, fwds))
    return out


def monthly_ls_returns(fid: str, series: dict, cost_bps: float = COST_M) -> dict:
    """월별 L-S(long-short) 순수익 — run_factor()와 동일 leg 구성(quintile), 비용 차감."""
    long_low = FACTORS[fid]["long_low"]
    out = {}
    for month, sigs, fwds in _panel_dated(fid, series):
        a_sig, a_fwd = np.asarray(sigs), np.asarray(fwds)
        order = np.argsort(a_sig)
        k = max(5, len(order) // 5)
        lo_leg, hi_leg = order[:k], order[-k:]
        long_leg, short_leg = (lo_leg, hi_leg) if long_low else (hi_leg, lo_leg)
        ls = float(a_fwd[long_leg].mean() - a_fwd[short_leg].mean()) - cost_bps
        out[month] = round(ls, 6)
    return out


def backtest_envelope(mret: dict) -> dict:
    vals = list(mret.values())
    if len(vals) < 2:
        return {"monthly_mean": None, "monthly_std": None, "monthly_p10": None,
                "monthly_p90": None, "n_months": len(vals)}
    srt = sorted(vals)
    return {
        "monthly_mean": round(_st.mean(vals), 6), "monthly_std": round(_st.stdev(vals), 6),
        "monthly_p10": round(srt[int(len(srt) * 0.1)], 6), "monthly_p90": round(srt[int(len(srt) * 0.9)], 6),
        "n_months": len(vals),
    }


def generate(fid: str, since: str | None = None, write: bool = True) -> dict:
    cfg = CFG.CANDIDATES[fid]
    series = _series()
    mret_base = monthly_ls_returns(fid, series, CFG.COST_BASE_BPS / 10_000.0)
    mret_stress = monthly_ls_returns(fid, series, CFG.COST_STRESS_BPS / 10_000.0)
    env = backtest_envelope(mret_base)
    last_month = max(mret_base) if mret_base else None

    since = since or CFG.FROZEN_AT
    fwd = {m: v for m, v in mret_base.items() if m >= since}
    deviations = {
        m: ("BELOW_P10" if env["monthly_p10"] is not None and v < env["monthly_p10"]
            else "ABOVE_P90" if env["monthly_p90"] is not None and v > env["monthly_p90"]
            else "in_envelope")
        for m, v in fwd.items()
    }

    report = {
        "fid": fid, "version": cfg["version"], "status": CFG.STATUS, "as_of": last_month,
        "config_frozen": {"signal": cfg["signal"], "long_low": cfg["long_low"],
                          "cost_base_bps": CFG.COST_BASE_BPS, "cost_stress_bps": CFG.COST_STRESS_BPS},
        "backtest_envelope": env,
        "cost": {"base_mean": env["monthly_mean"],
                 "stress_mean": round(_st.mean(list(mret_stress.values())), 6) if mret_stress else None},
        "forward_months": fwd, "envelope_deviation": deviations,
        "baseline_ref": cfg["baseline"],
    }
    if write:
        _write_md(report)
        _append_ledger(fid, {"as_of": last_month, "n_forward": len(fwd), "forward_months": fwd})
    return report


def generate_all(since: str | None = None, write: bool = True) -> dict:
    return {fid: generate(fid, since=since, write=write) for fid in CFG.CANDIDATES}


def _append_ledger(fid: str, entry: dict):
    with open(_ledger_path(fid), "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _write_md(r: dict):
    env = r["backtest_envelope"]; c = r["cost"]
    lines = [
        f"# KR Factor Forward-Test Report — {r['version']} ({r['fid']})",
        "",
        f"> **{r['status']}** · as of {r['as_of']} · ⚠️ PAPER ONLY, NO LIVE CAPITAL.",
        f"> config 동결(튜닝 금지): signal={r['config_frozen']['signal']} long_low={r['config_frozen']['long_low']} "
        f"cost {r['config_frozen']['cost_base_bps']}/{r['config_frozen']['cost_stress_bps']}bps",
        "",
        "## Backtest Envelope (forward 비교 기준)",
        f"- 월평균 {env['monthly_mean']} std {env['monthly_std']} · P10 {env['monthly_p10']} / P90 {env['monthly_p90']} (n={env['n_months']})",
        "",
        "## 비용 스트레스",
        f"- base 월평균 {c['base_mean']} / stress(160bps) 월평균 {c['stress_mean']}",
        "",
        f"## Baseline (auto-research 검증 시점, frozen_at={CFG.FROZEN_AT})",
        f"- {r['baseline_ref']}",
        "",
        "## Forward Months (envelope 이탈)",
    ]
    if r["forward_months"]:
        for m, v in sorted(r["forward_months"].items()):
            lines.append(f"- {m}: {v:+.4f} → {r['envelope_deviation'][m]}")
    else:
        lines.append("- (아직 forward 월 없음 — 월마다 최신 데이터 pull 후 재실행)")
    lines += ["", "## 운영 원칙", "- live capital 금지. 신호/quintile/리밸런스/비용 변경 금지. 결과 후 튜닝 금지."]
    os.makedirs(_DIR, exist_ok=True)
    with open(_report_path(r["fid"]), "w") as f:
        f.write("\n".join(lines) + "\n")


def generate_kr_size_smb(write: bool = True) -> dict:
    return generate("kr_size_smb", write=write)


def generate_kr_amihud_illiq(write: bool = True) -> dict:
    return generate("kr_amihud_illiq", write=write)


def generate_kr_turnover_neglect(write: bool = True) -> dict:
    return generate("kr_turnover_neglect", write=write)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fid", choices=list(CFG.CANDIDATES), help="없으면 3개 전부")
    ap.add_argument("--since", help="forward 월 시작 YYYY-MM-DD (envelope 이탈 체크)")
    args = ap.parse_args()
    if args.fid:
        r = generate(args.fid, args.since)
        print(f"report → {_report_path(args.fid)}")
        print(f"as_of {r['as_of']} | envelope mean {r['backtest_envelope']['monthly_mean']} "
              f"P10/P90 {r['backtest_envelope']['monthly_p10']}/{r['backtest_envelope']['monthly_p90']}")
    else:
        for fid, r in generate_all(args.since).items():
            print(f"{fid}: as_of {r['as_of']} | envelope mean {r['backtest_envelope']['monthly_mean']}")


if __name__ == "__main__":
    main()
