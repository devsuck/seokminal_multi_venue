"""사이클 페이로드 스키마 드리프트 감시 — 조용한 파싱 실패를 시끄럽게 만든다.

이 리포에서 같은 사고가 세 번 났다:

  lv5_learner   `actions` vs `action`   → 자기학습 6주간 영구 사망
  agent_perf    `fill`    vs `fills`    → PnL 오기록(-94.64%)
  backtest.py   `net_pnl` vs `net`      → 실데이터 전략 전건 오탈락

셋 다 파서가 **예외 대신 빈 결과**를 냈다. 그래서 시스템은 "아직 거래가 없음"과
"파서가 죽었음"을 구분하지 못했고, 대시보드엔 정상적인 콜드스타트로 보였다.
`compute_lv5_params`가 6주 내내 출력하던 "[Lv5 학습중] 데이터 0/5건"이 정확히
그 위장막이었다.

여기서 세우는 불변식:

    **파싱 근거가 충분히 쌓였는데 추출 결과가 0건이면, 그건 콜드스타트가 아니라
    스키마 드리프트다.**

판별의 핵심은 "근거(evidence)" 정의다. 단순히 "사이클이 많은데 결과가 0"으로 잡으면
조용한 에이전트(임계값이 높아 안 사는 중)를 오탐한다. 오탐이 쌓이면 이 감시는
무시당하고, 그게 애초에 원래 버그가 6주를 버틴 방식이다. 그래서 호출자가 각자
"이게 있으면 반드시 파싱됐어야 한다"는 증거를 직접 세어 넘긴다.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any

_log = logging.getLogger(__name__)

# 이만큼의 근거가 쌓였는데도 추출 0건이면 드리프트로 본다.
# 낮게 잡으면 오탐, 높게 잡으면 발견이 늦다. 5는 "우연히 전부 파싱 실패"가
# 사실상 불가능해지는 최소선.
MIN_EVIDENCE = 5

# 헬스 엔드포인트가 읽어갈 수 있게 최근 경고를 들고 있는다(프로세스 수명 한정).
_RECENT: deque[dict[str, Any]] = deque(maxlen=50)


def detect_drift(
    context: str,
    *,
    n_evidence: int,
    n_extracted: int,
    hint: str,
    min_evidence: int = MIN_EVIDENCE,
) -> dict[str, Any] | None:
    """근거는 쌓였는데 추출이 0건이면 드리프트 리포트를 반환(아니면 None).

    Args:
        context: 어느 파서인지 (`"lv5_learner.extract_trade_outcomes"` 등).
        n_evidence: "이게 있으면 반드시 파싱됐어야 한다"는 입력의 개수.
            호출자가 자기 파서에 맞게 직접 센다 — 이 정의가 오탐을 가른다.
        n_extracted: 파서가 실제로 뽑아낸 개수.
        hint: 사람이 읽을 다음 확인 지점(의심 키 이름 등).
        min_evidence: 이 값 미만이면 판단을 유보한다.
    """
    if n_extracted > 0 or n_evidence < min_evidence:
        return None

    report = {
        "context": context,
        "n_evidence": n_evidence,
        "n_extracted": 0,
        "hint": hint,
    }
    _RECENT.append(report)
    _log.error(
        "[스키마 드리프트 의심] %s — 근거 %d건인데 추출 0건. %s",
        context, n_evidence, hint,
    )
    return report


def recent_drifts() -> list[dict[str, Any]]:
    """최근 감지된 드리프트 경고(최신순). 헬스 체크·대시보드용."""
    return list(reversed(_RECENT))


def clear() -> None:
    """테스트용 — 누적 경고 비우기."""
    _RECENT.clear()


# ── 호출자들이 공유하는 근거 카운터 ──────────────────────────────────────────

_CLOSE_MARKERS = ("close", "청산")


def count_close_actions(cycles: list[dict]) -> int:
    """청산을 알리는 액션 문자열을 들고 있는 사이클 수.

    현행 키 `action`(단수 문자열)과 과거 버그가 읽던 `actions`를 **둘 다** 본다.
    파서가 어느 쪽을 읽든 무관하게 "청산이 기록되긴 했다"를 세야 파서와 독립적인
    증거가 되기 때문이다. 청산이 기록됐는데 outcome이 0건이면 파싱이 깨진 것이다.
    """
    n = 0
    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue
        raw = cycle.get("action") or cycle.get("actions") or ""
        text = " ".join(raw) if isinstance(raw, list) else str(raw)
        low = text.lower()
        if any(marker in low for marker in _CLOSE_MARKERS):
            n += 1
    return n


def has_fill_payload(cycle: Any) -> bool:
    """이 사이클에 체결이 기록돼 있는가.

    `fills`(현행 리스트) 또는 `fill`(구버전 단수) 중 하나라도 실질 내용이 있으면 참.
    파서가 어떤 키를 읽든 무관하게 "체결이 기록되긴 했다"만 본다 — 그래야 파서와
    독립적인 증거가 된다. 핫패스에서 기존 순회에 얹어 쓰라고 사이클 단위로 둔다.
    """
    if not isinstance(cycle, dict):
        return False
    fills = cycle.get("fills")
    if isinstance(fills, list) and any(isinstance(f, dict) for f in fills):
        return True
    return isinstance(cycle.get("fill"), dict)


def count_fill_bearing(cycles: list[dict]) -> int:
    """`has_fill_payload`를 만족하는 사이클 수(별도 순회가 괜찮은 곳에서만)."""
    return sum(1 for cycle in cycles if has_fill_payload(cycle))
