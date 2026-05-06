"""
Lightweight technical indicators used by the AI trend engine.

This module intentionally avoids heavy dependencies so the first engine can run
inside the existing FastAPI service. A trained ML model can be plugged in later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    time: str | None = None


def ema(values: Sequence[float], period: int) -> float:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        return 0.0

    k = 2.0 / (period + 1.0)
    current = sum(values[:period]) / period
    for price in values[period:]:
        current = price * k + current * (1.0 - k)
    return current


def rsi(values: Sequence[float], period: int = 14) -> float:
    if len(values) < period + 1:
        return 50.0

    gains = 0.0
    losses = 0.0
    window = values[-(period + 1):]

    for prev, curr in zip(window, window[1:]):
        delta = curr - prev
        if delta >= 0:
            gains += delta
        else:
            losses += abs(delta)

    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0

    true_ranges: list[float] = []
    for idx in range(len(candles) - period, len(candles)):
        current = candles[idx]
        previous = candles[idx - 1]
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )

    return sum(true_ranges) / period


def bollinger_position(values: Sequence[float], period: int = 20, std_factor: float = 2.0) -> float:
    """
    Return close position inside Bollinger band: 0 near lower band, 1 near upper.
    Values can go below 0 or above 1 during breakouts.
    """
    if len(values) < period:
        return 0.5

    window = values[-period:]
    mean = sum(window) / period
    variance = sum((value - mean) ** 2 for value in window) / period
    std = variance ** 0.5
    upper = mean + std_factor * std
    lower = mean - std_factor * std
    band_width = upper - lower
    if band_width == 0:
        return 0.5
    return (values[-1] - lower) / band_width

