"""데이터 없던 3 family(소각/손익구조/공급계약) 키워드·피드 수정 후 재pull + 재검증.
run_scanner와 같은 pull/study/redteam/log 경로 재사용."""
import sys
from research.scanner.families import FAMILIES, redteam_spec
from research.scanner.event_study import event_study, load_series
from research.run_scanner import _load_or_pull
from jarvis.redteam.review import review_strategy
from research.agents.experiment_registry import log_experiment

TARGETS = ["supply_contract", "turn_to_profit", "buyback_cancel"]  # I피드(빠른 실패 없음) 우선


def main():
    print("=" * 76)
    print("REFILL 스캔 — 3 family 키워드/피드 수정 재pull")
    print("=" * 76, flush=True)
    series = load_series()
    for fam_id in TARGETS:
        fam = FAMILIES[fam_id]
        print(f"\n[{fam_id}] pull 시작 feed={fam.get('pblntf_ty','B')} kw={fam['keywords']}", flush=True)
        ev = _load_or_pull(fam_id, fam, do_pull=True)
        print(f"[{fam_id}] pull 완료 — {len(ev)} 이벤트", flush=True)
        if len(ev) < 30:
            print(f"[{fam_id}] UNDERPOWERED (여전히 데이터 부족)", flush=True); continue
        res = event_study(ev, series, fam["direction"])
        if res.get("verdict") == "UNDERPOWERED":
            print(f"[{fam_id}] 매칭 {res['n']} UNDERPOWERED", flush=True); continue
        rt = review_strategy(redteam_spec(fam_id, fam), res["evidence"])
        print(f"[{fam_id}] {fam['thesis'][:44]}")
        print(f"  n={res['n']} net={res['net']:+.4f} median={res['median']:+.4f} pct={res['percentile']} "
              f"p={res['p']} WF={res['wf_first']:+.4f}/{res['wf_second']:+.4f} 상위꼬리={res['top_tail_share']}")
        print(f"  레드팀 {rt['verdict']}" + (f" [실패: {','.join(rt['failed'])}]" if rt['failed'] else "")
              + (f" [미실행: {','.join(rt['missing'])}]" if rt['missing'] else ""), flush=True)
        log_experiment({"hypothesis_id": f"scan_{fam_id}", "status": "candidate" if rt["verdict"] == "CLEARED" else "rejected",
                        "n": res["n"], "net": res["net"], "percentile": res["percentile"], "p": res["p"],
                        "wf_first": res["wf_first"], "wf_second": res["wf_second"], "redteam": rt["verdict"],
                        "direction": fam["direction"], "data_quality": "KRX PIT survivorship-free",
                        "verdict": f"스캐너(refill) {rt['verdict']}", "note": fam["thesis"]})
    print("\n" + "=" * 76 + "\nREFILL 완료", flush=True)


if __name__ == "__main__":
    main()
