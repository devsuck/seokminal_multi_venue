"""AI-powered strategy advisor using Claude."""
from __future__ import annotations

import json
import statistics

import anthropic

_VALID_STRATEGIES = {"ema_cross", "macd", "rsi"}
_MODEL = "claude-haiku-4-5-20251001"


def recommend_strategy(bars: list, instrument_id: str) -> dict:
    """
    Analyze bars and ask Claude to recommend a trading strategy.

    Returns dict with keys: strategy (str), params (dict), reasoning (str).
    Raises ValueError if bars is empty.
    """
    if not bars:
        raise ValueError("no bars provided")

    closes = [float(b.close) for b in bars]
    mean_price = statistics.mean(closes)
    price_std = statistics.stdev(closes) if len(closes) > 1 else 0.0
    overall_trend = (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0.0
    recent = closes[-20:] if len(closes) >= 20 else closes
    recent_mean = statistics.mean(recent)
    recent_vs_overall = (recent_mean - mean_price) / mean_price if mean_price > 0 else 0.0

    prompt = f"""You are a quantitative trading strategy advisor. Analyze this instrument and recommend the best strategy.

Instrument: {instrument_id}
Total bars analyzed: {len(bars)}
Price range: ${min(closes):.2f} - ${max(closes):.2f}
Mean price: ${mean_price:.2f}
Price volatility (std): ${price_std:.2f}
Overall trend (first to last): {overall_trend:+.2%}
Recent 20-bar mean vs overall mean: {recent_vs_overall:+.2%}

Available strategies:
- ema_cross: EMA crossover signals (params: fast, slow). Best for trending markets.
- macd: MACD momentum (params: fast, slow, signal_period). Good for momentum with trend confirmation.
- rsi: RSI mean-reversion (params: period, oversold, overbought). Best for ranging markets.

Respond with ONLY valid JSON in this exact format (no markdown, no code fences):
{{"strategy": "ema_cross"|"macd"|"rsi", "params": {{...}}, "reasoning": "2-3 sentence explanation"}}

For ema_cross: params = {{"fast": <int>, "slow": <int>}}
For macd: params = {{"fast": <int>, "slow": <int>, "signal_period": <int>}}
For rsi: params = {{"period": <int>, "oversold": <float>, "overbought": <float>}}"""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # Strip markdown code fences if model adds them despite instructions
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break

    result = json.loads(text)
    if result.get("strategy") not in _VALID_STRATEGIES:
        raise ValueError(f"Claude returned unknown strategy: {result.get('strategy')!r}")
    return result
