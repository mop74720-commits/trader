"""Deterministic synthetic OHLCV feed and causal market features."""
from __future__ import annotations

import math
import random
import statistics
from datetime import datetime, timezone

SYMBOLS = {"BTC": 64000.0, "ETH": 3200.0, "SOL": 145.0}
BAR_SECONDS = 900


def make_bar(symbol: str, previous: float, tick: int, start: float, seed: int = 42) -> dict:
    rng = random.Random(f"{seed}:{symbol}:{tick}")
    phase = list(SYMBOLS).index(symbol)
    drift = 0.0011 * math.sin(tick / 38 + phase) + 0.00025
    change = drift + rng.gauss(0, 0.0022 + phase * 0.0005)
    close = previous * math.exp(change)
    spread = abs(rng.gauss(0, 0.0018)) + 0.0004
    return {
        "time": start + tick * BAR_SECONDS,
        "open": previous,
        "high": max(previous, close) * (1 + spread),
        "low": min(previous, close) * (1 - spread),
        "close": close,
        "volume": rng.uniform(300, 1600),
        "funding": 0.0001 * math.sin(tick / 24 + phase),
    }


def features(bars: list[dict]) -> dict:
    closes = [b["close"] for b in bars]
    last = closes[-1]
    returns = [math.log(b / a) for a, b in zip(closes[-97:-1], closes[-96:])]
    recent = bars[-24:]
    vwap = sum(b["close"] * b["volume"] for b in recent) / sum(b["volume"] for b in recent)
    sigma = statistics.pstdev(closes[-24:]) or last * 1e-6
    travel = sum(abs(b - a) for a, b in zip(closes[-25:-1], closes[-24:]))
    efficiency = abs(last - closes[-25]) / travel if travel else 0
    return {
        "price": last,
        "momentum": last / closes[-97] - 1,
        "fast_momentum": last / closes[-17] - 1,
        "volatility": statistics.pstdev(returns) * math.sqrt(96) if returns else 0,
        "vwap": vwap,
        "zscore": (last - vwap) / sigma,
        "breakout": last / max(b["high"] for b in bars[-25:-1]) - 1,
        "efficiency": efficiency,
        "funding": bars[-1]["funding"],
    }


def iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")
