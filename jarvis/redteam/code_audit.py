"""리서치 코드 감사 — lookahead/PIT/survivorship 패턴 정적 탐지.

배경: SMT swings() lookahead는 통계 게이트(BH-FDR·매칭 random·WF) 전부 통과하고
사람이 코드 읽다가 잡았음. 통계는 누수를 못 잡는다 — 코드가 잡아야 한다.

설계 원칙(Phase 123): 판정은 결정적, LLM은 검증요구. 이 모듈은 패턴 탐지 +
finding 리포트까지만. REJECTED 도장은 안 찍음(오탐 있는 정적 분석이 판정하면
그것도 거짓 확신). 사람/스케줄 Claude가 finding 읽고 판단.

CLI: PYTHONPATH=. python3 -m jarvis.redteam.code_audit research/run_x.py [...]
     인자 없으면 research/ 전체 run_*.py 스캔.
"""
from __future__ import annotations

import glob
import os
import re
import sys

# (패턴, 심각도, 설명). 심각도: high=누수 개연성 큼, warn=확인 필요, info=관례 체크.
_CHECKS: list[tuple[str, str, str]] = [
    (r"\.shift\(\s*-\d", "high",
     "음수 shift = 미래 데이터를 현재 행으로 끌어옴. 시그널 계산이면 lookahead."),
    (r"argrelextrema|find_peaks", "high",
     "전체 시계열 극값 탐지(swings 패턴) — 피벗 확정에 미래 봉 필요. SMT를 죽인 그 버그."),
    (r"pct_change\(\)\.shift\(\s*-", "high",
     "미래 수익률을 피처로 사용하는 전형 패턴."),
    (r"\bswings\(", "warn",
     "swings() 사용 — research/ict/primitives.swings는 lookahead 확인됨(Phase 122). 리드 계산이면 무효."),
    (r"yfinance|FinanceDataReader|fdr\.", "warn",
     "생존자 편향 데이터 소스(현재 상장분만) — KR 검증은 KRX PIT(krx_api) 사용해야 함."),
    (r"dropna\(\)\s*$", "info",
     "전 구간 dropna — 초반 워밍업 제거는 OK, 이벤트 구간 제거면 표본 왜곡 확인."),
    (r"random\.(?:choice|sample|shuffle)\((?![^)]*seed)", "info",
     "seed 없는 random — 재현성 확인(baselines.empirical_p_value는 SEED 고정 관례)."),
]

# 이벤트/시그널 스크립트인데 매칭 random 베이스라인 없음 = 검증 표준 미달
_REQUIRED_FOR_STUDY = [
    (r"empirical_p_value|random_stats|매칭 random|N_RUNS",
     "매칭 random 베이스라인 흔적 없음 — 검증 표준(랜덤 대비) 미적용 의심."),
]


def audit_file(path: str) -> list[dict]:
    src = open(path, encoding="utf-8").read()
    lines = src.splitlines()
    findings = []
    for pat, sev, why in _CHECKS:
        for i, ln in enumerate(lines, 1):
            if ln.lstrip().startswith("#"):
                continue
            if re.search(pat, ln):
                findings.append({"file": path, "line": i, "severity": sev,
                                 "code": ln.strip()[:100], "why": why})
    # 스터디 스크립트(run_*)면 랜덤 베이스라인 존재 체크
    base = os.path.basename(path)
    if base.startswith("run_"):
        for pat, why in _REQUIRED_FOR_STUDY:
            if not re.search(pat, src):
                findings.append({"file": path, "line": 0, "severity": "warn",
                                 "code": "(파일 전체)", "why": why})
    return findings


def audit(paths: list[str]) -> dict:
    findings: list[dict] = []
    for p in paths:
        try:
            findings.extend(audit_file(p))
        except Exception as exc:  # noqa: BLE001
            findings.append({"file": p, "line": 0, "severity": "warn",
                             "code": "", "why": f"파일 읽기 실패: {exc}"})
    n_high = sum(1 for f in findings if f["severity"] == "high")
    return {"files": len(paths), "findings": findings, "n_high": n_high,
            "verdict_note": "판정 아님 — high는 사람이 반드시 확인. 통계 게이트는 누수를 못 잡는다."}


def main() -> None:
    paths = sys.argv[1:]
    if not paths:
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "research")
        paths = sorted(glob.glob(os.path.join(root, "run_*.py")))
    r = audit(paths)
    print(f"코드 감사 — {r['files']}파일 · finding {len(r['findings'])} (high {r['n_high']})")
    for f in r["findings"]:
        loc = f"{os.path.relpath(f['file'])}:{f['line']}"
        print(f"  [{f['severity'].upper():4}] {loc} — {f['why']}")
        if f["code"]:
            print(f"         {f['code']}")
    print(f"\n{r['verdict_note']}")
    sys.exit(1 if r["n_high"] else 0)


if __name__ == "__main__":
    main()
