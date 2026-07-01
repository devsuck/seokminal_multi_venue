"""HMM regime detection using hmmlearn."""
import numpy as np
from hmmlearn import hmm


def detect_regime_hmm(returns: list[float], n_components: int = 2) -> dict:
    ret = np.array(returns).reshape(-1, 1)

    model = hmm.GaussianHMM(
        n_components=n_components,
        covariance_type="full",
        n_iter=200,
        random_state=42,
    )
    model.fit(ret)
    hidden_states = model.predict(ret)

    # Sort states by mean return (ascending = bear first, bull last)
    state_means = [model.means_[i, 0] for i in range(n_components)]
    state_order = np.argsort(state_means)  # low mean → high mean

    regime_names: dict[int, str] = {}
    mean_vol = float(
        np.mean([np.sqrt(model.covars_[s, 0, 0]) for s in range(n_components)])
    )
    for rank, state in enumerate(state_order):
        vol = float(np.sqrt(model.covars_[state, 0, 0]))
        if rank == len(state_order) - 1:
            regime_names[state] = "bull_low_vol" if vol < mean_vol else "bull_high_vol"
        else:
            regime_names[state] = "bear_high_vol" if vol > mean_vol else "bear_low_vol"

    current_regime = regime_names[int(hidden_states[-1])]

    # Regime distribution
    unique, counts = np.unique(hidden_states, return_counts=True)
    dist: dict[str, float] = {}
    for s, c in zip(unique, counts):
        dist[regime_names[int(s)]] = round(float(c / len(hidden_states)), 4)

    # Transition matrix
    trans_matrix = model.transmat_.tolist()

    return {
        "method": "hmm",
        "current_regime": current_regime,
        "n_components": n_components,
        "regime_distribution": dist,
        "transition_matrix": trans_matrix,
        "state_means": [round(float(model.means_[i, 0]), 6) for i in range(n_components)],
        "state_vols": [
            round(float(np.sqrt(model.covars_[i, 0, 0])), 6) for i in range(n_components)
        ],
    }
