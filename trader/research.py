"""Walk-forward-style research: train selection, purged holdout, no automatic activation."""
from __future__ import annotations

import math
import statistics


def correlation(x: list[float], y: list[float]) -> float:
    if len(x) < 3 or not statistics.pstdev(x) or not statistics.pstdev(y):
        return 0.0
    mx, my = statistics.mean(x), statistics.mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        for index in ordered[start:end]:
            result[index] = (start + end - 1) / 2
        start = end
    return result


def evaluate(bars: list[dict], window: int, start: int, end: int, horizon: int = 4) -> dict:
    prices = [b["close"] for b in bars]
    indices = list(range(max(window, start), min(end, len(prices) - horizon)))
    scores = [prices[i] / prices[i - window] - 1 for i in indices]
    future = [prices[i + horizon] / prices[i] - 1 for i in indices]
    # Non-overlapping, long-only trades; 6 bps fees + 5 bps slippage on each side.
    samples = [prices[i + horizon] / prices[i] * (1 - 0.0005) * (1 - 0.0006) / ((1 + 0.0005) * (1 + 0.0006)) - 1
               for i in indices[::horizon] if prices[i] > prices[i - window]]
    return {
        "ic": correlation(scores, future),
        "rank_ic": correlation(ranks(scores), ranks(future)),
        "samples": len(indices),
        "trades": len(samples),
        "net_mean_return": statistics.mean(samples) if samples else 0.0,
    }


def research(bars: list[dict], tick: int) -> dict:
    split = int(len(bars) * 0.7)
    # Train labels must end before the holdout boundary (four-bar purge).
    choices = [(window, evaluate(bars, window, 32, split - 4)) for window in (8, 16, 32)]
    window, train = max(choices, key=lambda candidate: candidate[1]["ic"])
    test = evaluate(bars, window, split, len(bars) - 4)
    passed = test["samples"] >= 32 and test["trades"] >= 8 and test["ic"] > 0.03 and test["rank_ic"] > 0.03 and test["net_mean_return"] > 0
    return {
        "id": f"research-{tick}", "name": f"BTC Momentum ({window} bars)", "category": "momentum",
        "status": "Trial" if passed else "Rejected", "window": window, "tick": tick,
        "train": train, "validation": test, "split": split, "horizon": 4,
        "reason": "通过初筛，仅进入观察，不参与交易。" if passed else "样本外 IC、交易样本数或扣费收益未达到初筛门槛。",
        "dataset": "synthetic", "capital_enabled": False,
    }
