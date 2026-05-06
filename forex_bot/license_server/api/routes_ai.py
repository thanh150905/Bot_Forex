"""
AI Engine routes: trend classification endpoint for C++/EA consumers.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from ai_engine.indicators import Candle
from ai_engine.news_filter import DEFAULT_NEWS_URL, evaluate_news_risk
from ai_engine.scalping import classify_scalping
from ai_engine.trend import classify_trend
from core.security import require_bot

router = APIRouter()


class CandlePayload(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    time: Optional[str] = None


class TrendRequest(BaseModel):
    bot_token: str
    license_key: str
    symbol: str = Field(..., examples=["EURUSD"])
    timeframe: str = Field("M15", examples=["M5", "M15", "H1"])
    strategy: str = Field("trend", examples=["trend", "scalping"])
    candles: list[CandlePayload] = Field(..., min_length=40)


class NewsRiskRequest(BaseModel):
    bot_token: str
    license_key: str
    symbol: str
    minutes_before: int = 45
    minutes_after: int = 20
    impacts: list[str] = Field(default_factory=lambda: ["High", "Holiday"])
    news_url: str = DEFAULT_NEWS_URL
    cache_seconds: int = 3600


@router.post("/trend")
async def analyze_trend(body: TrendRequest):
    """
    Classify market state and return a trade-ready signal.

    The bot must pass its short-lived bot token from /bot/verify or /bot/ping.
    """
    payload = require_bot(body.bot_token)
    if payload.get("sub") != body.license_key:
        raise HTTPException(status_code=403, detail="Token không khớp license")

    try:
        candles = [
            Candle(
                open=item.open,
                high=item.high,
                low=item.low,
                close=item.close,
                volume=item.volume,
                time=item.time,
            )
            for item in body.candles
        ]
        strategy = body.strategy.lower()
        result = classify_scalping(candles) if strategy == "scalping" else classify_trend(candles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "ok",
        "symbol": body.symbol.upper(),
        "timeframe": body.timeframe.upper(),
        "strategy": body.strategy.lower(),
        "trend": result.trend,
        "signal": result.signal,
        "confidence": result.confidence,
        "reason": result.reason,
        "entry_price": result.entry_price,
        "sl_price": result.sl_price,
        "tp_price": result.tp_price,
        "indicators": result.indicators,
    }


@router.post("/news-risk")
async def analyze_news_risk(body: NewsRiskRequest):
    payload = require_bot(body.bot_token)
    if payload.get("sub") != body.license_key:
        raise HTTPException(status_code=403, detail="Token không khớp license")

    risk = await evaluate_news_risk(
        symbol=body.symbol,
        minutes_before=body.minutes_before,
        minutes_after=body.minutes_after,
        impacts={impact.title() for impact in body.impacts},
        url=body.news_url,
        cache_seconds=body.cache_seconds,
    )
    return {
        "status": "ok",
        "symbol": body.symbol.upper(),
        "blocked": risk.blocked,
        "reason": risk.reason,
        "events": risk.events,
        "source_error": risk.source_error,
    }
