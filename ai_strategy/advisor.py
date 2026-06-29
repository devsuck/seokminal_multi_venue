"""AI-powered strategy advisor using Groq."""
from __future__ import annotations

import json
import os
import statistics

from openai import OpenAI

_VALID_STRATEGIES = {"ema_cross", "macd", "rsi", "xgb"}
_MODEL = "llama-3.1-8b-instant"


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

    # Additional stats for richer prompt
    volatility_pct = price_std / mean_price if mean_price > 0 else 0.0
    # Simple trend strength: fraction of bars where close > previous close
    up_bars = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1])
    trend_strength = up_bars / (len(closes) - 1) if len(closes) > 1 else 0.5

    prompt = f"""You are a quantitative trading strategy advisor. Analyze this instrument and recommend the best strategy.

Instrument: {instrument_id}
Total bars analyzed: {len(bars)}
Price range: ${min(closes):.2f} - ${max(closes):.2f}
Mean price: ${mean_price:.2f}
Volatility (std/mean): {volatility_pct:.2%}
Overall trend (first to last): {overall_trend:+.2%}
Recent 20-bar mean vs overall mean: {recent_vs_overall:+.2%}
Up-bar ratio (trend strength 0=bearish, 1=bullish): {trend_strength:.2f}

Available strategies:
- ema_cross: EMA crossover. Best for clear trending markets (trend_strength < 0.35 or > 0.65).
- macd: MACD momentum with trend confirmation. Good for moderate trends with momentum.
- rsi: RSI mean-reversion. Best for ranging/choppy markets (trend_strength near 0.5, low volatility).
- xgb: XGBoost ML classifier trained on price features. Best when bars >= 100 and market regime is unclear or mixed. Learns non-linear patterns.

Respond with ONLY valid JSON in this exact format (no markdown, no code fences):
{{"strategy": "ema_cross"|"macd"|"rsi"|"xgb", "params": {{...}}, "reasoning": "2-3 sentence explanation"}}

For ema_cross: params = {{"fast": <int 5-20>, "slow": <int 20-50>}}
For macd: params = {{"fast": <int 8-15>, "slow": <int 20-30>, "signal_period": <int 7-12>}}
For rsi: params = {{"period": <int 10-20>, "oversold": <float 25-35>, "overbought": <float 65-75>}}
For xgb: params = {{"train_ratio": <float 0.6-0.8>, "n_estimators": <int 50-200>, "max_depth": <int 3-6>, "learning_rate": <float 0.05-0.2>}}"""

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ["GROQ_API_KEY"],
    )
    message = client.chat.completions.create(
        model=_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.choices[0].message.content.strip()
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
