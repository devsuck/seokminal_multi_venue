"""CVaR (Expected Shortfall) computation."""
import numpy as np


def compute_cvar(returns: list[float], confidence_levels=(0.95, 0.99)) -> dict:
    arr = np.array(returns)
    result = {}
    for cl in confidence_levels:
        var = float(np.percentile(arr, (1 - cl) * 100))
        cvar = float(arr[arr <= var].mean()) if (arr <= var).any() else var
        key = str(int(cl * 100))
        result[f"var_{key}"] = var
        result[f"cvar_{key}"] = cvar
    return result
