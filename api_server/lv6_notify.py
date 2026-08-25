"""Lv6 Telegram 알림 — 실전 집행·전략 변경·회로차단기 이벤트 알림.

지금은 Lv5 페이퍼 리뷰 완료 알림도 포함 (Lv6 준비 단계).
메인 스레드를 절대 블로킹하지 않음 (daemon 스레드 발송).
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import threading
import time
import urllib.error
import urllib.request

_log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_RETRIES = 3
_MAX_BACKOFF_S = 30.0


def _ssl_ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


# ── 기반 ─────────────────────────────────────────────────────────────────────

def _retry_after(err: urllib.error.HTTPError) -> float:
    """429 응답 바디의 retry_after(초) 파싱, 실패시 1초 기본값."""
    try:
        return float(json.loads(err.read()).get("parameters", {}).get("retry_after", 1))
    except Exception:
        return 1.0


def _send(text: str) -> None:
    """실제 HTTP 전송 (스레드 내부에서 호출). 429만 재시도 — 그 외 실패는 조용히 드롭."""
    # 모듈 로드 시점이 아닌 전송 시점에 env 읽기 (uvicorn reload 대응)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        _log.debug("[Notify] TELEGRAM_BOT_TOKEN / CHAT_ID 미설정 — 스킵")
        return
    url = _API.format(token=token)
    body = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }).encode()
    ctx = _ssl_ctx()
    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                if resp.status != 200:
                    _log.warning("[Notify] Telegram 응답 %s", resp.status)
                return
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < _MAX_RETRIES - 1:
                wait = min(_retry_after(e), _MAX_BACKOFF_S)
                _log.warning("[Notify] Telegram 429 — %.1fs 대기 후 재시도(%d/%d)",
                             wait, attempt + 1, _MAX_RETRIES)
                time.sleep(wait)
                continue
            _log.warning("[Notify] Telegram 전송 실패: %s", e)
            return
        except Exception as e:
            _log.warning("[Notify] Telegram 전송 실패: %s", e)
            return


def send(text: str) -> None:
    """비동기 전송 (daemon 스레드). 실패해도 메인 흐름에 영향 없음."""
    threading.Thread(target=_send, args=(text,), daemon=True).start()


# ── 이벤트별 포맷터 ───────────────────────────────────────────────────────────

def notify_lv5_review_done(
    agent_id: str,
    venue: str,
    cycle: int,
    threshold: float,
    position_pct: float,
    universe_add: list[str],
    universe_remove: list[str],
    strategy_note: str,
    dsl_summary: str = "",
) -> None:
    """Lv5 3-Phase 리뷰 완료 알림."""
    lines = [
        f"🤖 <b>[Lv5 에이전트] {agent_id}</b>",
        f"거래소: {venue} | 사이클: {cycle}",
        f"threshold: <b>{threshold:.0f}</b> | pos: <b>{position_pct:.0%}</b>",
    ]
    if universe_add:
        lines.append(f"➕ 추가: {', '.join(universe_add)}")
    if universe_remove:
        lines.append(f"➖ 제거: {', '.join(universe_remove)}")
    if strategy_note:
        lines.append(f"📝 {strategy_note}")
    if dsl_summary:
        lines.append(f"⚙️ DSL: {dsl_summary}")
    send("\n".join(lines))


def notify_live_trade(
    agent_id: str,
    venue: str,
    symbol: str,
    side: str,
    size: float,
    price: float,
    paper: bool = False,
) -> None:
    """실전(또는 페이퍼) 체결 알림."""
    tag = "📄 PAPER" if paper else "🔴 LIVE"
    emoji = "🟢" if side == "buy" else "🔴"
    usd = size * price
    send(
        f"{tag} <b>{agent_id}</b> [{venue}]\n"
        f"{emoji} {side.upper()} {symbol} × {size} @ {price:.4f}\n"
        f"≈ ${usd:,.0f}"
    )


def notify_circuit_breaker(agent_id: str, daily_loss_usd: float, limit_usd: float) -> None:
    """일일 손실 한도 초과 → 회로차단기 발동."""
    send(
        f"🚨 <b>회로차단기 발동</b> — {agent_id}\n"
        f"일일 손실 ${daily_loss_usd:,.0f} / 한도 ${limit_usd:,.0f}\n"
        f"오늘 추가 진입 차단됨"
    )


def notify_arm_check(agent_id: str, decision: str, reasons: list[str]) -> None:
    """Arm 기준 평가 결과."""
    emoji = {"GO": "✅", "WAIT": "⏳", "KILL": "❌"}.get(decision, "❓")
    send(
        f"{emoji} <b>Arm 평가: {decision}</b> — {agent_id}\n"
        + "\n".join(f"• {r}" for r in reasons)
    )


def notify_strategy_pivot(agent_id: str, what: str, detail: str) -> None:
    """전략 중대 변경 (유니버스 재편, DSL 대폭 수정 등)."""
    send(f"⚠️ <b>[전략 변경] {agent_id}</b>\n{what}\n{detail}")


def notify_daily_summary(
    agent_id: str,
    venue: str,
    n_trades: int,
    win_rate: float | None,
    pnl_usd: float | None,
    paper: bool = True,
) -> None:
    """일일 성과 요약."""
    tag = "📄" if paper else "💰"
    wr = f"{win_rate:.0%}" if win_rate is not None else "N/A"
    pnl_str = f"${pnl_usd:+,.1f}" if pnl_usd is not None else "N/A"
    send(
        f"{tag} <b>일일 리포트 — {agent_id}</b> [{venue}]\n"
        f"거래 {n_trades}건 | 승률 {wr} | P&L {pnl_str}"
    )
