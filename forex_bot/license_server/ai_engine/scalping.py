"""
Fast rule-based scalping classifier for M1/M5 execution.

This is intentionally lightweight: it looks for short EMA alignment, fresh
momentum and enough ATR room to pay spread. Risk control still lives in the MT5
client where live spread, open positions and account execution are known.
"""

from __future__ import annotations

import os
from typing import Sequence

from ai_engine.indicators import Candle, atr, bollinger_position, ema, rsi
from ai_engine.trend import Signal, Trend, TrendResult


def classify_scalping(candles: Sequence[Candle]) -> TrendResult:
    if len(candles) < 40:
        raise ValueError("Need at least 40 candles for scalping classification")

    closes = [candle.close for candle in candles]
    last = candles[-1]
    previous = candles[-2]
    recent = candles[-12:-1]

    ema_fast = ema(closes, 5)
    ema_mid = ema(closes, 13)
    ema_slow = ema(closes, 34)
    current_atr = atr(candles, 14)
    current_rsi = rsi(closes, 7)
    bb_pos = bollinger_position(closes, 20)
    price = last.close
    candle_range = max(last.high - last.low, 0.0)
    body = last.close - last.open
    previous_body = previous.close - previous.open
    body_ratio = abs(body) / candle_range if candle_range else 0.0
    upper_wick = last.high - max(last.open, last.close)
    lower_wick = min(last.open, last.close) - last.low
    recent_high = max(candle.high for candle in recent)
    recent_low = min(candle.low for candle in recent)
    recent_volumes = [float(candle.volume or 0.0) for candle in recent]
    avg_volume = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 0.0
    volume_spike = bool(last.volume and avg_volume and float(last.volume) >= avg_volume * 1.15)
    ema_slope = ema_fast - ema(closes[:-3], 5)

    min_atr = price * 0.00008
    max_atr = price * 0.0018
    volatility_ok = current_atr >= min_atr
    volatility_extreme = current_atr > max_atr
    bullish_stack = ema_fast > ema_mid > ema_slow
    bearish_stack = ema_fast < ema_mid < ema_slow
    bullish_impulse = body > 0 and previous_body >= 0 and price > ema_fast
    bearish_impulse = body < 0 and previous_body <= 0 and price < ema_fast
    # M1 scalp needs to react before the candle becomes too obvious. 0.25 keeps
    # weak/doji candles out, while avoiding missed entries when spread is acceptable.
    body_is_useful = body_ratio >= 0.25
    bullish_breakout = price > recent_high and body > 0
    bearish_breakout = price < recent_low and body < 0
    bullish_rejection = lower_wick > abs(body) * 0.75 and price > ema_fast and body >= 0
    bearish_rejection = upper_wick > abs(body) * 0.75 and price < ema_fast and body <= 0
    bullish_slope = ema_slope > 0
    bearish_slope = ema_slope < 0

    buy_score = 0
    sell_score = 0

    if bullish_stack:
        buy_score += 30
    if bearish_stack:
        sell_score += 30
    if bullish_impulse:
        buy_score += 25
    if bearish_impulse:
        sell_score += 25
    if bullish_breakout:
        buy_score += 18
    if bearish_breakout:
        sell_score += 18
    if bullish_rejection:
        buy_score += 12
    if bearish_rejection:
        sell_score += 12
    if bullish_slope:
        buy_score += 8
    if bearish_slope:
        sell_score += 8
    if volume_spike:
        buy_score += 6 if body > 0 else 0
        sell_score += 6 if body < 0 else 0
    if 50 <= current_rsi <= 68:
        buy_score += 20
    if 32 <= current_rsi <= 50:
        sell_score += 20
    if 0.52 <= bb_pos <= 0.88:
        buy_score += 10
    if 0.12 <= bb_pos <= 0.48:
        sell_score += 10
    if volatility_ok and body_is_useful and not volatility_extreme:
        buy_score += 15
        sell_score += 15
    if volatility_extreme:
        buy_score -= 12
        sell_score -= 12

    score_threshold = float(os.getenv("SCALP_SCORE_THRESHOLD", "52"))
    min_score_gap = float(os.getenv("SCALP_MIN_SCORE_GAP", "10"))

    if buy_score >= score_threshold and buy_score >= sell_score + min_score_gap:
        trend: Trend = "trending_up"
        signal: Signal = "BUY"
        confidence = min(max(buy_score / 100.0, 0.55 + (buy_score - score_threshold) / 100.0), 0.94)
        sl_price = price - current_atr * 0.95 if current_atr else None
        tp_price = price + current_atr * 1.20 if current_atr else None
        reason = "M1 Scalp BUY: EMA alignment, impulse/breakout/rejection and momentum agree"
        edge_score = buy_score - sell_score
    elif sell_score >= score_threshold and sell_score >= buy_score + min_score_gap:
        trend = "trending_down"
        signal = "SELL"
        confidence = min(max(sell_score / 100.0, 0.55 + (sell_score - score_threshold) / 100.0), 0.94)
        sl_price = price + current_atr * 0.95 if current_atr else None
        tp_price = price - current_atr * 1.20 if current_atr else None
        reason = "M1 Scalp SELL: EMA alignment, impulse/breakout/rejection and momentum agree"
        edge_score = sell_score - buy_score
    else:
        trend = "ranging"
        signal = "HOLD"
        confidence = max(0.35, 1.0 - abs(buy_score - sell_score) / 100.0)
        sl_price = None
        tp_price = None
        reason = "No clean M1 scalp edge, weak candle body, or ATR is outside the tradable zone"
        edge_score = abs(buy_score - sell_score)

    estimated_probability = min(0.90, max(0.40, 0.45 + edge_score / 150.0))
    risk_score = min(
        1.0,
        max(
            0.0,
            (0.24 if not volatility_ok else 0.0)
            + (0.20 if volatility_extreme else 0.0)
            + (0.18 if not body_is_useful else 0.0)
            + max(0.0, 0.62 - edge_score / 100.0),
        ),
    )

    return TrendResult(
        trend=trend,
        signal=signal,
        confidence=round(confidence, 4),
        reason=reason,
        entry_price=price,
        sl_price=round(sl_price, 5) if sl_price is not None else None,
        tp_price=round(tp_price, 5) if tp_price is not None else None,
        indicators={
            "ema_5": round(ema_fast, 5),
            "ema_13": round(ema_mid, 5),
            "ema_34": round(ema_slow, 5),
            "atr_14": round(current_atr, 5),
            "rsi_7": round(current_rsi, 2),
            "bollinger_position": round(bb_pos, 4),
            "body_ratio": round(body_ratio, 4),
            "ema_5_slope": round(ema_slope, 5),
            "recent_high": round(recent_high, 5),
            "recent_low": round(recent_low, 5),
            "volume_spike": 1.0 if volume_spike else 0.0,
            "volatility_extreme": 1.0 if volatility_extreme else 0.0,
            "buy_score": float(buy_score),
            "sell_score": float(sell_score),
            "edge_score": float(edge_score),
            "estimated_probability": round(estimated_probability, 4),
            "risk_score": round(risk_score, 4),
        },
    )
