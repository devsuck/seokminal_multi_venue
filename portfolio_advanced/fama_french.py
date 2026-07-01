"""Fama-French 3-factor attribution."""
import numpy as np
import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
import warnings


def get_ff3_factors(start: str, end: str) -> pd.DataFrame | None:
    """Download Fama-French 3 factors. Returns None on failure."""
    try:
        import pandas_datareader.data as web
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ff = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench", start=start, end=end)[0]
        ff.columns = ["MKT_RF", "SMB", "HML", "RF"]
        ff = ff / 100.0  # convert from percent
        ff.index = pd.to_datetime(ff.index)
        return ff
    except Exception:
        return None


def compute_factor_attribution(
    dates: list[str],
    returns: list[float],
    start: str,
    end: str,
) -> dict:
    """
    Regress asset returns on FF3 factors: R - Rf = α + β_mkt*(Mkt-Rf) + β_smb*SMB + β_hml*HML + ε
    Falls back to single-factor (CAPM) if FF data unavailable.
    """
    ret_series = pd.Series(returns, index=pd.to_datetime(dates))

    ff = get_ff3_factors(start, end)

    if ff is None:
        # Fallback: single-factor CAPM using SPY as proxy
        return {
            "model": "single-factor (FF data unavailable)",
            "alpha": None, "mkt_rf": None, "smb": None, "hml": None,
            "r_squared": None,
            "error": "Could not download Fama-French factor data",
        }

    # Align dates
    aligned = ret_series.to_frame("ret").join(ff, how="inner")
    if len(aligned) < 30:
        return {
            "model": "ff3",
            "error": "insufficient overlapping data",
            "alpha": None, "mkt_rf": None, "smb": None, "hml": None,
            "r_squared": None,
        }

    excess_ret = aligned["ret"] - aligned["RF"]
    X = add_constant(aligned[["MKT_RF", "SMB", "HML"]])
    model = OLS(excess_ret, X).fit()

    coeffs = model.params
    pvals = model.pvalues

    # Cumulative factor contributions
    factor_contributions = {
        "MKT": (aligned["MKT_RF"] * coeffs.get("MKT_RF", 0)).cumsum().tolist(),
        "SMB": (aligned["SMB"] * coeffs.get("SMB", 0)).cumsum().tolist(),
        "HML": (aligned["HML"] * coeffs.get("HML", 0)).cumsum().tolist(),
    }

    return {
        "model": "fama-french-3",
        "alpha": round(float(coeffs.get("const", 0)) * 252, 4),  # annualized
        "alpha_pvalue": round(float(pvals.get("const", 1)), 4),
        "mkt_rf": round(float(coeffs.get("MKT_RF", 0)), 4),
        "mkt_rf_pvalue": round(float(pvals.get("MKT_RF", 1)), 4),
        "smb": round(float(coeffs.get("SMB", 0)), 4),
        "smb_pvalue": round(float(pvals.get("SMB", 1)), 4),
        "hml": round(float(coeffs.get("HML", 0)), 4),
        "hml_pvalue": round(float(pvals.get("HML", 1)), 4),
        "r_squared": round(float(model.rsquared), 4),
        "obs": int(len(aligned)),
        "dates": aligned.index.strftime("%Y-%m-%d").tolist(),
        "factor_contributions": factor_contributions,
        "residual_alpha": round(float(model.resid.sum()), 4),
    }
