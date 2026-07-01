"""Kelly Criterion position sizing."""
import numpy as np


def compute_kelly(returns: list[float]) -> dict:
    ret = np.array(returns)
    wins = ret[ret > 0]
    losses = ret[ret < 0]
    if len(wins) == 0 or len(losses) == 0:
        return {
            "kelly_full": 0.0,
            "kelly_half": 0.0,
            "kelly_quarter": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expected_value": 0.0,
        }
    win_rate = len(wins) / len(ret)
    avg_win = float(wins.mean())
    avg_loss = float(abs(losses.mean()))
    # Kelly = p - q/b  where b = avg_win / avg_loss
    b = avg_win / avg_loss
    p = win_rate
    q = 1 - p
    kelly = p - q / b
    ev = win_rate * avg_win - (1 - win_rate) * avg_loss
    return {
        "kelly_full": round(max(kelly, 0.0), 4),
        "kelly_half": round(max(kelly / 2, 0.0), 4),
        "kelly_quarter": round(max(kelly / 4, 0.0), 4),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "win_loss_ratio": round(b, 4),
        "expected_value": round(ev, 4),
    }
