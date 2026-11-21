import json
import os


def weighted_rate(series, weights):
    """Compute weighted average of rate series with given weights."""
    if not series or not weights:
        return 0.0
    n = len(series)
    w = weights[:n] if len(weights) >= n else weights + [0.0] * (n - len(weights))
    total_w = sum(w)
    if total_w <= 0:
        return series[-1] if series else 0.0
    weighted_sum = sum(series[i] * w[i] for i in range(n))
    return weighted_sum / total_w


def compute_quantiles(weighted_rate_val, levels):
    """Compute quantiles from weighted rate using spread formula."""
    q50 = weighted_rate_val
    # spread proportional to rate level, minimum 0.01
    spread = max(q50 * 0.10, 0.01)
    quantiles = []
    for level in levels:
        q = q50 + (level - 0.5) * 2 * spread
        # clamp to valid range [0, 100]
        q = max(0.0, min(100.0, q))
        quantiles.append(round(q, 4))
    # enforce non-decreasing: each quantile must be >= previous
    for i in range(1, len(quantiles)):
        if quantiles[i] < quantiles[i - 1]:
            quantiles[i] = quantiles[i - 1]
    return quantiles


def forecast_case(case):
    levels = case["levels"]
    history = case["history"]
    trophies = case["trophies"]
    n = len(trophies)
    
    # Build weighted history: more weight on recent entries
    # Use last 4 history entries with exponentially decaying weights
    recent = history[-4:] if len(history) >= 4 else history
    num_recent = len(recent)
    
    # Weight: newer = higher weight (exponential decay)
    # weights for [oldest, ..., newest] in recent window
    if num_recent == 0:
        weights = []
    elif num_recent == 1:
        weights = [1.0]
    else:
        # exponential: newest gets weight 2^(n-1), oldest gets 2^0
        weights = [2 ** (i - num_recent + 1) for i in range(num_recent)]
    
    out = []
    for i in range(n):
        # Extract rate series for this trophy across recent history
        series = [h["rates"][i] for h in recent]
        wr = weighted_rate(series, weights)
        q = compute_quantiles(wr, levels)
        out.append(q)
    return out


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "out")
    
    os.makedirs(output_dir, exist_ok=True)
    
    for fn in sorted(os.listdir(input_dir)):
        if not fn.endswith(".in"):
            continue
        path = os.path.join(input_dir, fn)
        with open(path) as f:
            case = json.load(f)
        
        pred = forecast_case(case)
        id_ = case["id"]
        out_path = os.path.join(output_dir, id_ + ".out")
        with open(out_path, "w") as f:
            json.dump(pred, f)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
