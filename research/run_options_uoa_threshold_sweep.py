"""옵션 UOA 임계값 스윕 — 3단계(수집→라벨링→**여기**→BH-FDR/워크포워드 정식등록).

원 질문("노이즈 많으면 vol/oi 임계값 올리면 되는거 아닌가")에 답한다. max_vol_oi 컷오프를
올려가며 사후수익률(fwd_1d/fwd_3d) 평균이 유의하게 양(+)인지 본다. 표본이 다지선다이므로
BH-FDR로 다중검정 보정(각 컷오프×지평선 조합을 독립 가설로 취급).

실행: PYTHONPATH=. python3 research/run_options_uoa_threshold_sweep.py
"""
from __future__ import annotations

import json
from pathlib import Path

from scipy import stats

from research.validation.multiple_testing import benjamini_hochberg

_LABELS = Path(__file__).parent / "data" / "options_uoa_forward" / "labels.jsonl"
CUTOFFS = [3.0, 5.0, 10.0, 20.0]
HORIZONS = [1, 3]  # 5d는 표본 너무 적음(수집 더 필요)
MIN_N = 10  # 이 미만이면 t-검정 자체를 안 함(표본 부족)


def load_labels() -> list[dict]:
    rows = []
    with _LABELS.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    labels = load_labels()
    print("=" * 72)
    print("OPTIONS UOA 임계값 스윕 (RESEARCH — 판정 아님)")
    print(f"라벨 {len(labels)}건 로드, 컷오프={CUTOFFS}, 지평선={HORIZONS}일")
    print("=" * 72)

    tests = []  # (label, n, mean, pvalue)
    for h in HORIZONS:
        key = f"fwd_{h}d"
        for cut in CUTOFFS:
            vals = [r[key] for r in labels if r["max_vol_oi"] >= cut and r.get(key) is not None]
            if len(vals) < MIN_N:
                print(f"  {key} vol_oi>={cut}: n={len(vals)} < {MIN_N} — 스킵(표본 부족)")
                continue
            mean = sum(vals) / len(vals)
            _, p = stats.ttest_1samp(vals, 0.0)
            tests.append({"label": f"{key} vol_oi>={cut}", "n": len(vals), "mean": mean, "p": p})

    if not tests:
        print("검정 가능한 조합 없음 — 표본이 전반적으로 부족.")
        return

    pvals = [t["p"] for t in tests]
    bh = benjamini_hochberg(pvals, alpha=0.1)

    print()
    print(f"{'조합':<20}{'n':>6}{'평균':>10}{'p값':>10}{'BH생존':>8}")
    for t, survived in zip(tests, bh["survivors"]):
        print(f"{t['label']:<20}{t['n']:>6}{t['mean']:>+10.4f}{t['p']:>10.4f}{'Y' if survived else '-':>8}")

    print()
    print(f"BH-FDR(alpha=0.1) 생존: {bh['n_survivors']}/{len(tests)}")
    print("주의: 생존 0건이면 '임계값 올리면 노이즈 걸러진다'는 가설 이 데이터로는 기각.")


if __name__ == "__main__":
    main()
