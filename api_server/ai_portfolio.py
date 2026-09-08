"""AI 포트폴리오 구성 — registry 검증 전략(paper_active 이상) 대상, LLM이 비중+근거 제안.
**추천만, 실행 없음.** investment_os 불변식과 동일: is_advisory=True, is_decision=False,
requires_human_review=True. Research OS 무변경(읽기전용 소비).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os

from api_server.claude_cli import call_claude, claude_bin

_log = logging.getLogger(__name__)
_STATE_PATH = "jarvis/_state/ai_portfolio_recs.jsonl"
_MAX_WEIGHT = 0.4  # portfolio_construction.py의 _MAX_WEIGHT와 동일 캡


def _build_prompt(candidates: list[dict]) -> str:
    lines = [
        f"- {c['strategy_id']} | family={c.get('family', '?')} | "
        f"asset_class={c.get('asset_class', '?')} | evidence={c.get('evidence_grade', 'UNKNOWN')} | "
        f"status={c.get('status', '?')}"
        for c in candidates
    ]
    return (
        "다음은 페이퍼 검증을 통과했거나 진행 중인 트레이딩 전략 목록이다. 각 전략에 배분 비중을 "
        "추천하라.\n\n" + "\n".join(lines) +
        "\n\n규칙: 비중 합계는 정확히 1.0. 단일 전략 최대 비중 0.4. evidence_grade가 낮거나 "
        "UNKNOWN인 전략은 보수적으로. 아래 JSON 스키마로 한 줄만 출력(설명 텍스트 금지):\n"
        '{"weights": {"<strategy_id>": <float>, ...}, '
        '"per_strategy_note": {"<strategy_id>": "<한줄 근거>", ...}, '
        '"overall_rationale": "<전체 근거 한 문단>"}'
    )


def _parse_response(raw: str, candidate_ids: set[str]) -> dict | None:
    try:
        data = json.loads(raw.strip().splitlines()[-1]) if raw.strip() else None
    except (json.JSONDecodeError, IndexError):
        return None
    if not isinstance(data, dict) or "weights" not in data:
        return None
    if not isinstance(data["weights"], dict):
        return None
    try:
        weights = {k: float(v) for k, v in data["weights"].items() if k in candidate_ids}
    except (TypeError, ValueError):
        return None
    if not weights:
        return None
    total = sum(weights.values())
    if total <= 0:
        return None
    weights = {k: round(v / total, 4) for k, v in weights.items()}
    if max(weights.values()) > _MAX_WEIGHT + 1e-6:
        return None  # 캡 위반 — 폴백으로
    notes = data.get("per_strategy_note")
    if notes is not None and not isinstance(notes, dict):
        return None
    return {
        "weights": weights,
        "per_strategy_note": {k: v for k, v in (notes or {}).items()
                               if k in candidate_ids},
        "overall_rationale": str(data.get("overall_rationale", "")),
    }


def generate_ai_recommendation() -> dict:
    """주 1회(launchd) 호출 진입점. 반환 = jsonl에 append하는 레코드와 동일 dict."""
    from jarvis.investment_os import consume_research, construct_portfolio

    k = consume_research()
    candidates = [c for c in k.get("candidates", []) if c.get("evidence_grade") != "REJECTED"]
    ts = dt.datetime.now(dt.timezone.utc).isoformat()

    if not candidates:
        record = {"timestamp": ts, "weights": {}, "per_strategy_note": {}, "overall_rationale": "",
                   "fallback_used": False, "candidates_count": 0,
                   "is_advisory": True, "is_decision": False, "requires_human_review": True,
                   "note": "구성할 후보 없음 — 연구 지식 축적 필요."}
        _append(record)
        return record

    candidate_ids = {c["strategy_id"] for c in candidates}
    parsed = None
    claude = claude_bin()
    if claude:
        prompt = _build_prompt(candidates)
        for _ in range(2):  # 1회 재시도
            raw = call_claude(claude, prompt, timeout=120)
            parsed = _parse_response(raw, candidate_ids)
            if parsed:
                break
    else:
        _log.warning("[ai_portfolio] Claude CLI 없음 — 폴백")

    fallback_used = parsed is None
    if fallback_used:
        rule_based = construct_portfolio(candidates)
        parsed = {"weights": rule_based.get("weights", {}), "per_strategy_note": {},
                  "overall_rationale": "AI 응답 파싱 실패 또는 Claude CLI 없음 — 규칙 기반(evidence_weighted) 폴백."}

    record = {"timestamp": ts, "candidates_count": len(candidates), "fallback_used": fallback_used,
              **parsed,
              "is_advisory": True, "is_decision": False, "requires_human_review": True,
              "note": "AI Portfolio Builder(추천) — 실제 배분/집행 아님. 사람이 결정."}
    _append(record)
    return record


def _append(record: dict) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def latest_recommendation() -> dict | None:
    rows = _read_all()
    return rows[-1] if rows else None


def history(limit: int = 20) -> list[dict]:
    return _read_all()[-limit:][::-1]


def _read_all() -> list[dict]:
    if not os.path.exists(_STATE_PATH):
        return []
    with open(_STATE_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]
