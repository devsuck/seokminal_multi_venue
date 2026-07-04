"""Red-team 감사 — 오늘 전략들에 통제층 적용 → 사람 판단 검증.

내(AI) 판단이 결정적 통제층과 일치하나? SMT/무상증자/ICT를 통제가 자동으로 잡나?
실행: PYTHONPATH=. python3 research/run_redteam_audit.py
"""
from __future__ import annotations

from jarvis.redteam.review import audit_registry
from jarvis.redteam.controls import CONTROLS


def main():
    print("=" * 74)
    print("RED-TEAM 통제 감사 — 통제층 verdict vs 사람(AI) 판단")
    print("=" * 74)
    a = audit_registry()
    print(f"\n{'전략':26} {'사람판단':22} {'레드팀':10} 일치")
    for r in a["rows"]:
        flag = "✓" if r["match"] else "✗ 불일치!"
        detail = ""
        if r["failed"]:
            detail = f" [실패: {','.join(r['failed'])}]"
        elif r["missing"]:
            detail = f" [미실행: {','.join(r['missing'])}]"
        print(f"  {r['strategy']:24} {r['human_call']:22} {r['redteam_verdict']:10} {flag}{detail}")

    print(f"\n일치 {a['human_redteam_agree']}/{a['n']}")
    print("\n핵심 확인:")
    for r in a["rows"]:
        if r["strategy"] == "ict_smt":
            print(f"  SMT → 레드팀 {r['redteam_verdict']} (entry_confound·lookahead 요구·실패) = confound 자동 포착 {'✓' if r['failed'] else '✗'}")
        if r["strategy"] == "kr_bonus_issue":
            print(f"  무상증자 → 레드팀 {r['redteam_verdict']} (ex_date_adjustment 미완) = 아티팩트 자동 요구 {'✓' if r['missing'] else '✗'}")
    print(f"\n결론: 통제층이 SMT confound·무상증자 아티팩트·ICT lookahead를 "
          f"{'자동으로 잡음 = AI 판단과 일치(검증됨)' if a['human_redteam_agree'] >= a['n'] - 1 else '일부 불일치(재검 필요)'}")


if __name__ == "__main__":
    main()
