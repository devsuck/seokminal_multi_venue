"""Historical stress test scenarios."""
import numpy as np

# Scenario: market drawdown (used to estimate portfolio impact via beta)
SCENARIOS = [
    {
        "name": "2008 Financial Crisis",
        "period": "Sep 2008 – Mar 2009",
        "market_return": -0.55,
        "vol_spike": 3.0,
        "description": "Lehman collapse, global credit freeze",
    },
    {
        "name": "COVID-19 Crash",
        "period": "Feb – Mar 2020",
        "market_return": -0.34,
        "vol_spike": 2.5,
        "description": "Pandemic panic, fastest bear market in history",
    },
    {
        "name": "Dot-com Bust",
        "period": "Mar 2000 – Oct 2002",
        "market_return": -0.49,
        "vol_spike": 1.8,
        "description": "Tech bubble collapse, 2.5-year bear market",
    },
    {
        "name": "2022 Rate Shock",
        "period": "Jan – Oct 2022",
        "market_return": -0.25,
        "vol_spike": 1.5,
        "description": "Fed aggressive tightening, 40-year inflation high",
    },
    {
        "name": "Flash Crash 2010",
        "period": "May 6, 2010",
        "market_return": -0.09,
        "vol_spike": 4.0,
        "description": "Intraday 9% crash, algorithmic trading cascade",
    },
    {
        "name": "Black Monday 1987",
        "period": "Oct 19, 1987",
        "market_return": -0.23,
        "vol_spike": 5.0,
        "description": "Single-day 22% drop, program trading panic",
    },
    {
        "name": "Mild Recession",
        "period": "Hypothetical",
        "market_return": -0.20,
        "vol_spike": 1.3,
        "description": "Moderate economic slowdown scenario",
    },
    {
        "name": "Severe Recession",
        "period": "Hypothetical",
        "market_return": -0.40,
        "vol_spike": 2.0,
        "description": "Deep recession, credit crunch scenario",
    },
]


def run_stress_test(returns: list[float], beta: float = 1.0) -> dict:
    ret = np.array(returns)
    current_vol = float(ret.std(ddof=1) * np.sqrt(252))
    current_var95 = float(np.percentile(ret, 5))  # 1-day VaR

    results = []
    for s in SCENARIOS:
        # Portfolio impact = beta * market_return (simplified CAPM)
        portfolio_impact = beta * s["market_return"]
        # VaR under stress = current VaR * vol_spike factor
        var_stressed = current_var95 * s["vol_spike"]
        # Estimated max loss from current position
        results.append({
            "name": s["name"],
            "period": s["period"],
            "description": s["description"],
            "market_return": round(s["market_return"], 4),
            "portfolio_impact": round(portfolio_impact, 4),
            "var_stressed": round(var_stressed, 4),
            "vol_spike_factor": s["vol_spike"],
        })

    return {
        "beta_used": round(beta, 4),
        "current_vol_ann": round(current_vol, 4),
        "current_var95_daily": round(current_var95, 4),
        "scenarios": results,
    }
