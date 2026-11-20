"""gta6-trophy-rarity-forecast-01: trend-aware forecast in Python 3.13 (stdlib only).

Improved over the house persistence baseline (starter/main.py):

  1. Fits, per trophy, an OLS line of logit(rate) vs ln(1 + hours_since_T0)
     over the case's last 24 h of reads (same window as the house curve
     baseline).  With fewer than 3 valid reads it falls back to persistence.
  2. Reads that line at the target instant to get a trend-informed median.
  3. Spreads the five quantiles with a sigma that combines the random-walk
     term (sigma * sqrt(days)) with the fit's residual scale, so a trophy
     whose recent rates wobble gets a wider band than one that is steady.

The forecast is deterministic: same input always produces the same output
(PYTHONHASHSEED=0, no randomness, sorted file walk).

Invocation outside the grader's container:
    mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first so a shipped
# model.py (if any) can be imported beside this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

# Quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]

# Standard-normal quantiles at each level.
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Random-walk spread: logit units per sqrt(day).
SIGMA = 0.5

# Hours from a fixed reference instant to the first possible read in the
# house's recording.  ln(1 + hours_since_T0) is the x-axis of the trend fit.
# Chosen as the midnight before launch night so every real read has hours>0.
_T0_UNIX = 1763520000.0  # 2026-11-19T00:00:00Z


def clamp(x: float) -> float:
    """Clamp a percentage to the page's printable range [0.01, 99.99]."""
    return min(99.99, max(0.01, x))


def logit(pct: float) -> float:
    """Logit of a percentage (already clamped)."""
    return math.log(clamp(pct) / (100.0 - clamp(pct)))


def inv_logit(lg: float) -> float:
    """Inverse logit: logit -> percentage."""
    return 100.0 / (1.0 + math.exp(-lg))


def round4(x: float) -> float | int:
    """Round to 4 decimals, half-up — same rounding JavaScript's
    Math.round(x * 10000) / 10000 gives.  A whole number returns as int so
    json.dumps writes `100` where JS writes `100` (not `100.0`)."""
    scaled = x * 10000.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000.0
    return int(value) if value.is_integer() else value


def _to_hours(case_at: str) -> float:
    """Hours from _T0_UNIX to an ISO-8601 UTC instant.

    Handles both ``YYYY-MM-DDTHH:MM:SSZ`` and ``YYYY-MM-DDTHH:MM:SS.fffZ``.
    """
    import datetime

    # Strip trailing 'Z' and any fractional seconds.
    ts = case_at.rstrip("Z")
    # Split off fractional seconds if present.
    if "." in ts:
        base, frac = ts.split(".", 1)
        # Keep only HH:MM:SS.fff — discard any sub-parse beyond seconds.
        ts = f"{base}.{frac[:3]}"
    else:
        ts = ts

    date_part, time_part = ts.split("T")
    y, m, d = date_part.split("-")
    time_tokens = time_part.split(":")
    hh = int(time_tokens[0])
    mm = int(time_tokens[1])
    ss = float(time_tokens[2])  # may include fractional part
    dt = datetime.datetime(
        int(y), int(m), int(d), hh, mm, int(ss), int((ss % 1) * 1_000_000),
        tzinfo=datetime.timezone.utc,
    )
    return (dt.timestamp() - _T0_UNIX) / 3600.0


def fit_trend(case: dict, trophy_idx: int):
    """Fit OLS of logit(rate) on ln(1 + hours) over the case's last 24 h.

    Returns (slope, intercept, sigma_fit, used_n) or None when fewer than
    3 valid (non-null) rates exist in that window — the persistence fallback
    path.
    """
    history = case["history"]
    if not history:
        return None

    case_unix = _to_hours(case["at"])
    window_cutoff_h = case_unix - 24.0

    xs = []
    ys = []
    for read in history:
        if read["rates"][trophy_idx] is None:
            continue
        h = _to_hours(read["at"])
        if h < window_cutoff_h:
            continue
        xs.append(math.log(1.0 + max(h, 0.0)))
        ys.append(logit(read["rates"][trophy_idx]))

    n = len(xs)
    if n < 3:
        return None

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    ss_xx = sum((x - mean_x) ** 2 for x in xs)
    ss_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))

    if ss_xx < 1e-18:  # all x equal (shouldn't happen with real reads)
        return None

    slope = ss_xy / ss_xx
    intercept = mean_y - slope * mean_x

    # Residual scale (RMS of residuals = sqrt(MSE)).
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    sigma_fit = math.sqrt(ss_res / n) if n > 0 else 0.0

    return slope, intercept, sigma_fit, n


def forecast_case(case: dict, name: str) -> dict:
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    if not case["history"]:
        raise ValueError(f"{name} has no history")

    last = case["history"][-1]
    horizon_days = case["horizon_minutes"] / 1440.0

    # Random-walk spread in logit units at the target.
    sigma_rw = SIGMA * math.sqrt(horizon_days)

    target_hours = _to_hours(case["target"])

    rows = []
    for i, trophy in enumerate(case["trophies"]):
        rate_last = last["rates"][i]
        lg_last = logit(rate_last if rate_last is not None else 0.0)

        # --- Trend fit over last 24 h ---------------------------------------
        fit = fit_trend(case, i)

        if fit is None:
            # Fewer than 3 reads in the window (or all null): pure persistence.
            lg_median = lg_last
            sigma_fit = 0.0
        else:
            slope, intercept, sigma_fit, _n = fit
            lg_trend = intercept + slope * math.log(1.0 + max(target_hours, 0.0))
            # Blend: use the trend line as the median; when the slope is
            # negligible the line sits on the last rate anyway.
            lg_median = lg_trend

        # --- Spread: random-walk sigma, optionally widened by fit residual --
        # The fit residual captures trophy-specific noise the random-walk
        # term does not; taking max() keeps the spread at least as wide as
        # the baseline's, and strictly wider when the recent rates actually
        # vary around the line.
        sigma = max(sigma_rw, sigma_fit) if sigma_fit > 0.0 else sigma_rw

        # --- Five quantiles on the logit scale ------------------------------
        q = [round4(inv_logit(lg_median + z * sigma)) for z in Z]

        rows.append({"id": trophy["id"], "q": q})

    return {"trophies": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        out_path = OUTPUT_DIR / f"{path.stem}.out"
        out_path.write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
