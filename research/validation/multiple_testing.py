"""다중검정 보정 — 여러 종목을 동시에 테스트하면 우연히 p<0.05가 나옴.
30개 독립검정에서 최소 1개 p<0.05 확률 ≈ 78.5%. 그래서 보정 필수."""
from __future__ import annotations


def benjamini_hochberg(pvals: list[float], alpha: float = 0.1) -> dict:
    """BH-FDR 절차. 반환: {survivors:[bool 원순서], n_survivors, threshold, alpha}.

    p 오름차순 정렬 후 p_(k) <= (k/m)*alpha 인 최대 k까지 기각.
    survivors = 그 임계 이하 p들(원래 순서 기준 bool 마스크)."""
    m = len(pvals)
    if m == 0:
        return {"survivors": [], "n_survivors": 0, "threshold": None, "alpha": alpha}
    indexed = sorted(range(m), key=lambda i: pvals[i])  # p 오름차순 원인덱스
    max_k = 0
    thresh = 0.0
    for rank, orig in enumerate(indexed, start=1):
        crit = (rank / m) * alpha
        if pvals[orig] <= crit:
            max_k = rank
            thresh = pvals[orig]
    survivors = [False] * m
    if max_k > 0:
        for rank, orig in enumerate(indexed, start=1):
            if rank <= max_k:
                survivors[orig] = True
    return {"survivors": survivors, "n_survivors": max_k,
            "threshold": (thresh if max_k > 0 else None), "alpha": alpha}


def prob_at_least_one_fp(m: int, alpha: float = 0.05) -> float:
    """m개 독립검정에서 최소 1개 거짓양성 확률 = 1-(1-alpha)^m (직관용)."""
    return 1.0 - (1.0 - alpha) ** m
