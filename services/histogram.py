"""
Histogram bin calculation utilities that replicate MATLAB's automatic
binning behavior (Scott's rule) and fixed-bin edge calculations.
"""

import math
import numpy as np


def matlab_histogram_bins_fixed(X: np.ndarray, n_bins: int) -> np.ndarray:
    """
    Compute evenly-spaced histogram bin edges that closely match MATLAB's
    fixed-count histogram output.

    Args:
        X: 1-D array of data values.
        n_bins: Desired number of bins.

    Returns:
        Array of n_bins+1 bin edges.
    """
    if len(X) == 0:
        return np.linspace(0, 100, n_bins + 1)

    min_val = float(np.min(X))
    max_val = float(np.max(X))

    if min_val == max_val:
        return np.linspace(min_val - 1, max_val + 1, n_bins + 1)

    nice_min = math.floor(min_val * 20.0) / 20.0
    nice_max = math.ceil(max_val * 100.0) / 100.0

    if nice_min > min_val:
        nice_min -= 0.05
    if nice_max < max_val:
        nice_max += 0.01

    return np.linspace(nice_min, nice_max, n_bins + 1)


def matlab_auto_bins(X: np.ndarray) -> np.ndarray:
    """
    Compute automatic histogram bin edges using Scott's rule, matching
    MATLAB's default autobinning algorithm.

    Args:
        X: 1-D array of data values.

    Returns:
        Array of bin edges.
    """
    if len(X) == 0:
        return np.array([0.0, 100.0])

    min_val = float(np.min(X))
    max_val = float(np.max(X))

    if min_val == max_val:
        return np.array([min_val - 1.0, min_val + 1.0])

    std_val = float(np.std(X, ddof=1)) if len(X) > 1 else 1.0
    N = len(X)

    if std_val > 0 and N > 0:
        raw_w = 3.49 * std_val * (N ** (-1.0 / 3.0))
    else:
        raw_w = 1.0

    if raw_w <= 0:
        raw_w = 1.0

    power = 10 ** math.floor(math.log10(raw_w)) if raw_w > 0 else 1.0
    ratio = raw_w / power if power > 0 else 1.0

    if ratio < 1.5:
        step = 1.0 * power
    elif ratio < 2.5:
        step = 2.0 * power
    elif ratio < 4.0:
        step = 3.0 * power
    elif ratio < 7.5:
        step = 5.0 * power
    else:
        step = 10.0 * power

    nice_min = math.floor(min_val / step) * step
    edges = [nice_min]
    curr = nice_min
    while curr < max_val:
        curr += step
        edges.append(curr)

    return np.array(edges)
