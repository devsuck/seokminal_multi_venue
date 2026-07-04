"""KR 이벤트 family 스캐너 실행 — 생성기+실검증+레드팀. 밤새 systematic 스캔.

각 family: 이벤트 로드/pull → 이벤트스터디(실데이터) → 레드팀 전통제 → verdict.
합성 아님. survivorship·cost·WF·outlier 전부 실행. 생존자 = 진짜 후보.
실행: PYTHONPATH=. python3 research/run_scanner.py [--pull]
"""
from __future__ import annotations

import sys

from research.agents.experiment_registry import log_experiment
from research.data.kr_dart_events import EVENT_DEFS, load_events, pull_events, save_events
from research.scanner.event_study import event_study, load_series
from research.scanner.families import FAMILIES, redteam_spec


def _load_or_pull(fam_id: str, fam: dict, do_pull: bool):
    """캐시 있으면 로드, 없고 pull이면 DART 증분(EVENT_DEFS 동적 등록)."""
    ev = load_events(fam_id)
    if ev:
        return ev
    if not do_pull:
        return []
    EVENT_DEFS[fam_id] = {"include": fam["keywords"], "exclude": fam["exclude"], "bias": fam["direction"],
                          "pblntf_ty": fam.get("pblntf_ty", "B")}
    rows = pull_events(fam_id, years=6.5)
    save_events(fam_id, rows)
    return rows


def main():
    do_pull = "--pull" in sys.argv
    print("=" * 76)
    print(f"KR 이벤트 family 스캐너 — {len(FAMILIES)} family (pull={'ON' if do_pull else 'OFF'})")
    print("=" * 76)
    series = load_series()
    from jarvis.redteam.review import review_strategy

    results = []
    for fam_id, fam in FAMILIES.items():
        ev = _load_or_pull(fam_id, fam, do_pull)
        if len(ev) < 30:
            print(f"\n[{fam_id}] 이벤트 {len(ev)} — UNDERPOWERED (데이터 부족/커버리지)")
            results.append((fam_id, "UNDERPOWERED", None)); continue
        res = event_study(ev, series, fam["direction"])
        if res.get("verdict") == "UNDERPOWERED":
            print(f"\n[{fam_id}] 매칭 {res['n']} — UNDERPOWERED"); results.append((fam_id, "UNDERPOWERED", None)); continue
        rt = review_strategy(redteam_spec(fam_id, fam), res["evidence"])
        results.append((fam_id, rt["verdict"], res))
        print(f"\n[{fam_id}] {fam['thesis'][:40]}")
        print(f"  n={res['n']} net={res['net']:+.4f} median={res['median']:+.4f} pct={res['percentile']} p={res['p']} "
              f"WF={res['wf_first']:+.4f}/{res['wf_second']:+.4f} 상위꼬리={res['top_tail_share']}")
        print(f"  레드팀 {rt['verdict']}" + (f" [실패: {','.join(rt['failed'])}]" if rt["failed"] else "")
              + (f" [미실행: {','.join(rt['missing'])}]" if rt["missing"] else ""))
        log_experiment({"hypothesis_id": f"scan_{fam_id}", "status": "candidate" if rt["verdict"] == "CLEARED" else "rejected",
                        "n": res["n"], "net": res["net"], "percentile": res["percentile"], "p": res["p"],
                        "wf_first": res["wf_first"], "wf_second": res["wf_second"], "redteam": rt["verdict"],
                        "direction": fam["direction"], "data_quality": "KRX PIT survivorship-free",
                        "verdict": f"스캐너 {rt['verdict']}", "note": f"{fam['thesis']}"})

    cleared = [r for r in results if r[1] == "CLEARED"]
    print("\n" + "=" * 76)
    print(f"스캔 완료: {len(FAMILIES)} family | CLEARED {len(cleared)} | 나머지 REJECT/UNDERPOWERED")
    if cleared:
        print("★ 레드팀 전통제 통과 (진짜 후보):")
        for fid, _, res in cleared:
            print(f"   {fid}: net {res['net']:+.4f} pct {res['percentile']} (방향 {res['direction']})")
    else:
        print("생존 0 — 이번 스캔 family는 전부 탈락(정직). 새 엣지 없음.")


if __name__ == "__main__":
    main()
