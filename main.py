#!/usr/bin/env python3
"""
GTA VI Trophy Rarity Forecast — Week 1 Player Count Prediction
==============================================================

Predicts how many players earn each trophy in the first week after GTA VI
release.  Reads per-trophy rate histories from MAKEFUN_INPUT_DIR/*.in case
files and writes five-stratum quantile forecasts to MAKEFUN_OUTPUT_DIR/.

Model
-----
For every trophy we fit an Ordinary-Least-Squares line of **logit(rate)**
against **ln(1 + hours_since_T0)** over the case's most recent 24 h of
reads (the same window the house persistence baseline uses).  The fitted
line is evaluated at the target instant to obtain a trend-informed median
logit; the five output quantiles are then spread around that median using a
sigma that blends the random-walk term (sigma * sqrt(days)) with the fit's
residual standard error, so trophies whose recent rates wobble receive wider
bands than steady ones.

With fewer than three valid (non-null) reads in the window we fall back to
the plain persistence baseline (last observed rate carried forward).

The forecast is fully deterministic — PYTHONHASHSEED=0, no calls to random,
and all file walks are sorted — so the same input always yields the same
output.  Only the Python 3.13 standard library is used.

Invocation (outside the grader container)
    mkdir -p out
    MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

INPUT_DIR  = Path(os.environ.get("MAKEFUN_INPUT_DIR",    "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR",   "/output"))

# ---------------------------------------------------------------------------
# Constants shared by every case
# ---------------------------------------------------------------------------

# Quantile levels the contest scores, in the order each output row lists them.
LEVELS = [0.05, 0.25, 0.50, 0.75, 0.95]

# Corresponding standard-normal z-scores.
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Random-walk spread in logit units per sqrt(day).
SIGMA_RW = 0.5

# Reference instant for the x-axis of the trend fit.
# Chosen as the midnight before launch night so every real read has hours>0.
T0_UNIX = 1763520000.0   # 2026-11-19T00:00:00Z

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def clamp(x: float, lo: float = 0.01, hi: float = 99.99) -> float:
    """Clamp *x* to the printable percentage range [lo, hi]."""
    return min(hi, max(lo, x))


def logit(pct: float) -> float:
    """Logit of a percentage value (already clamped to (0, 100))."""
    p = clamp(pct) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit(lg: float) -> float:
    """Inverse logit — convert a logit back to a percentage."""
    return 100.0 / (1.0 + math.exp(-lg))


def round4(x: float) -> float:
    """Round to 4 decimal places (the contest's reported precision)."""
    return round(x, 4)


def _to_hours(ts: str) -> float:
    """Convert an ISO-8601 timestamp string to hours since T0_UNIX.

    Handles fractional-second formats such as
        2026-11-19T03:00:49.360Z
    by truncating to whole seconds before the conversion.
    """
    # Strip fractional seconds: keep only up to the seconds field.
    base = ts.rstrip("Z")
    if "." in base:
        base = base.split(".", 1)[0]
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(base)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt.timestamp() - T0_UNIX) / 3600.0
    except Exception:
        # Last resort: manual parse of YYYY-MM-DDTHH:MM:SS
        import re
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", base)
        if not m:
            raise ValueError(f"Cannot parse timestamp: {ts!r}")
        from datetime import datetime, timezone
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      int(m.group(4)), int(m.group(5)), int(m.group(6)),
                      tzinfo=timezone.utc)
        return (dt.timestamp() - T0_UNIX) / 3600.0


# ---------------------------------------------------------------------------
# OLS trend fit  (logit(rate) vs ln(1 + hours))
# ---------------------------------------------------------------------------

def fit_trend(case: Dict[str, Any], trophy_idx: int) -> Optional[Tuple[float, float, float]]:
    """Fit OLS of logit(rate) on ln(1+hours) over the last 24 h of reads.

    Returns (intercept, slope, residual_std) when >= 3 valid reads exist,
    or None when we must fall back to persistence.
    """
    history: List[Dict[str, Any]] = case.get("history", [])
    if not history:
        return None

    case_hours = _to_hours(case["at"])
    window_cutoff = case_hours - 24.0

    xs: List[float] = []
    ys: List[float] = []

    for read in history:
        rates = read.get("rates", [])
        if trophy_idx >= len(rates):
            continue
        rate = rates[trophy_idx]
        if rate is None:
            continue
        h = _to_hours(read["at"])
        if h < window_cutoff:
            continue
        x = math.log(1.0 + h)
        y = logit(rate)
        xs.append(x)
        ys.append(y)

    n = len(xs)
    if n < 3:
        return None

    x_bar = sum(xs) / n
    y_bar = sum(ys) / n

    ss_xx = sum((x - x_bar) ** 2 for x in xs)
    ss_xy = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys))

    if ss_xx < 1e-18:
        return (y_bar, 0.0, 0.0)

    slope = ss_xy / ss_xx
    intercept = y_bar - slope * x_bar

    # Residual standard error.
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    rss = sum(r ** 2 for r in residuals)
    residual_std = math.sqrt(rss / (n - 2)) if n > 2 else 0.0

    return (intercept, slope, residual_std)


# ---------------------------------------------------------------------------
# Per-case forecast
# ---------------------------------------------------------------------------

def forecast_case(case: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Produce the five-quantile forecast for every trophy in *case*."""

    if case.get("levels") != LEVELS:
        raise ValueError(
            f"{name}: expected levels {LEVELS}, got {case.get('levels')}"
        )

    history = case.get("history", [])
    if not history:
        raise ValueError(f"{name}: empty history")

    last = history[-1]
    rates = last.get("rates", [])
    n_trophies = len(rates)

    target_hours = _to_hours(case["target"])
    horizon_days  = case.get("horizon_minutes", 90) / 1440.0

    # Random-walk contribution to sigma at the forecast horizon.
    rw_sigma = SIGMA_RW * math.sqrt(horizon_days)

    out_rates: List[List[float]] = []

    for t in range(n_trophies):
        fit = fit_trend(case, t)

        if fit is None:
            # ----- Persistence fallback -----
            last_rate = rates[t]
            if last_rate is None:
                last_rate = 0.63   # very-conservative default
            median_rate = last_rate
            sigma = rw_sigma
        else:
            intercept, slope, res_std = fit
            # Median logit at the target instant.
            target_x = math.log(1.0 + target_hours)
            median_logit = intercept + slope * target_x
            median_rate  = clamp(inv_logit(median_logit))

            # Combine random-walk and fit-residual uncertainty.
            sigma = math.sqrt(rw_sigma ** 2 + res_std ** 2)

        # Build the five quantiles in logit space, then convert back.
        median_lg = logit(median_rate)
        quants_lg = [median_lg + z * sigma for z in Z]
        quants_pct = [clamp(inv_logit(lg)) for lg in quants_lg]
        out_rates.append([round4(p) for p in quants_pct])

    return {
        "id":     case.get("id", "unknown"),
        "rates":  out_rates,
    }


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def load_cases() -> List[Dict[str, Any]]:
    """Read every *.in case file from INPUT_DIR, sorted by name."""
    cases: List[Dict[str, Any]] = []
    for path in sorted(INPUT_DIR.glob("*.in")):
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    return cases


def write_outputs(results: List[Dict[str, Any]]) -> None:
    """Write one output file per case to OUTPUT_DIR."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for res in results:
        cid = res["id"]
        # Accept both integer IDs (p0, p1, …) and string IDs (p00, p01, …).
        if isinstance(cid, str) and cid.startswith("p") and cid[1:].isdigit():
            safe_name = f"{cid}.out"
        elif isinstance(cid, int):
            safe_name = f"p{cid}.out"
        else:
            safe_name = f"case_{cid}.out"
        out_path = OUTPUT_DIR / safe_name
        out_path.write_text(json.dumps(res["rates"]), encoding="utf-8")
        print(f"  wrote {out_path.name}  ({len(res['rates'])} trophies)", 
              file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"Reading cases from {INPUT_DIR}", file=sys.stderr)
    cases = load_cases()
    print(f"  {len(cases)} case(s) found", file=sys.stderr)

    results: List[Dict[str, Any]] = []
    for case in cases:
        name = case.get("id", case.get("at", "unnamed"))
        print(f"Forecasting case {name}  ({len(case.get('history', []))} history points, "
              f"{len(case.get('history', [{}])[0].get('rates', []))} trophies)",
              file=sys.stderr)
        res = forecast_case(case, str(name))
        results.append(res)

    write_outputs(results)
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
