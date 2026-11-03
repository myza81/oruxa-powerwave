"""Floating-point safety for PU bases and division; no electrical policy.

Use the established operation order for ordinary values. Exponent-separated
evaluation is needed only when that order loses an otherwise representable
answer. Subnormal results are valid; overflow and nonzero-to-zero underflow
are unavailable, never a fabricated zero or a configured gap.
"""

import math
import sys

import numpy as np

SQRT_3 = 1.7320508075688772


def positive_finite(value: float | None) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def scaled_base(value: float | None, scale: float) -> float | None:
    if not positive_finite(value):
        return None
    result = value * scale
    return result if positive_finite(result) else None


def _scaled_ratio(value: float, scale: float, denominator: float) -> float | None:
    """No intermediate value*scale or scale/denominator need be representable."""
    mv, ev = math.frexp(value)
    ms, es = math.frexp(scale)
    md, ed = math.frexp(denominator)
    try:
        result = math.ldexp((mv * ms) / md, ev + es - ed)
    except OverflowError:
        return None
    return result if math.isfinite(result) and (result != 0 or value == 0) else None


def derived_current_ka(rating_mva: float, nominal_ll_kv: float) -> float | None:
    if not positive_finite(rating_mva) or scaled_base(nominal_ll_kv, 1000.) is None:
        return None
    denominator = SQRT_3 * nominal_ll_kv
    result = rating_mva / denominator
    if not (math.isfinite(denominator) and denominator >= sys.float_info.min
            and math.isfinite(result) and result >= sys.float_info.min):
        result = _scaled_ratio(rating_mva, 1. / SQRT_3, nominal_ll_kv)
    if result is None or scaled_base(result, 1000.) is None:
        return None
    return result


def convert_scalar(value: float | None, scale: float, denominator: float) -> float | None:
    if value is None or not math.isfinite(value) or not positive_finite(denominator):
        return None
    value = float(value)
    result = (value * scale) / denominator
    if math.isfinite(result) and (result != 0 or value == 0):
        return result
    return _scaled_ratio(value, scale, denominator)


def convert_array(values: np.ndarray, scale: float, denominator: float) -> np.ndarray | None:
    if not positive_finite(denominator):
        return None
    # Keep the existing arithmetic and rounding for ordinary data. Only
    # exceptional finite samples need the vectorized exponent fallback.
    with np.errstate(over="ignore", under="ignore", invalid="ignore", divide="ignore"):
        result = (values.astype(np.float64) * scale) / denominator
        bad = np.isfinite(values) & (~np.isfinite(result) | ((result == 0) & (values != 0)))
        if np.any(bad):
            mantissa, exponent = np.frexp(values[bad])
            ms, es = math.frexp(scale)
            md, ed = math.frexp(denominator)
            fixed = np.ldexp((mantissa * ms) / md, exponent + es - ed)
            if np.any(~np.isfinite(fixed) | (fixed == 0)):
                return None
            result[bad] = fixed
    return result


def channel_values_representable(values: np.ndarray, scale: float, denominator: float) -> bool:
    """Two native reductions, never a second full waveform conversion.

    Positive division is monotonic in magnitude: checking the smallest
    nonzero and largest finite input proves all finite samples are usable.
    Original gaps and actual zeros do not block a channel. Whole-channel
    validation makes viewport/cursor/provenance readiness deterministic.
    """
    magnitudes = np.abs(np.asarray(values, dtype=np.float64))
    nonzero = np.isfinite(magnitudes) & (magnitudes != 0)
    minimum = float(np.min(magnitudes, where=nonzero, initial=np.inf))
    if not math.isfinite(minimum):
        return True
    maximum = float(np.max(magnitudes, where=nonzero, initial=0.))
    return (convert_scalar(minimum, scale, denominator) is not None
            and convert_scalar(maximum, scale, denominator) is not None)
