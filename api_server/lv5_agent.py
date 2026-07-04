"""Lv5 에이전틱 트레이딩 AI — 3-Phase Claude 비평 루프 (페이퍼 전용).

Phase 1 — Strategist : 실적+컨텍스트+메모리 분석 → 전략 제안 (산문)
Phase 2 — Critic     : 제안 공격 → 리스크·약점 지적 (산문)
Phase 3 — Merger     : 두 의견 통합 → 최종 JSON + DSL 생성

출력 JSON에 포함:
  threshold, position_pct, universe_add, universe_remove, pause_next,
  strategy_note, memory_insight, dsl (time_rules/vix_rules/symbol_overrides/…)

구조:
  - 10사이클마다 백그라운드 스레드에서 3번 Claude 호출 (~90-180초)
  - tick 블로킹 없음
  - 에이전트별 캐시에 결과 저장 → 다음 사이클들에 apply_cached_strategy로 적용
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time

from api_server.lv5_learner import extract_trade_outcomes
from api_server.lv5_memory import read_memory, append_memory
from api_server.lv5_context import get_cached_context, format_context_for_prompt
from api_server.lv5_dsl import set_cached_dsl

_log = logging.getLogger(__name__)

REVIEW_EVERY_N_CYCLES = 10

# ── In-process strategy cache ─────────────────────────────────────────────────
_CACHE: dict[str, dict] = {}
_CACHE_LOCK = threading.Lock()


def _get_cache(agent_id: str) -> dict:
    with _CACHE_LOCK:
        return dict(_CACHE.get(agent_id, {}))


def _set_cache(agent_id: str, update: dict) -> None:
    with _CACHE_LOCK:
        existing = _CACHE.get(agent_id, {})
        existing.update(update)
        _CACHE[agent_id] = existing


# ── Claude CLI helper ─────────────────────────────────────────────────────────

def _claude_bin() -> str | None:
    return shutil.which("claude") or (
        os.path.expanduser("~/.local/bin/claude")
        if os.path.exists(os.path.expanduser("~/.local/bin/claude")) else None
    )


def _call_claude(claude_path: str, prompt: str, timeout: int = 90) -> str:
    """Claude CLI 호출 → stdout 반환. 실패 시 빈 문자열."""
    try:
        proc = subprocess.run(
            [claude_path, "--dangerously-skip-permissions",
             "--permission-mode", "bypassPermissions", "--print", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        return proc.stdout.strip()
    except Exception as e:
        _log.warning("[Lv5] Claude 호출 실패: %s", e)
        return ""


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_strategist_prompt(
    agent_id: str, venue: str,
    base_threshold: float, base_position_pct: float,
    universe: list[str],
    outcomes: list[dict],
    context_str: str,
    memory: str,
) -> str:
    n = len(outcomes)
    wins = sum(1 for o in outcomes if o["win"])
    win_rate = wins / n if n else 0
    consecutive_sl = 0
    for o in reversed(outcomes):
        if o["sl"]:
            consecutive_sl += 1
        else:
            break

    sym_stats: dict[str, dict] = {}
    for o in outcomes:
        s = o["symbol"]
        if s not in sym_stats:
            sym_stats[s] = {"trades": 0, "wins": 0}
        sym_stats[s]["trades"] += 1
        if o["win"]:
            sym_stats[s]["wins"] += 1

    sym_lines = []
    for sym, st in sorted(sym_stats.items(), key=lambda x: -x[1]["trades"]):
        wr = st["wins"] / st["trades"]
        sym_lines.append(f"  {sym}: {st['trades']}건 승률 {wr:.0%}")
    sym_block = "\n".join(sym_lines) if sym_lines else "  (데이터 없음)"

    cached = _get_cache(agent_id)
    active_thr = cached.get("threshold", base_threshold)
    active_pct = cached.get("position_pct", base_position_pct)
    prev_note = cached.get("strategy_note", "없음")

    return f"""너는 자율 단타 트레이딩 전략가(Lv5 에이전틱 AI)다.
아래 데이터를 바탕으로 전략 개선 제안을 작성해라.

=== 에이전트 상태 ===
ID: {agent_id} | 거래소: {venue}
현재 threshold: {active_thr} | position_pct: {active_pct}
현재 유니버스: {', '.join(universe)}
이전 전략 메모: {prev_note}

=== 누적 메모리 (이전 리뷰들) ===
{memory}

=== 최근 {n}건 실적 (승률 {win_rate:.0%}) ===
종목별:
{sym_block}
연속 손절: {consecutive_sl}회

=== 시장 컨텍스트 ===
{context_str}

=== 지시 ===
1. 종목별 성과를 분석하라. 왜 잘되고 왜 안 되는지.
2. threshold와 position_pct를 어떻게 바꿔야 하는지 이유와 함께 제안하라.
3. 유니버스에서 뺄 종목, 추가할 종목을 제안하라 ({venue} 거래소 한정, 추가 최대 3개).
4. 시간대별/VIX별/어닝별 진입 조건 변화가 필요한지 분석하라.
5. 한 줄 핵심 인사이트 (다음 리뷰 때 기억할 것).

[출력] 산문으로 자유롭게 작성. JSON 금지. 한국어."""


def _build_critic_prompt(proposal: str, outcomes: list[dict], context_str: str) -> str:
    n = len(outcomes)
    wins = sum(1 for o in outcomes if o["win"])
    return f"""너는 까다로운 퀀트 리스크 매니저다. 아래 전략 제안을 비판하라.

=== 제안 내용 ===
{proposal[:2000]}

=== 실적 요약 ===
최근 {n}건, 승률 {wins/n:.0%}
{context_str[:500]}

=== 지시 ===
1. 제안의 약점과 위험을 지적하라.
2. 데이터가 부족하거나 근거가 약한 부분을 꼬집어라.
3. 특히 유니버스 변경이나 threshold 조정이 과도하면 반박하라.
4. 동의하는 부분이 있다면 짧게 인정해도 된다.

[출력] 산문 비판. JSON 금지. 한국어."""


def _build_merger_prompt(
    proposal: str, critique: str,
    base_threshold: float, base_position_pct: float,
    universe: list[str],
) -> str:
    return f"""너는 최종 의사결정자다. 전략가와 비평가의 의견을 통합해 최종 결정을 내려라.

=== 전략가 제안 ===
{proposal[:1500]}

=== 비평가 비판 ===
{critique[:800]}

=== 현재 기준값 ===
threshold: {base_threshold}, position_pct: {base_position_pct}
유니버스: {', '.join(universe)}

=== 지시 ===
두 의견을 균형있게 통합해서 아래 JSON을 생성해라.
- threshold: 숫자 (20~90, 변경 근거 없으면 현재값 유지)
- position_pct: 숫자 (0.03~0.25)
- pause_next: bool (연속 손절 심각할 때만 true)
- universe_add: 추가할 종목 리스트 (최대 3개, 빈 리스트 가능)
- universe_remove: 제거할 종목 리스트
- strategy_note: 한 줄 전략 요약 (한국어)
- memory_insight: 다음 리뷰 때 기억해야 할 핵심 발견 (한국어, 1~2문장)
- dsl: 아래 형식의 규칙 (없으면 빈 리스트)
  {{
    "time_rules": [{{"hour_start": 정수, "hour_end": 정수, "threshold_boost": 숫자, "position_scale": 숫자}}],
    "vix_rules": [{{"vix_above": 숫자, "threshold_boost": 숫자, "position_scale": 숫자}}],
    "symbol_overrides": [{{"symbol": "티커", "threshold": 숫자, "position_scale": 숫자, "skip": false}}],
    "earnings_buffer_days": 정수,
    "banned_symbols": []
  }}

[출력] JSON 한 줄만. 설명·마크다운 금지.
{{"threshold": {base_threshold}, "position_pct": {base_position_pct}, "pause_next": false, "universe_add": [], "universe_remove": [], "strategy_note": "요약", "memory_insight": "발견", "dsl": {{"time_rules": [], "vix_rules": [], "symbol_overrides": [], "earnings_buffer_days": 1, "banned_symbols": []}}}}"""


# ── JSON 파싱 ─────────────────────────────────────────────────────────────────

def _parse_strategy_json(raw: str, base_threshold: float, base_position_pct: float) -> dict | None:
    """Merger 출력에서 JSON 추출. 안전 범위 클램핑."""
    # 코드블록 제거
    raw = re.sub(r"```[a-z]*\n?", "", raw).strip()
    # 가장 큰 JSON 객체 추출
    matches = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}", raw, re.DOTALL)
    if not matches:
        matches = re.findall(r"\{.*\}", raw, re.DOTALL)
    if not matches:
        _log.warning("[Lv5] JSON 없음: %s", raw[:300])
        return None
    try:
        data = json.loads(matches[-1])
    except json.JSONDecodeError:
        # 마지막 완전한 JSON 찾기
        for m in reversed(matches):
            try:
                data = json.loads(m)
                break
            except Exception:
                continue
        else:
            _log.warning("[Lv5] JSON 파싱 실패: %s", raw[:300])
            return None

    data["threshold"] = float(max(20, min(90, data.get("threshold", base_threshold))))
    data["position_pct"] = float(max(0.03, min(0.25, data.get("position_pct", base_position_pct))))
    data["pause_next"] = bool(data.get("pause_next", False))
    data["universe_add"] = list(data.get("universe_add", []))[:3]
    data["universe_remove"] = list(data.get("universe_remove", []))
    data["strategy_note"] = str(data.get("strategy_note", ""))[:200]
    data["memory_insight"] = str(data.get("memory_insight", ""))[:300]
    return data


# ── 3-Phase 리뷰 실행 (백그라운드) ───────────────────────────────────────────

def _run_review(
    agent_id: str, venue: str,
    base_threshold: float, base_position_pct: float,
    current_universe: list[str], cycles: list[dict], cycle: int,
) -> None:
    _set_cache(agent_id, {"reviewing": True})
    try:
        claude = _claude_bin()
        if not claude:
            _log.warning("[Lv5] claude CLI 없음")
            return

        outcomes = extract_trade_outcomes(cycles)
        recent = outcomes[-30:]
        context = get_cached_context(venue, current_universe)
        ctx_str = format_context_for_prompt(context)
        memory = read_memory(agent_id)

        # ── Phase 1: Strategist ───────────────────────────────────────────────
        _log.info("[Lv5:%s] Phase 1 Strategist 시작", agent_id)
        p1 = _build_strategist_prompt(
            agent_id, venue, base_threshold, base_position_pct,
            current_universe, recent, ctx_str, memory,
        )
        proposal = _call_claude(claude, p1, timeout=90)
        if not proposal:
            _log.warning("[Lv5:%s] Strategist 응답 없음", agent_id)
            return
        _log.info("[Lv5:%s] Strategist 완료 (%d자)", agent_id, len(proposal))

        # ── Phase 2: Critic ───────────────────────────────────────────────────
        _log.info("[Lv5:%s] Phase 2 Critic 시작", agent_id)
        p2 = _build_critic_prompt(proposal, recent, ctx_str)
        critique = _call_claude(claude, p2, timeout=60)
        if not critique:
            critique = "(비평 없음)"
        _log.info("[Lv5:%s] Critic 완료 (%d자)", agent_id, len(critique))

        # ── Phase 3: Merger ───────────────────────────────────────────────────
        _log.info("[Lv5:%s] Phase 3 Merger 시작", agent_id)
        cached = _get_cache(agent_id)
        active_thr = cached.get("threshold", base_threshold)
        active_pct = cached.get("position_pct", base_position_pct)
        p3 = _build_merger_prompt(proposal, critique, active_thr, active_pct, current_universe)
        final_raw = _call_claude(claude, p3, timeout=60)
        if not final_raw:
            _log.warning("[Lv5:%s] Merger 응답 없음", agent_id)
            return
        _log.info("[Lv5:%s] Merger 완료 (%d자)", agent_id, len(final_raw))

        # ── 결과 적용 ─────────────────────────────────────────────────────────
        data = _parse_strategy_json(final_raw, base_threshold, base_position_pct)
        if not data:
            return

        # DSL 저장
        dsl = data.pop("dsl", {})
        if dsl:
            set_cached_dsl(agent_id, dsl)
            _log.info("[Lv5:%s] DSL 업데이트: %s", agent_id, str(dsl)[:200])

        # 메모리 기록
        insight = data.pop("memory_insight", "")
        if insight:
            append_memory(agent_id, f"[사이클 {cycle}] {insight}")

        data["last_review_cycle"] = cycle
        data["review_ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        _set_cache(agent_id, data)

        _log.info("[Lv5:%s] 전략 업데이트 완료 thr=%.0f pct=%.2f +%s -%s note=%s",
                  agent_id, data["threshold"], data["position_pct"],
                  data["universe_add"], data["universe_remove"],
                  data["strategy_note"][:60])

        # Telegram 알림
        try:
            from api_server.lv6_notify import notify_lv5_review_done
            dsl_summary = ""
            if dsl:
                parts = []
                if dsl.get("banned_symbols"):
                    parts.append(f"금지:{','.join(dsl['banned_symbols'])}")
                if dsl.get("vix_rules"):
                    parts.append(f"VIX룰:{len(dsl['vix_rules'])}개")
                if dsl.get("time_rules"):
                    parts.append(f"시간룰:{len(dsl['time_rules'])}개")
                dsl_summary = " | ".join(parts)
            notify_lv5_review_done(
                agent_id=agent_id, venue=venue, cycle=cycle,
                threshold=data["threshold"], position_pct=data["position_pct"],
                universe_add=data["universe_add"], universe_remove=data["universe_remove"],
                strategy_note=data["strategy_note"], dsl_summary=dsl_summary,
            )
        except Exception:
            pass  # 알림 실패는 조용히

    except Exception as e:
        _log.error("[Lv5:%s] 리뷰 실패: %s", agent_id, e, exc_info=True)
    finally:
        _set_cache(agent_id, {"reviewing": False})


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

def should_review(agent_id: str, current_cycle: int) -> bool:
    with _CACHE_LOCK:
        if _CACHE.get(agent_id, {}).get("reviewing", False):
            return False
        last = _CACHE.get(agent_id, {}).get("last_review_cycle", -999)
    return (current_cycle - last) >= REVIEW_EVERY_N_CYCLES


def trigger_review_if_needed(
    agent_id: str, venue: str,
    base_threshold: float, base_position_pct: float,
    current_universe: list[str], cycles: list[dict], cycle: int,
) -> None:
    """필요 시 백그라운드 3-Phase 리뷰 트리거. tick 블로킹 없음."""
    if not should_review(agent_id, cycle):
        return
    _set_cache(agent_id, {"last_review_cycle": cycle})
    t = threading.Thread(
        target=_run_review,
        args=(agent_id, venue, base_threshold, base_position_pct,
              current_universe, cycles, cycle),
        daemon=True,
    )
    t.start()
    _log.info("[Lv5:%s] 3-Phase 리뷰 스레드 시작 (사이클 %d)", agent_id, cycle)


def apply_cached_strategy(
    agent_id: str,
    threshold: float,
    position_pct: float,
    universe: list[str],
) -> tuple[float, float, list[str], bool, str]:
    """캐시된 에이전틱 전략 적용.

    Returns: (threshold, position_pct, universe, pause, note)
    """
    cached = _get_cache(agent_id)
    if not cached:
        return threshold, position_pct, universe, False, ""

    new_threshold = cached.get("threshold", threshold)
    new_position_pct = cached.get("position_pct", position_pct)
    pause = cached.get("pause_next", False)
    note = cached.get("strategy_note", "")
    reviewing = cached.get("reviewing", False)
    review_ts = cached.get("review_ts", "")

    new_universe = list(universe)
    for sym in cached.get("universe_remove", []):
        if sym in new_universe:
            new_universe.remove(sym)
    for sym in cached.get("universe_add", []):
        if sym not in new_universe:
            new_universe.append(sym)

    status = f"[Lv5 에이전트] {note}"
    if reviewing:
        status += " (3-Phase 리뷰 진행 중...)"
    elif review_ts:
        status += f" (리뷰: {review_ts})"

    return new_threshold, new_position_pct, new_universe, pause, status


def get_review_status(agent_id: str) -> dict:
    """프론트엔드용 상태 스냅샷."""
    cached = _get_cache(agent_id)
    return {
        "reviewing": cached.get("reviewing", False),
        "last_review_cycle": cached.get("last_review_cycle"),
        "review_ts": cached.get("review_ts"),
        "strategy_note": cached.get("strategy_note"),
        "threshold": cached.get("threshold"),
        "position_pct": cached.get("position_pct"),
        "universe_add": cached.get("universe_add", []),
        "universe_remove": cached.get("universe_remove", []),
        "pause_next": cached.get("pause_next", False),
    }
