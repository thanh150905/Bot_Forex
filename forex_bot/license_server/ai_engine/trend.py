"""
Rule-based trend classifier with ML-ready boundaries.

The response shape is stable for the C++ bot. Later, the score calculation can
be replaced with LightGBM/scikit-learn while keeping the API contract intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from ai_engine.indicators import Candle, atr, bollinger_position, ema, rsi

Trend = Literal["trending_up", "trending_down", "ranging"]
Signal = Literal["BUY", "SELL", "HOLD"]


@dataclass(frozen=True)
class TrendResult:
    trend: Trend
    signal: Signal
    confidence: float
    reason: str
    entry_price: float
    sl_price: float | None
    tp_price: float | None
    indicators: dict[str, float]


def classify_trend(candles: Sequence[Candle]) -> TrendResult:
    if len(candles) < 60:
        raise ValueError("Need at least 60 candles for trend classification")

    closes = [candle.close for candle in candles]
    last = candles[-1]

    ema_fast = ema(closes, 8)
    ema_mid = ema(closes, 21)
    ema_slow = ema(closes, 50)
    current_atr = atr(candles, 14)
    current_rsi = rsi(closes, 14)
    bb_pos = bollinger_position(closes, 20)
    price = last.close

    min_atr = price * 0.00025
    volatility_ok = current_atr >= min_atr
    up_stack = ema_fast > ema_mid > ema_slow
    down_stack = ema_fast < ema_mid < ema_slow
    price_above_trend = price > ema_slow
    price_below_trend = price < ema_slow

    up_score = 0
    down_score = 0

    if up_stack:
        up_score += 35
    if down_stack:
        down_score += 35
    if price_above_trend:
        up_score += 20
    if price_below_trend:
        down_score += 20
    if 52 <= current_rsi <= 72:
        up_score += 20
    if 28 <= current_rsi <= 48:
        down_score += 20
    if bb_pos > 0.58:
        up_score += 10
    if bb_pos < 0.42:
        down_score += 10
    if volatility_ok:
        up_score += 15
        down_score += 15

    if up_score >= 70 and up_score >= down_score + 15:
        trend: Trend = "trending_up"
        signal: Signal = "BUY"
        confidence = min(up_score / 100.0, 0.95)
        sl_price = price - current_atr * 1.5 if current_atr else None
        tp_price = price + current_atr * 2.0 if current_atr else None
        reason = "EMA stack bullish, price above EMA50, momentum supports BUY"
        edge_score = up_score - down_score
    elif down_score >= 70 and down_score >= up_score + 15:
        trend = "trending_down"
        signal = "SELL"
        confidence = min(down_score / 100.0, 0.95)
        sl_price = price + current_atr * 1.5 if current_atr else None
        tp_price = price - current_atr * 2.0 if current_atr else None
        reason = "EMA stack bearish, price below EMA50, momentum supports SELL"
        edge_score = down_score - up_score
    else:
        trend = "ranging"
        signal = "HOLD"
        confidence = max(0.35, 1.0 - abs(up_score - down_score) / 100.0)
        sl_price = None
        tp_price = None
        reason = "No clean directional edge or volatility is too low"
        edge_score = abs(up_score - down_score)

    estimated_probability = min(0.90, max(0.40, 0.47 + edge_score / 150.0))
    risk_score = min(1.0, max(0.0, (0.24 if not volatility_ok else 0.0) + max(0.0, 0.58 - edge_score / 100.0)))

    return TrendResult(
        trend=trend,
        signal=signal,
        confidence=round(confidence, 4),
        reason=reason,
        entry_price=price,
        sl_price=round(sl_price, 5) if sl_price is not None else None,
        tp_price=round(tp_price, 5) if tp_price is not None else None,
        indicators={
            "ema_8": round(ema_fast, 5),
            "ema_21": round(ema_mid, 5),
            "ema_50": round(ema_slow, 5),
            "atr_14": round(current_atr, 5),
            "rsi_14": round(current_rsi, 2),
            "bollinger_position": round(bb_pos, 4),
            "up_score": float(up_score),
            "down_score": float(down_score),
            "edge_score": float(edge_score),
            "estimated_probability": round(estimated_probability, 4),
            "risk_score": round(risk_score, 4),
        },
    )
