"""구조화 스펙 → SignalFn 코드 생성 — LLM 호출 1건.

runner.py 시그니처 (ohlc, feat, aux, params) -> {"entry": bool[], "eligible": int[]}
를 반드시 지키도록 few-shot(strategies.py 발췌)으로 강제한다. 생성된 코드는
문자열로만 반환 — 파일 저장은 호출측(run_paper_ingest.py) 책임."""
from __future__ import annotations

import json

from research.papers.llm_cli import call_claude

_FEW_SHOT = '''# 예시 — 기존 research/hypotheses/strategies.py의 실제 가설 하나:
def vwap_mean_reversion(ohlc, feat, aux, params):
    c, vwap, mso, atr = ohlc["close"], feat["vwap"], feat["mso"], feat["atr_abs"]
    dev_k = params.get("dev_k", 0.004)
    n = len(c); entry = [False] * n; elig = []
    for i in range(n):
        if not (mso[i] >= 30 and vwap[i] and atr[i]):
            continue
        elig.append(i)
        dev = (c[i] - vwap[i]) / vwap[i]
        if dev < -dev_k:
            entry[i] = True
    return {"entry": entry, "eligible": elig}
'''

_PROMPT_TEMPLATE = '''아래는 트레이딩 시그널 함수 작성 예시다:
{few_shot}

feat 딕셔너리 키: sids(세션ID), mso(장시작후경과분), vwap(세션VWAP), atr_abs(ATR절대값).
전부 ohlc["close"]와 같은 길이 리스트, 세션 시작 전이나 계산불가 구간은 None.

이제 아래 스펙을 구현하는 Python 함수를 작성하라. 반드시 이 형식만 출력(설명
없이 코드만, 마크다운 코드펜스도 없이):

NAME = "<영문 소문자 스네이크케이스 슬러그, 20자 이내>"
DESCRIPTION = "<한 줄 요약>"

def signal_fn(ohlc, feat, aux, params):
    ...
    return {{"entry": entry, "eligible": elig}}

제약: 롱온리(entry는 매수 진입 신호만), params는 튜닝 없이 고정값 사용(하드코딩
가능), 외부 네트워크/파일 접근 금지, import는 표준 라이브러리만.

스펙:
{spec_json}
'''


def generate_signal_code(spec: dict) -> str:
    prompt = _PROMPT_TEMPLATE.format(
        few_shot=_FEW_SHOT, spec_json=json.dumps(spec, ensure_ascii=False, indent=2),
    )
    return call_claude(prompt)
