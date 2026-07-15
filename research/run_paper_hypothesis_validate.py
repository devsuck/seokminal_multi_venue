"""논문 자동생성 가설 검증 러너 — research/hypotheses/papers/*.py 통과분을
기존 runner.py 제네릭 엔진에 태우고, 논문가설 전용 신규 격리 BH-FDR 풀로
correction한다(기존 수동가설 풀과 절대 안 섞음, alpha=0.1).

각 가설은 이미 runner.run_universe() 내부에서 종목별 BH-FDR/OOS를 거친
pooled["empirical_p_value"]를 얻는다 — 이 러너는 그 pooled p-value들을
가설 간(논문 간) 레벨에서 다시 한번 BH-FDR로 묶는다. 실집행 근거 아님,
통계적 스크리닝만. CANDIDATE라도 라이브 집행은 기존 arm_criteria 게이트를
그대로 통과해야 함.
"""
from __future__ import annotations

import glob
import importlib.util
import os

from research.hypotheses.runner import run_universe
from research.validation.multiple_testing import benjamini_hochberg

_HYPOTHESES_DIR = "research/hypotheses/papers"


def _load_module(path: str):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(f"research.hypotheses.papers.{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_hypotheses() -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(_HYPOTHESES_DIR, "*.py"))):
        module = _load_module(path)
        if all(hasattr(module, s) for s in ("NAME", "DESCRIPTION", "signal_fn")):
            out.append({"path": path, "name": module.NAME, "desc": module.DESCRIPTION, "signal_fn": module.signal_fn})
    return out


def main() -> dict:
    hypotheses = discover_hypotheses()
    results = []
    pvals: list[float] = []
    names: list[str] = []

    for h in hypotheses:
        r = run_universe(h["name"], h["desc"], h["signal_fn"])
        results.append(r)
        pval = r["pooled"]["empirical_p_value"]
        if pval is not None:
            pvals.append(pval)
            names.append(h["name"])

    bh = benjamini_hochberg(pvals, alpha=0.1) if pvals else {
        "survivors": [], "n_survivors": 0, "threshold": None, "alpha": 0.1,
    }
    bh["names"] = names

    print(f"\n=== 논문가설 {len(hypotheses)}개 검증 (신규 격리 BH-FDR 풀, alpha=0.1) ===\n")
    for r in results:
        p = r["pooled"]
        print(f"{r['name']}: pnl={p['total_pnl']} p={p['empirical_p_value']} "
              f"pct={p['percentile_vs_random']} verdict={r['verdict']}")
    survivors = [n for n, s in zip(bh["names"], bh["survivors"]) if s]
    print(f"\nsurvivors: {survivors}")
    print(f"n_survivors: {bh['n_survivors']} / {len(pvals)}")

    return {"results": results, "bh_fdr": bh}


if __name__ == "__main__":
    main()
