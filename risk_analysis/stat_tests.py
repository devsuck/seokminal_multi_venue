"""Statistical tests: ADF, Ljung-Box, Jarque-Bera."""
import numpy as np
from scipy import stats as scipy_stats
from statsmodels.tsa.stattools import adfuller
from statsmodels.stats.diagnostic import acorr_ljungbox


def run_stat_tests(prices: list[float], returns: list[float]) -> dict:
    ret = np.array(returns)

    # ADF test for stationarity of returns
    adf_result = adfuller(ret, autolag="AIC")
    adf_crit = {str(k): round(v, 4) for k, v in adf_result[4].items()}

    # Ljung-Box test for autocorrelation (lag 10)
    lb = acorr_ljungbox(ret, lags=10, return_df=True)
    lb_stat = float(lb["lb_stat"].iloc[-1])
    lb_pval = float(lb["lb_pvalue"].iloc[-1])

    # Jarque-Bera normality test
    jb_stat, jb_pval = scipy_stats.jarque_bera(ret)
    skewness = float(scipy_stats.skew(ret))
    kurt = float(scipy_stats.kurtosis(ret))

    return {
        "adf": {
            "statistic": round(float(adf_result[0]), 4),
            "pvalue": round(float(adf_result[1]), 4),
            "critical_values": adf_crit,
            "is_stationary": float(adf_result[1]) < 0.05,
            "interpretation": "stationary" if float(adf_result[1]) < 0.05 else "non-stationary",
        },
        "ljung_box": {
            "statistic": round(lb_stat, 4),
            "pvalue": round(lb_pval, 4),
            "lags": 10,
            "is_autocorrelated": lb_pval < 0.05,
            "interpretation": "autocorrelation detected" if lb_pval < 0.05 else "no significant autocorrelation",
        },
        "jarque_bera": {
            "statistic": round(float(jb_stat), 4),
            "pvalue": round(float(jb_pval), 4),
            "is_normal": float(jb_pval) >= 0.05,
            "skewness": round(skewness, 4),
            "excess_kurtosis": round(kurt, 4),
            "interpretation": "normal" if float(jb_pval) >= 0.05 else "non-normal (fat tails)",
        },
    }
