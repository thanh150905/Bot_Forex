"""
MetaTrader 5 AI Bot Runtime

Flow:
  1. Connect to local MetaTrader 5 terminal
  2. Verify license with FastAPI server and keep pinging
  3. Fetch OHLC candles from MT5
  4. Call /ai/trend for BUY/SELL/HOLD
  5. Send orders to MT5 and report trade to server

Default mode is DRY_RUN=true. Set DRY_RUN=false only after demo testing.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
import MetaTrader5 as mt5

from license_client import LicenseClient


TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

LAST_TRADE_BAR: dict[tuple[str, str], int] = {}
LAST_CLOSE_TIME: dict[tuple[str, str], float] = {}


@dataclass
class BotConfig:
    server_url: str
    license_key: str
    mt_account: str | None
    mt5_path: str | None
    mt5_login: int | None
    mt5_password: str | None
    mt5_server: str | None
    symbols: list[str]
    timeframe: str
    ensemble_timeframes: list[str]
    min_ensemble_agreement: int
    strategy: str
    bars: int
    lot_size: float
    loop_seconds: int
    trade_session_enabled: bool
    trade_sessions_utc: list[tuple[int, int]]
    one_trade_per_bar: bool
    reentry_cooldown_seconds: int
    max_spread_points: float
    max_spread_atr_ratio: float
    min_tp_spread_ratio: float
    min_confidence: float
    min_win_probability: float
    max_signal_risk: float
    max_positions_per_symbol: int
    max_total_positions: int
    orders_per_signal: int
    batch_min_confidence: float
    force_both_sides: bool
    force_alternate_sides: bool
    force_entry_confidence: float
    adx_period: int
    adx_sideway_level: float
    trend_filter_enabled: bool
    allow_hedging: bool
    hedge_rebalance_enabled: bool
    hedge_rebalance_bypass_risk: bool
    min_order_spacing_seconds: int
    min_add_confidence: float
    pyramid_lot_multiplier: float
    batch_fixed_lot: bool
    lot_min_size: float
    lot_max_size: float
    lot_step_size: float
    trend_lot_multiplier: float
    sideway_lot_multiplier: float
    counter_trend_lot_multiplier: float
    max_equity_drawdown_percent: float
    max_daily_loss_percent: float
    max_symbol_floating_loss: float
    close_on_reverse: bool
    max_hold_seconds: int
    close_losers_enabled: bool
    loser_max_loss_money: float
    loser_max_loss_points: float
    close_winners_enabled: bool
    winner_min_profit_money: float
    winner_max_profit_money: float
    winner_min_profit_points: float
    basket_close_enabled: bool
    basket_min_close_positions: int
    basket_min_net_profit_money: float
    basket_max_net_loss_money: float
    basket_profit_loss_ratio: float
    breakeven_points: float
    trailing_start_points: float
    trailing_distance_points: float
    magic: int
    deviation: int
    dry_run: bool
    command_poll_seconds: int
    news_filter_enabled: bool
    news_block_before_minutes: int
    news_block_after_minutes: int
    news_impacts: list[str]
    news_fail_closed: bool


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_hhmm_minutes(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"invalid HH:MM value: {value}")
    hour = int(parts[0])
    minute = int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"invalid HH:MM value: {value}")
    return hour * 60 + minute


def parse_session_ranges(value: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" not in item:
            raise ValueError(f"invalid session range: {item}")
        start_text, end_text = item.split("-", 1)
        ranges.append((parse_hhmm_minutes(start_text), parse_hhmm_minutes(end_text)))
    if not ranges:
        raise ValueError("TRADE_SESSIONS_UTC must include at least one HH:MM-HH:MM range")
    return ranges


def load_config() -> BotConfig:
    license_key = os.getenv("LICENSE_KEY", "").strip()
    if not license_key:
        print("[CONFIG] LICENSE_KEY chưa được cấu hình")
        sys.exit(1)

    symbols = [
        symbol.strip()
        for symbol in os.getenv("SYMBOLS", "EURUSD").split(",")
        if symbol.strip()
    ]
    timeframe = os.getenv("TIMEFRAME", "M15").upper()
    if timeframe not in TIMEFRAMES:
        print(f"[CONFIG] TIMEFRAME không hỗ trợ: {timeframe}. Dùng một trong: {', '.join(TIMEFRAMES)}")
        sys.exit(1)
    ensemble_timeframes = [
        item.strip().upper()
        for item in os.getenv("ENSEMBLE_TIMEFRAMES", timeframe).split(",")
        if item.strip()
    ]
    invalid_timeframes = [item for item in ensemble_timeframes if item not in TIMEFRAMES]
    if invalid_timeframes:
        print(f"[CONFIG] ENSEMBLE_TIMEFRAMES không hỗ trợ: {', '.join(invalid_timeframes)}")
        sys.exit(1)

    session_text = os.getenv("TRADE_SESSIONS_UTC", "07:00-17:00")
    try:
        trade_sessions_utc = parse_session_ranges(session_text)
    except ValueError as exc:
        print(f"[CONFIG] TRADE_SESSIONS_UTC không hợp lệ: {exc}")
        sys.exit(1)

    login = os.getenv("MT5_LOGIN")
    return BotConfig(
        server_url=os.getenv("SERVER_URL", "http://localhost:8000").rstrip("/"),
        license_key=license_key,
        mt_account=os.getenv("MT_ACCOUNT"),
        mt5_path=os.getenv("MT5_PATH"),
        mt5_login=int(login) if login else None,
        mt5_password=os.getenv("MT5_PASSWORD"),
        mt5_server=os.getenv("MT5_SERVER"),
        symbols=symbols,
        timeframe=timeframe,
        ensemble_timeframes=ensemble_timeframes,
        min_ensemble_agreement=int(os.getenv("MIN_ENSEMBLE_AGREEMENT", "1")),
        strategy=os.getenv("STRATEGY", "scalping").strip().lower(),
        bars=int(os.getenv("BARS", "100")),
        lot_size=float(os.getenv("LOT_SIZE", "0.01")),
        loop_seconds=int(os.getenv("LOOP_SECONDS", "60")),
        trade_session_enabled=env_bool("TRADE_SESSION_ENABLED", True),
        trade_sessions_utc=trade_sessions_utc,
        one_trade_per_bar=env_bool("ONE_TRADE_PER_BAR", True),
        reentry_cooldown_seconds=int(os.getenv("REENTRY_COOLDOWN_SECONDS", "15")),
        max_spread_points=float(os.getenv("MAX_SPREAD_POINTS", "30")),
        max_spread_atr_ratio=float(os.getenv("MAX_SPREAD_ATR_RATIO", "0.35")),
        min_tp_spread_ratio=float(os.getenv("MIN_TP_SPREAD_RATIO", "2.5")),
        min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.70")),
        min_win_probability=float(os.getenv("MIN_WIN_PROBABILITY", "0.58")),
        max_signal_risk=float(os.getenv("MAX_SIGNAL_RISK", "0.55")),
        max_positions_per_symbol=int(os.getenv("MAX_POSITIONS_PER_SYMBOL", "1")),
        max_total_positions=int(os.getenv("MAX_TOTAL_POSITIONS", "3")),
        orders_per_signal=int(os.getenv("ORDERS_PER_SIGNAL", "1")),
        batch_min_confidence=float(os.getenv("BATCH_MIN_CONFIDENCE", "0.82")),
        force_both_sides=env_bool("FORCE_BOTH_SIDES", False),
        force_alternate_sides=env_bool("FORCE_ALTERNATE_SIDES", True),
        force_entry_confidence=float(os.getenv("FORCE_ENTRY_CONFIDENCE", "0.66")),
        adx_period=int(os.getenv("ADX_PERIOD", "14")),
        adx_sideway_level=float(os.getenv("ADX_SIDEWAY_LEVEL", "25.0")),
        trend_filter_enabled=env_bool("TREND_FILTER_ENABLED", True),
        allow_hedging=env_bool("ALLOW_HEDGING", False),
        hedge_rebalance_enabled=env_bool("HEDGE_REBALANCE_ENABLED", True),
        hedge_rebalance_bypass_risk=env_bool("HEDGE_REBALANCE_BYPASS_RISK", True),
        min_order_spacing_seconds=int(os.getenv("MIN_ORDER_SPACING_SECONDS", "45")),
        min_add_confidence=float(os.getenv("MIN_ADD_CONFIDENCE", "0.78")),
        pyramid_lot_multiplier=float(os.getenv("PYRAMID_LOT_MULTIPLIER", "0.75")),
        batch_fixed_lot=env_bool("BATCH_FIXED_LOT", False),
        lot_min_size=float(os.getenv("LOT_MIN_SIZE", "0")),
        lot_max_size=float(os.getenv("LOT_MAX_SIZE", "0")),
        lot_step_size=float(os.getenv("LOT_STEP_SIZE", "0.01")),
        trend_lot_multiplier=float(os.getenv("TREND_LOT_MULTIPLIER", "1.00")),
        sideway_lot_multiplier=float(os.getenv("SIDEWAY_LOT_MULTIPLIER", "1.00")),
        counter_trend_lot_multiplier=float(os.getenv("COUNTER_TREND_LOT_MULTIPLIER", "0.50")),
        max_equity_drawdown_percent=float(os.getenv("MAX_EQUITY_DRAWDOWN_PERCENT", "4")),
        max_daily_loss_percent=float(os.getenv("MAX_DAILY_LOSS_PERCENT", "3")),
        max_symbol_floating_loss=float(os.getenv("MAX_SYMBOL_FLOATING_LOSS", "40")),
        close_on_reverse=env_bool("CLOSE_ON_REVERSE", True),
        max_hold_seconds=int(os.getenv("MAX_HOLD_SECONDS", "900")),
        close_losers_enabled=env_bool("CLOSE_LOSERS_ENABLED", True),
        loser_max_loss_money=float(os.getenv("LOSER_MAX_LOSS_MONEY", "40")),
        loser_max_loss_points=float(os.getenv("LOSER_MAX_LOSS_POINTS", "0")),
        close_winners_enabled=env_bool("CLOSE_WINNERS_ENABLED", True),
        winner_min_profit_money=float(os.getenv("WINNER_MIN_PROFIT_MONEY", "3.00")),
        winner_max_profit_money=float(os.getenv("WINNER_MAX_PROFIT_MONEY", "8.00")),
        winner_min_profit_points=float(os.getenv("WINNER_MIN_PROFIT_POINTS", "0")),
        basket_close_enabled=env_bool("BASKET_CLOSE_ENABLED", True),
        basket_min_close_positions=int(os.getenv("BASKET_MIN_CLOSE_POSITIONS", "0")),
        basket_min_net_profit_money=float(os.getenv("BASKET_MIN_NET_PROFIT_MONEY", "50.00")),
        basket_max_net_loss_money=float(os.getenv("BASKET_MAX_NET_LOSS_MONEY", "40.00")),
        basket_profit_loss_ratio=float(os.getenv("BASKET_PROFIT_LOSS_RATIO", "0")),
        breakeven_points=float(os.getenv("BREAKEVEN_POINTS", "80")),
        trailing_start_points=float(os.getenv("TRAILING_START_POINTS", "120")),
        trailing_distance_points=float(os.getenv("TRAILING_DISTANCE_POINTS", "80")),
        magic=int(os.getenv("MAGIC", "260501")),
        deviation=int(os.getenv("DEVIATION", "20")),
        dry_run=env_bool("DRY_RUN", True),
        command_poll_seconds=int(os.getenv("COMMAND_POLL_SECONDS", "2")),
        news_filter_enabled=env_bool("NEWS_FILTER_ENABLED", True),
        news_block_before_minutes=int(os.getenv("NEWS_BLOCK_BEFORE_MINUTES", "45")),
        news_block_after_minutes=int(os.getenv("NEWS_BLOCK_AFTER_MINUTES", "20")),
        news_impacts=[
            item.strip().title()
            for item in os.getenv("NEWS_IMPACTS", "High,Holiday").split(",")
            if item.strip()
        ],
        news_fail_closed=env_bool("NEWS_FAIL_CLOSED", False),
    )


def connect_mt5(config: BotConfig) -> None:
    kwargs: dict[str, Any] = {}
    if config.mt5_path:
        kwargs["path"] = config.mt5_path
    if config.mt5_login:
        kwargs["login"] = config.mt5_login
    if config.mt5_password:
        kwargs["password"] = config.mt5_password
    if config.mt5_server:
        kwargs["server"] = config.mt5_server

    if not mt5.initialize(**kwargs):
        print(f"[MT5] Không kết nối được terminal: {mt5.last_error()}")
        sys.exit(1)

    account = mt5.account_info()
    if account is None:
        print(f"[MT5] Không lấy được account info: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)
    if getattr(account, "trade_allowed", True) is False:
        print("[MT5] Trading bị khóa trên tài khoản/terminal. Kiểm tra quyền trade của broker.")
        mt5.shutdown()
        sys.exit(1)
    if getattr(account, "trade_expert", True) is False:
        print("[MT5] AutoTrading/Algo Trading đang tắt. Bật nút Algo Trading trong MT5 rồi chạy lại bot.")
        mt5.shutdown()
        sys.exit(1)

    print(f"[MT5] Connected | Login: {account.login} | Server: {account.server} | Balance: {account.balance}")


def ensure_symbol(symbol: str) -> bool:
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"[MT5] Symbol không tồn tại: {symbol}")
        return False
    if not info.visible and not mt5.symbol_select(symbol, True):
        print(f"[MT5] Không bật được symbol: {symbol}")
        return False
    return True


def fetch_candles(symbol: str, timeframe: str, bars: int) -> list[dict[str, Any]]:
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAMES[timeframe], 0, bars)
    if rates is None or len(rates) < 60:
        raise RuntimeError(f"Không đủ nến cho {symbol}: {mt5.last_error()}")

    candles: list[dict[str, Any]] = []
    for rate in rates:
        candles.append(
            {
                "time": datetime.fromtimestamp(int(rate["time"]), tz=timezone.utc).isoformat(),
                "open": float(rate["open"]),
                "high": float(rate["high"]),
                "low": float(rate["low"]),
                "close": float(rate["close"]),
                "volume": float(rate["tick_volume"]),
            }
        )
    return candles


def get_adx_dmi(symbol: str, period: int = 14, timeframe: str = "M1") -> dict[str, float]:
    """
    Lấy nến OHLC từ MT5 và tính ADX, +DI, -DI bằng Wilder smoothing.

    Cách chèn:
      - Gọi hàm này trong main loop sau khi đã ensure_symbol(symbol).
      - Dùng kết quả đưa vào get_market_state() để quyết định SIDEWAY/UPTREND/DOWNTREND.
    """
    try:
        timeframe = timeframe.upper()
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Timeframe không hỗ trợ: {timeframe}")
        if period < 2:
            raise ValueError("ADX_PERIOD phải >= 2")

        bars = max(period * 4 + 20, 80)
        rates = mt5.copy_rates_from_pos(symbol, TIMEFRAMES[timeframe], 0, bars)
        if rates is None or len(rates) < period * 2 + 2:
            raise RuntimeError(f"Không đủ nến {timeframe} để tính ADX cho {symbol}: {mt5.last_error()}")

        highs = [float(rate["high"]) for rate in rates]
        lows = [float(rate["low"]) for rate in rates]
        closes = [float(rate["close"]) for rate in rates]

        tr_values: list[float] = []
        plus_dm_values: list[float] = []
        minus_dm_values: list[float] = []

        for index in range(1, len(rates)):
            high_diff = highs[index] - highs[index - 1]
            low_diff = lows[index - 1] - lows[index]

            plus_dm = high_diff if high_diff > low_diff and high_diff > 0 else 0.0
            minus_dm = low_diff if low_diff > high_diff and low_diff > 0 else 0.0
            true_range = max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )

            tr_values.append(true_range)
            plus_dm_values.append(plus_dm)
            minus_dm_values.append(minus_dm)

        smoothed_tr = sum(tr_values[:period])
        smoothed_plus_dm = sum(plus_dm_values[:period])
        smoothed_minus_dm = sum(minus_dm_values[:period])
        dx_values: list[float] = []
        latest_plus_di = 0.0
        latest_minus_di = 0.0

        for index in range(period, len(tr_values)):
            smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr_values[index]
            smoothed_plus_dm = smoothed_plus_dm - (smoothed_plus_dm / period) + plus_dm_values[index]
            smoothed_minus_dm = smoothed_minus_dm - (smoothed_minus_dm / period) + minus_dm_values[index]

            if smoothed_tr <= 0:
                plus_di = 0.0
                minus_di = 0.0
                dx = 0.0
            else:
                plus_di = 100.0 * smoothed_plus_dm / smoothed_tr
                minus_di = 100.0 * smoothed_minus_dm / smoothed_tr
                di_total = plus_di + minus_di
                dx = 0.0 if di_total <= 0 else 100.0 * abs(plus_di - minus_di) / di_total

            latest_plus_di = plus_di
            latest_minus_di = minus_di
            dx_values.append(dx)

        if len(dx_values) < period:
            raise RuntimeError(f"Không đủ DX để tính ADX cho {symbol}")

        adx = sum(dx_values[:period]) / period
        for dx in dx_values[period:]:
            adx = ((adx * (period - 1)) + dx) / period

        return {
            "adx": round(adx, 4),
            "plus_di": round(latest_plus_di, 4),
            "minus_di": round(latest_minus_di, 4),
        }
    except Exception as exc:
        raise RuntimeError(f"[ADX] {symbol} lỗi tính ADX/DMI: {exc}") from exc


def get_market_state(symbol: str, config: BotConfig) -> dict[str, Any]:
    """
    Phân loại thị trường theo timeframe chính:
      - SIDEWAY: ADX < ADX_SIDEWAY_LEVEL
      - UPTREND: ADX >= level và +DI > -DI
      - DOWNTREND: ADX >= level và -DI > +DI
    """
    try:
        dmi = get_adx_dmi(symbol, config.adx_period, config.timeframe)
        adx = dmi["adx"]
        plus_di = dmi["plus_di"]
        minus_di = dmi["minus_di"]

        if adx < config.adx_sideway_level:
            state = "SIDEWAY"
        elif plus_di > minus_di:
            state = "UPTREND"
        elif minus_di > plus_di:
            state = "DOWNTREND"
        else:
            state = "SIDEWAY"

        print(
            f"[MARKET] {symbol} {state} | ADX={adx:.2f} "
            f"+DI={plus_di:.2f} -DI={minus_di:.2f} level={config.adx_sideway_level:.2f}"
        )
        return {"state": state, **dmi}
    except Exception as exc:
        print(f"[MARKET] {symbol} warning | không phân loại được market state: {exc}")
        return {"state": "UNKNOWN", "adx": 0.0, "plus_di": 0.0, "minus_di": 0.0}


def filter_signals(config: BotConfig, market_state: dict[str, Any], ai_signal: dict[str, Any]) -> dict[str, Any]:
    """
    Lọc tín hiệu trước khi send_order():
      - SIDEWAY: cho phép cả BUY và SELL để hedge/scalp.
      - UPTREND + TREND_FILTER_ENABLED=true: chặn SELL, chỉ cho BUY.
      - DOWNTREND + TREND_FILTER_ENABLED=true: chặn BUY, chỉ cho SELL.

    Cách chèn vào main loop:
      signal = analyze_signal(...)
      market_state = get_market_state(symbol, config)
      signal = filter_signals(config, market_state, signal)
      send_order(config, license_client, signal)
    """
    direction = ai_signal.get("signal")
    state = str(market_state.get("state", "UNKNOWN"))
    indicators = dict(ai_signal.get("indicators") or {})
    indicators.update(
        {
            "market_adx": float(market_state.get("adx", 0.0)),
            "market_plus_di": float(market_state.get("plus_di", 0.0)),
            "market_minus_di": float(market_state.get("minus_di", 0.0)),
        }
    )
    enriched_signal = {**ai_signal, "market_state": state, "indicators": indicators}

    if direction not in {"BUY", "SELL"}:
        return enriched_signal
    if state in {"SIDEWAY", "UNKNOWN"} or not config.trend_filter_enabled:
        return enriched_signal
    if state == "UPTREND" and direction == "SELL":
        return {
            **enriched_signal,
            "signal": "HOLD",
            "reason": (
                f"Trend filter blocked SELL in UPTREND "
                f"(ADX={market_state.get('adx', 0):.2f}, +DI={market_state.get('plus_di', 0):.2f}, "
                f"-DI={market_state.get('minus_di', 0):.2f})"
            ),
        }
    if state == "DOWNTREND" and direction == "BUY":
        return {
            **enriched_signal,
            "signal": "HOLD",
            "reason": (
                f"Trend filter blocked BUY in DOWNTREND "
                f"(ADX={market_state.get('adx', 0):.2f}, +DI={market_state.get('plus_di', 0):.2f}, "
                f"-DI={market_state.get('minus_di', 0):.2f})"
            ),
        }
    return enriched_signal


def request_signal(
    config: BotConfig,
    license_client: LicenseClient,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    candles = fetch_candles(symbol, timeframe, config.bars)
    response = httpx.post(
        f"{config.server_url}/ai/trend",
        json={
            "bot_token": license_client.bot_token,
            "license_key": config.license_key,
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": config.strategy,
            "candles": candles,
        },
        timeout=15,
    )
    data = response.json()
    if response.status_code != 200:
        raise RuntimeError(data.get("detail", "AI Engine error"))
    return data


def combine_ensemble_signals(symbol: str, signals: list[dict[str, Any]], min_agreement: int) -> dict[str, Any]:
    actionable = [item for item in signals if item.get("signal") in {"BUY", "SELL"}]
    buy_votes = [item for item in actionable if item["signal"] == "BUY"]
    sell_votes = [item for item in actionable if item["signal"] == "SELL"]
    winning_votes = buy_votes if len(buy_votes) >= len(sell_votes) else sell_votes

    if len(winning_votes) < min_agreement:
        primary = signals[0]
        return {
            **primary,
            "symbol": symbol,
            "signal": "HOLD",
            "reason": f"Ensemble HOLD: only {len(winning_votes)} agreeing signals, need {min_agreement}",
            "ensemble": signals,
        }

    direction = winning_votes[0]["signal"]
    avg_confidence = sum(float(item.get("confidence", 0)) for item in winning_votes) / len(winning_votes)
    avg_probability = sum(signal_probability(item) for item in winning_votes) / len(winning_votes)
    avg_risk = sum(signal_risk(item) for item in winning_votes) / len(winning_votes)
    best = max(winning_votes, key=lambda item: float(item.get("confidence", 0)))
    indicators = dict(best.get("indicators") or {})
    indicators.update(
        {
            "ensemble_votes": float(len(winning_votes)),
            "ensemble_total": float(len(signals)),
            "estimated_probability": round(avg_probability, 4),
            "risk_score": round(avg_risk, 4),
        }
    )
    return {
        **best,
        "symbol": symbol,
        "signal": direction,
        "confidence": round(avg_confidence, 4),
        "reason": (
            f"Ensemble {direction}: {len(winning_votes)}/{len(signals)} timeframes agree. "
            f"Best: {best.get('reason')}"
        ),
        "indicators": indicators,
        "ensemble": signals,
    }


def analyze_signal(config: BotConfig, license_client: LicenseClient, symbol: str) -> dict[str, Any]:
    signals = [
        request_signal(config, license_client, symbol, timeframe)
        for timeframe in config.ensemble_timeframes
    ]
    return combine_ensemble_signals(symbol, signals, config.min_ensemble_agreement)


def forced_signal(config: BotConfig, symbol: str, direction: str, base_signal: dict[str, Any]) -> dict[str, Any]:
    indicators = dict(base_signal.get("indicators") or {})
    confidence = config.force_entry_confidence
    indicators.update(
        {
            "estimated_probability": max(float(indicators.get("estimated_probability", 0.0)), confidence),
            "risk_score": min(float(indicators.get("risk_score", 0.35)), 0.35),
            "force_entry": 1.0,
        }
    )
    price = float(base_signal.get("entry_price", 0.0) or 0.0)
    return {
        **base_signal,
        "symbol": symbol,
        "signal": direction,
        "confidence": confidence,
        "trend": f"forced_{direction.lower()}",
        "entry_price": price,
        "sl_price": None,
        "tp_price": None,
        "reason": f"FORCE_BOTH_SIDES hedge entry from base signal: {base_signal.get('reason', '-')}",
        "indicators": indicators,
    }


def news_allows_trading(config: BotConfig, license_client: LicenseClient, symbol: str) -> bool:
    if not config.news_filter_enabled:
        return True
    try:
        response = httpx.post(
            f"{config.server_url}/ai/news-risk",
            json={
                "bot_token": license_client.bot_token,
                "license_key": config.license_key,
                "symbol": symbol,
                "minutes_before": config.news_block_before_minutes,
                "minutes_after": config.news_block_after_minutes,
                "impacts": config.news_impacts,
            },
            timeout=12,
        )
        data = response.json()
        if response.status_code != 200:
            raise RuntimeError(data.get("detail", "News filter error"))
        if data.get("source_error") and config.news_fail_closed:
            print(f"[NEWS] {symbol} blocked | source error: {data['source_error']}")
            return False
        if data.get("blocked"):
            print(f"[NEWS] {symbol} blocked | {data.get('reason')}")
            return False
        if data.get("source_error"):
            print(f"[NEWS] {symbol} warning | source error, fail-open: {data['source_error']}")
        return True
    except Exception as exc:
        if config.news_fail_closed:
            print(f"[NEWS] {symbol} blocked | filter failed: {exc}")
            return False
        print(f"[NEWS] {symbol} warning | filter failed, fail-open: {exc}")
        return True


def format_session_ranges(ranges: list[tuple[int, int]]) -> str:
    def fmt(minutes: int) -> str:
        return f"{minutes // 60:02d}:{minutes % 60:02d}"

    return ",".join(f"{fmt(start)}-{fmt(end)}" for start, end in ranges)


def minute_in_range(minute: int, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end


def trade_session_is_allowed(config: BotConfig) -> bool:
    if not config.trade_session_enabled:
        return True
    now = datetime.now(timezone.utc)
    minute = now.hour * 60 + now.minute
    return any(minute_in_range(minute, start, end) for start, end in config.trade_sessions_utc)


def trade_session_allows(config: BotConfig, symbol: str) -> bool:
    if trade_session_is_allowed(config):
        return True

    now = datetime.now(timezone.utc)
    print(
        f"[SESSION] {symbol} skip | now_utc={now.strftime('%H:%M')} "
        f"outside {format_session_ranges(config.trade_sessions_utc)}"
    )
    return False


def current_bar_time(symbol: str, timeframe: str) -> int | None:
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAMES[timeframe], 0, 1)
    if rates is None or len(rates) < 1:
        return None
    return int(rates[-1]["time"])


def one_trade_per_bar_allows(config: BotConfig, symbol: str, direction: str, timeframe: str) -> bool:
    if not config.one_trade_per_bar:
        return True

    bar_time = current_bar_time(symbol, timeframe)
    if bar_time is None:
        print(f"[BAR] {symbol} skip | không lấy được current bar time")
        return False

    key = (symbol, direction)
    if LAST_TRADE_BAR.get(key) == bar_time:
        print(f"[BAR] {symbol} skip | already traded {direction} on current {timeframe} bar")
        return False

    LAST_TRADE_BAR[key] = bar_time
    return True


def reentry_cooldown_allows(config: BotConfig, symbol: str, direction: str) -> bool:
    if config.reentry_cooldown_seconds <= 0:
        return True

    last_close = LAST_CLOSE_TIME.get((symbol, direction))
    if last_close is None:
        return True

    elapsed = time.time() - last_close
    if elapsed >= config.reentry_cooldown_seconds:
        return True

    print(
        f"[CYCLE] {symbol} skip | {direction} reentry cooldown "
        f"{elapsed:.0f}s < {config.reentry_cooldown_seconds}s"
    )
    return False


def symbol_spread_points(symbol: str) -> float:
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None or info.point <= 0:
        return 999999.0
    return (tick.ask - tick.bid) / info.point


def bot_positions(symbol: str, magic: int) -> list[Any]:
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return []
    return [position for position in positions if position.magic == magic]


def all_bot_positions(magic: int) -> list[Any]:
    positions = mt5.positions_get()
    if not positions:
        return []
    return [position for position in positions if position.magic == magic]


def signed_profit_pips(symbol: str, position: Any, close_price: float | None = None) -> float:
    price = close_price
    if price is None:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return 0.0
        price = tick.bid if position.type == mt5.POSITION_TYPE_BUY else tick.ask

    pips = points_between(symbol, position.price_open, float(price)) / 10.0
    if position_direction(position) == "SELL":
        return round(-pips if float(price) > position.price_open else pips, 1)
    return round(-pips if float(price) < position.price_open else pips, 1)


def position_snapshot(position: Any) -> dict[str, Any]:
    symbol = str(position.symbol)
    opened_at = None
    opened_epoch = int(getattr(position, "time", 0) or 0)
    if opened_epoch > 0:
        opened_at = datetime.fromtimestamp(opened_epoch, timezone.utc).isoformat()
    return {
        "ticket": str(position.ticket),
        "symbol": symbol,
        "direction": position_direction(position),
        "entry_price": float(position.price_open),
        "sl_price": float(position.sl) if position.sl else None,
        "tp_price": float(position.tp) if position.tp else None,
        "lot_size": float(position.volume),
        "profit": float(position.profit or 0.0),
        "pips": signed_profit_pips(symbol, position),
        "opened_at": opened_at,
        "note": "MT5 live position sync",
    }


def sync_live_positions(config: BotConfig, license_client: LicenseClient) -> None:
    snapshots = [position_snapshot(position) for position in all_bot_positions(config.magic)]
    license_client.sync_positions(snapshots, mark_missing_closed=True)


def report_runtime_status(
    config: BotConfig,
    license_client: LicenseClient,
    symbol: str,
    signal: dict[str, Any] | None,
    run_state: str,
    reason: str | None = None,
    session_allowed: bool | None = None,
) -> None:
    signal = signal or {"signal": "HOLD", "confidence": 0.0, "reason": reason or "-"}
    signal_name = str(signal.get("signal") or "HOLD").upper()
    timeframe = str(signal.get("timeframe") or config.timeframe).upper()
    open_count = len(bot_positions(symbol, config.magic))
    total_count = len(all_bot_positions(config.magic))
    indicators = signal.get("indicators") or {}
    payload = {
        "trend": signal.get("trend"),
        "market_state": signal.get("market_state"),
        "probability": signal_probability(signal),
        "risk": signal_risk(signal),
        "atr_points": round(signal_atr_points(symbol, signal), 1),
        "reward_points": round(signal_reward_points(symbol, signal), 1),
        "ensemble": signal.get("ensemble"),
        "indicators": indicators,
    }
    license_client.report_status(
        symbol=symbol,
        timeframe=timeframe,
        strategy=config.strategy,
        signal=signal_name,
        reason=reason or str(signal.get("reason") or "-"),
        confidence=float(signal.get("confidence", 0.0) or 0.0),
        spread_points=round(symbol_spread_points(symbol), 1),
        open_positions=open_count,
        total_positions=total_count,
        max_positions=config.max_positions_per_symbol,
        max_total_positions=config.max_total_positions,
        dry_run=config.dry_run,
        session_allowed=trade_session_is_allowed(config) if session_allowed is None else session_allowed,
        run_state=run_state,
        payload=payload,
    )


def position_direction(position: Any) -> str:
    return "BUY" if position.type == mt5.POSITION_TYPE_BUY else "SELL"


def hedge_side_stats(symbol: str, magic: int) -> dict[str, dict[str, float]]:
    stats = {
        "BUY": {"count": 0.0, "lot": 0.0, "profit": 0.0, "loss": 0.0},
        "SELL": {"count": 0.0, "lot": 0.0, "profit": 0.0, "loss": 0.0},
    }
    for position in bot_positions(symbol, magic):
        direction = position_direction(position)
        profit = float(position.profit or 0.0)
        stats[direction]["count"] += 1
        stats[direction]["lot"] += float(position.volume or 0.0)
        stats[direction]["profit"] += profit
        stats[direction]["loss"] += abs(min(0.0, profit))
    return stats


def hedge_rebalance_direction(config: BotConfig, symbol: str) -> str | None:
    if not config.hedge_rebalance_enabled or not config.force_both_sides or not config.allow_hedging:
        return None

    stats = hedge_side_stats(symbol, config.magic)
    buy = stats["BUY"]
    sell = stats["SELL"]
    if buy["count"] + sell["count"] <= 0:
        return None

    if buy["count"] > sell["count"]:
        return "SELL"
    if sell["count"] > buy["count"]:
        return "BUY"
    if buy["lot"] > sell["lot"] + 0.0001:
        return "SELL"
    if sell["lot"] > buy["lot"] + 0.0001:
        return "BUY"
    if buy["loss"] > sell["loss"] + 0.01:
        return "SELL"
    if sell["loss"] > buy["loss"] + 0.01:
        return "BUY"
    return None


def forced_direction_order(config: BotConfig, symbol: str, signal: dict[str, Any]) -> tuple[tuple[str, ...], bool]:
    rebalance_direction = hedge_rebalance_direction(config, symbol)
    if rebalance_direction:
        return (rebalance_direction,), True

    first_direction = "SELL" if signal.get("signal") == "SELL" else "BUY"
    second_direction = "BUY" if first_direction == "SELL" else "SELL"
    return (first_direction, second_direction), False


def points_between(symbol: str, price_a: float, price_b: float) -> float:
    info = mt5.symbol_info(symbol)
    if info is None or info.point <= 0:
        return 0.0
    return abs(price_a - price_b) / info.point


def position_profit_points(symbol: str, position: Any) -> float:
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None or info.point <= 0:
        return 0.0
    if position.type == mt5.POSITION_TYPE_BUY:
        return (tick.bid - position.price_open) / info.point
    return (position.price_open - tick.ask) / info.point


def position_age_seconds(position: Any) -> int:
    opened_at = int(getattr(position, "time", 0) or 0)
    if opened_at <= 0:
        return 0
    return max(0, int(time.time()) - opened_at)


def seconds_since_last_position(positions: list[Any]) -> int | None:
    if not positions:
        return None
    latest_open = max(int(getattr(position, "time", 0) or 0) for position in positions)
    if latest_open <= 0:
        return None
    return max(0, int(time.time()) - latest_open)


def today_realized_profit(magic: int) -> float:
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, now)
    if not deals:
        return 0.0
    total = 0.0
    for deal in deals:
        if getattr(deal, "magic", None) == magic:
            total += float(getattr(deal, "profit", 0.0) or 0.0)
            total += float(getattr(deal, "swap", 0.0) or 0.0)
            total += float(getattr(deal, "commission", 0.0) or 0.0)
    return total


def signal_probability(signal: dict[str, Any]) -> float:
    indicators = signal.get("indicators") or {}
    return float(indicators.get("estimated_probability", signal.get("confidence", 0.0)))


def signal_risk(signal: dict[str, Any]) -> float:
    indicators = signal.get("indicators") or {}
    return float(indicators.get("risk_score", 1.0 - float(signal.get("confidence", 0.0))))


def signal_atr_points(symbol: str, signal: dict[str, Any]) -> float:
    indicators = signal.get("indicators") or {}
    atr_value = float(indicators.get("atr_14", 0.0) or 0.0)
    info = mt5.symbol_info(symbol)
    if info is None or info.point <= 0:
        return 0.0
    return atr_value / info.point


def signal_reward_points(symbol: str, signal: dict[str, Any]) -> float:
    entry_price = float(signal.get("entry_price", 0.0) or 0.0)
    tp_price = signal.get("tp_price")
    direction = signal.get("signal")
    if not entry_price or tp_price is None or direction not in {"BUY", "SELL"}:
        return 0.0

    info = mt5.symbol_info(symbol)
    if info is None or info.point <= 0:
        return 0.0

    tp = float(tp_price)
    if direction == "BUY":
        return max(0.0, (tp - entry_price) / info.point)
    return max(0.0, (entry_price - tp) / info.point)


def risk_allows_new_order(
    config: BotConfig,
    symbol: str,
    signal: dict[str, Any],
    hedge_rebalance: bool = False,
) -> tuple[bool, str | None]:
    probability = signal_probability(signal)
    risk = signal_risk(signal)
    spread = symbol_spread_points(symbol)
    atr_points = signal_atr_points(symbol, signal)
    reward_points = signal_reward_points(symbol, signal)
    if probability < config.min_win_probability:
        reason = f"probability {probability:.2f} < {config.min_win_probability:.2f}"
        print(f"[RISK] {symbol} skip | {reason}")
        return False, reason
    if risk > config.max_signal_risk:
        reason = f"signal risk {risk:.2f} > {config.max_signal_risk:.2f}"
        print(f"[RISK] {symbol} skip | {reason}")
        return False, reason
    if atr_points > 0 and config.max_spread_atr_ratio > 0:
        spread_ratio = spread / atr_points
        if spread_ratio > config.max_spread_atr_ratio:
            reason = f"spread/ATR {spread_ratio:.2f} > {config.max_spread_atr_ratio:.2f}"
            print(
                f"[RISK] {symbol} skip | {reason}"
            )
            return False, reason
    if reward_points > 0 and spread > 0 and config.min_tp_spread_ratio > 0:
        reward_spread_ratio = reward_points / spread
        if reward_spread_ratio < config.min_tp_spread_ratio:
            reason = f"TP/spread {reward_spread_ratio:.2f} < {config.min_tp_spread_ratio:.2f}"
            print(
                f"[RISK] {symbol} skip | {reason}"
            )
            return False, reason

    account = mt5.account_info()
    if account is None:
        reason = "Không lấy được account info"
        print(f"[RISK] {reason}")
        return False, reason

    balance = float(account.balance or 0.0)
    equity = float(account.equity or 0.0)
    if balance > 0 and config.max_equity_drawdown_percent > 0:
        drawdown_percent = max(0.0, (balance - equity) / balance * 100.0)
        if drawdown_percent >= config.max_equity_drawdown_percent:
            if hedge_rebalance and config.hedge_rebalance_bypass_risk:
                print(
                    f"[HEDGE] {symbol} rebalance bypass | equity drawdown "
                    f"{drawdown_percent:.2f}% >= {config.max_equity_drawdown_percent:.2f}%"
                )
            else:
                reason = (
                    f"equity drawdown {drawdown_percent:.2f}% "
                    f">= {config.max_equity_drawdown_percent:.2f}%"
                )
                print(
                    f"[RISK] {symbol} stop | {reason}"
                )
                return False, reason

    if balance > 0 and config.max_daily_loss_percent > 0:
        daily_profit = today_realized_profit(config.magic)
        daily_loss_percent = max(0.0, -daily_profit / balance * 100.0)
        if daily_loss_percent >= config.max_daily_loss_percent:
            if hedge_rebalance and config.hedge_rebalance_bypass_risk:
                print(
                    f"[HEDGE] {symbol} rebalance bypass | daily loss "
                    f"{daily_loss_percent:.2f}% >= {config.max_daily_loss_percent:.2f}%"
                )
            else:
                reason = (
                    f"daily loss {daily_loss_percent:.2f}% "
                    f">= {config.max_daily_loss_percent:.2f}%"
                )
                print(
                    f"[RISK] {symbol} stop | {reason}"
                )
                return False, reason

    if config.max_symbol_floating_loss > 0:
        symbol_loss = sum(min(0.0, float(position.profit or 0.0)) for position in bot_positions(symbol, config.magic))
        if abs(symbol_loss) >= config.max_symbol_floating_loss:
            if hedge_rebalance and config.hedge_rebalance_bypass_risk:
                print(
                    f"[HEDGE] {symbol} rebalance bypass | floating loss "
                    f"{symbol_loss:.2f} <= -{config.max_symbol_floating_loss:.2f}"
                )
            else:
                reason = (
                    f"floating loss {symbol_loss:.2f} "
                    f"<= -{config.max_symbol_floating_loss:.2f}"
                )
                print(
                    f"[RISK] {symbol} stop | {reason}"
                )
                return False, reason

    return True, None


def normalize_volume(symbol: str, volume: float) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        return volume
    volume = max(info.volume_min, min(volume, info.volume_max))
    steps = round(volume / info.volume_step)
    return round(steps * info.volume_step, 2)


def trend_lot_multiplier(config: BotConfig, direction: str, signal: dict[str, Any]) -> tuple[float, str]:
    market_state = str(signal.get("market_state") or "UNKNOWN").upper()
    if market_state == "UPTREND":
        if direction == "BUY":
            return max(0.0, config.trend_lot_multiplier), "trend_aligned"
        return max(0.0, config.counter_trend_lot_multiplier), "counter_trend"
    if market_state == "DOWNTREND":
        if direction == "SELL":
            return max(0.0, config.trend_lot_multiplier), "trend_aligned"
        return max(0.0, config.counter_trend_lot_multiplier), "counter_trend"
    return max(0.0, config.sideway_lot_multiplier), "sideway"


def order_volume(config: BotConfig, symbol: str, direction: str, signal: dict[str, Any]) -> tuple[float, str]:
    multiplier, lot_basis = trend_lot_multiplier(config, direction, signal)
    volume = config.lot_size * multiplier
    if config.lot_min_size > 0:
        volume = max(volume, config.lot_min_size)
    if config.lot_max_size > 0:
        volume = min(volume, config.lot_max_size)
    return normalize_volume(symbol, volume), lot_basis


def modify_position_sl_tp(symbol: str, ticket: int, sl: float | None, tp: float | None, dry_run: bool) -> bool:
    if dry_run:
        print(f"[DRY_RUN] Modify {symbol} ticket={ticket} sl={sl} tp={tp}")
        return True

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": ticket,
        "sl": float(sl or 0.0),
        "tp": float(tp or 0.0),
    }
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        detail = mt5.last_error() if result is None else f"{result.retcode} {result.comment}"
        print(f"[MT5] Modify rejected | ticket={ticket} {detail}")
        return False
    return True


def close_position(config: BotConfig, license_client: LicenseClient, position: Any, reason: str) -> bool:
    symbol = position.symbol
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[MT5] Không lấy được tick để đóng {symbol}")
        return False

    direction = position_direction(position)
    close_type = mt5.ORDER_TYPE_SELL if direction == "BUY" else mt5.ORDER_TYPE_BUY
    close_price = tick.bid if direction == "BUY" else tick.ask

    print(
        f"[SCALP] Close {direction} {symbol} ticket={position.ticket} "
        f"profit={position.profit:.2f} reason={reason}"
    )

    LAST_CLOSE_TIME[(symbol, direction)] = time.time()

    if config.dry_run:
        print("[DRY_RUN] Không đóng lệnh thật.")
        return True

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": position.volume,
        "type": close_type,
        "position": position.ticket,
        "price": close_price,
        "deviation": config.deviation,
        "magic": config.magic,
        "comment": "FB close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None:
        print(f"[MT5] close order_send failed: {mt5.last_error()}")
        return False
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[MT5] Close rejected | retcode={result.retcode} comment={result.comment}")
        return False

    pips = points_between(symbol, position.price_open, close_price) / 10.0
    if direction == "SELL":
        pips *= -1 if close_price > position.price_open else 1
    elif close_price < position.price_open:
        pips *= -1

    license_client.report_trade(
        ticket=str(position.ticket),
        symbol=symbol,
        direction=direction,
        entry_price=float(position.price_open),
        lot_size=float(position.volume),
        sl_price=float(position.sl) if position.sl else None,
        tp_price=float(position.tp) if position.tp else None,
        status="closed",
        close_price=float(close_price),
        profit=float(position.profit),
        pips=float(round(pips, 1)),
        note=f"Auto close: {reason}",
    )
    return True


def manage_basket_profit(config: BotConfig, license_client: LicenseClient, symbol: str, positions: list[Any]) -> bool:
    if not config.basket_close_enabled or not positions:
        return False

    profits = [float(position.profit or 0.0) for position in positions]
    net_profit = sum(profits)
    gross_profit = sum(value for value in profits if value > 0)
    gross_loss = abs(sum(value for value in profits if value < 0))

    if config.basket_max_net_loss_money > 0 and net_profit <= -config.basket_max_net_loss_money:
        reason = f"basket stop loss net={net_profit:.2f}"
        print(f"[BASKET] Close all {symbol} positions | {reason}")
        for position in sorted(positions, key=lambda item: float(item.profit or 0.0)):
            close_position(config, license_client, position, reason)
        return True

    enough_positions_for_target = (
        config.basket_min_close_positions <= 0
        or len(positions) >= config.basket_min_close_positions
    )
    close_by_target = (
        enough_positions_for_target
        and net_profit >= config.basket_min_net_profit_money > 0
    )
    close_by_cover = (
        config.basket_profit_loss_ratio > 0
        and
        gross_loss > 0
        and net_profit > 0
        and gross_profit >= gross_loss * config.basket_profit_loss_ratio
    )
    if not close_by_target and not close_by_cover:
        return False

    reason = (
        f"basket net={net_profit:.2f} gross_profit={gross_profit:.2f} "
        f"gross_loss={gross_loss:.2f}"
    )
    print(f"[BASKET] Close all {symbol} positions | {reason}")
    for position in sorted(positions, key=lambda item: float(item.profit or 0.0), reverse=True):
        close_position(config, license_client, position, reason)
    return True


def manage_account_basket_profit(config: BotConfig, license_client: LicenseClient) -> bool:
    positions = all_bot_positions(config.magic)
    if not config.basket_close_enabled or not positions:
        return False

    profits = [float(position.profit or 0.0) for position in positions]
    net_profit = sum(profits)
    gross_profit = sum(value for value in profits if value > 0)
    gross_loss = abs(sum(value for value in profits if value < 0))

    close_by_loss = config.basket_max_net_loss_money > 0 and net_profit <= -config.basket_max_net_loss_money
    close_by_profit = config.basket_min_net_profit_money > 0 and net_profit >= config.basket_min_net_profit_money
    if not close_by_loss and not close_by_profit:
        return False

    reason = (
        f"account basket net={net_profit:.2f} gross_profit={gross_profit:.2f} "
        f"gross_loss={gross_loss:.2f}"
    )
    print(f"[BASKET] Close all account positions | {reason}")
    sort_reverse = close_by_profit
    for position in sorted(positions, key=lambda item: float(item.profit or 0.0), reverse=sort_reverse):
        close_position(config, license_client, position, reason)
    return True


def manage_open_positions(
    config: BotConfig,
    license_client: LicenseClient,
    symbol: str,
    signal: dict[str, Any] | None = None,
) -> None:
    positions = bot_positions(symbol, config.magic)
    if not positions:
        return

    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None or info.point <= 0:
        return

    reverse_signal = (signal or {}).get("signal")
    confidence = float((signal or {}).get("confidence", 0))

    if manage_basket_profit(config, license_client, symbol, positions):
        return

    for position in positions:
        direction = position_direction(position)
        profit_points = position_profit_points(symbol, position)
        age_seconds = position_age_seconds(position)
        profit_money = float(position.profit or 0.0)

        if config.close_losers_enabled:
            hit_money_stop = (
                config.loser_max_loss_money > 0
                and profit_money <= -config.loser_max_loss_money
            )
            hit_points_stop = (
                config.loser_max_loss_points > 0
                and profit_points <= -config.loser_max_loss_points
            )
            if hit_money_stop or hit_points_stop:
                close_position(
                    config,
                    license_client,
                    position,
                    f"loser stop money={profit_money:.2f} points={profit_points:.1f}",
                )
                continue

        if config.close_winners_enabled:
            if config.winner_max_profit_money > 0 and profit_money >= config.winner_max_profit_money:
                close_position(
                    config,
                    license_client,
                    position,
                    f"winner hard cap money={profit_money:.2f} >= {config.winner_max_profit_money:.2f}",
                )
                continue
            if (
                profit_money >= config.winner_min_profit_money
                and (
                    config.winner_min_profit_points <= 0
                    or profit_points >= config.winner_min_profit_points
                )
            ):
                close_position(
                    config,
                    license_client,
                    position,
                    f"winner take profit money={profit_money:.2f} points={profit_points:.1f}",
                )
                continue

        if config.close_on_reverse and reverse_signal in {"BUY", "SELL"}:
            if reverse_signal != direction and confidence >= config.min_confidence:
                close_position(config, license_client, position, f"reverse signal {reverse_signal}")
                continue

        if config.max_hold_seconds > 0 and age_seconds >= config.max_hold_seconds:
            close_position(config, license_client, position, f"max hold {age_seconds}s")
            continue

        new_sl: float | None = None
        current_tp = float(position.tp) if position.tp else None
        if profit_points >= config.trailing_start_points > 0:
            if direction == "BUY":
                new_sl = tick.bid - config.trailing_distance_points * info.point
                if position.sl and new_sl <= position.sl:
                    new_sl = None
            else:
                new_sl = tick.ask + config.trailing_distance_points * info.point
                if position.sl and new_sl >= position.sl:
                    new_sl = None
        elif profit_points >= config.breakeven_points > 0:
            if direction == "BUY" and (not position.sl or position.sl < position.price_open):
                new_sl = position.price_open
            if direction == "SELL" and (not position.sl or position.sl > position.price_open):
                new_sl = position.price_open

        if new_sl is not None:
            modify_position_sl_tp(symbol, position.ticket, round(new_sl, 5), current_tp, config.dry_run)


def send_order(
    config: BotConfig,
    license_client: LicenseClient,
    signal: dict[str, Any],
    orders_override: int | None = None,
    hedge_rebalance: bool = False,
) -> None:
    symbol = signal["symbol"]
    direction = signal["signal"]
    if direction not in {"BUY", "SELL"}:
        reason = str(signal.get("reason") or "Signal HOLD")
        print(f"[BOT] {symbol} HOLD | {reason}")
        report_runtime_status(config, license_client, symbol, signal, "hold", reason)
        return

    confidence = float(signal.get("confidence", 0))
    if confidence < config.min_confidence:
        reason = f"confidence {confidence:.2f} < {config.min_confidence:.2f}"
        print(f"[BOT] {symbol} skip | {reason}")
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
        return
    if not reentry_cooldown_allows(config, symbol, direction):
        report_runtime_status(config, license_client, symbol, signal, "skipped", "reentry cooldown")
        return
    session_allowed = trade_session_allows(config, symbol)
    if not session_allowed:
        reason = f"outside trade session {format_session_ranges(config.trade_sessions_utc)}"
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason, session_allowed=False)
        return
    if not news_allows_trading(config, license_client, symbol):
        report_runtime_status(config, license_client, symbol, signal, "skipped", "news filter blocked trading")
        return

    open_positions = bot_positions(symbol, config.magic)
    all_positions = all_bot_positions(config.magic)
    if len(open_positions) >= config.max_positions_per_symbol:
        reason = f"đã có {len(open_positions)} position magic={config.magic}, max={config.max_positions_per_symbol}"
        print(
            f"[BOT] {symbol} skip | {reason}"
        )
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
        return
    if len(all_positions) >= config.max_total_positions:
        reason = f"tổng position bot={len(all_positions)}, max={config.max_total_positions}"
        print(
            f"[BOT] {symbol} skip | {reason}"
        )
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
        return

    opposite_positions = [
        position for position in open_positions if position_direction(position) != direction
    ]
    if opposite_positions and not config.allow_hedging:
        reason = "đang có lệnh ngược, ALLOW_HEDGING=false"
        print(f"[BOT] {symbol} skip | {reason}")
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
        return

    same_direction_positions = [
        position for position in open_positions if position_direction(position) == direction
    ]
    last_age = seconds_since_last_position(same_direction_positions)
    if last_age is not None and last_age < config.min_order_spacing_seconds:
        reason = f"lệnh gần nhất mới {last_age}s < {config.min_order_spacing_seconds}s"
        print(
            f"[BOT] {symbol} skip | {reason}"
        )
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
        return

    same_direction_count = len(same_direction_positions)
    if same_direction_count > 0 and confidence < config.min_add_confidence:
        reason = f"confidence {confidence:.2f} < add threshold {config.min_add_confidence:.2f}"
        print(
            f"[BOT] {symbol} skip add | {reason}"
        )
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
        return

    signal_timeframe = str(signal.get("timeframe", config.timeframe)).upper()
    if signal_timeframe not in TIMEFRAMES:
        signal_timeframe = config.timeframe
    if not one_trade_per_bar_allows(config, symbol, direction, signal_timeframe):
        report_runtime_status(config, license_client, symbol, signal, "skipped", f"already traded {direction} on current {signal_timeframe} bar")
        return

    risk_allowed, risk_reason = risk_allows_new_order(config, symbol, signal, hedge_rebalance=hedge_rebalance)
    if not risk_allowed:
        report_runtime_status(config, license_client, symbol, signal, "skipped", risk_reason or "risk filter blocked")
        return

    spread = symbol_spread_points(symbol)
    if spread > config.max_spread_points:
        reason = f"spread {spread:.1f} > {config.max_spread_points:.1f} points"
        print(f"[BOT] {symbol} skip | {reason}")
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
        return

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    sl_price = signal.get("sl_price")
    tp_price = signal.get("tp_price")
    configured_orders = orders_override if orders_override is not None else config.orders_per_signal
    requested_orders = configured_orders if confidence >= config.batch_min_confidence else 1
    symbol_slots = config.max_positions_per_symbol - len(open_positions)
    total_slots = config.max_total_positions - len(all_positions)
    orders_to_send = max(0, min(requested_orders, symbol_slots, total_slots))
    if orders_to_send <= 0:
        reason = "không còn slot để mở batch order"
        print(f"[BOT] {symbol} skip | {reason}")
        report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
        return
    if requested_orders > 1:
        print(
            f"[BATCH] {symbol} {direction} | sending {orders_to_send}/{requested_orders} orders "
            f"confidence={confidence:.2f} threshold={config.batch_min_confidence:.2f}"
        )

    for batch_index in range(orders_to_send):
        current_spread = symbol_spread_points(symbol)
        if current_spread > config.max_spread_points:
            reason = f"spread {current_spread:.1f} > {config.max_spread_points:.1f} points"
            print(
                f"[BOT] {symbol} stop batch | {reason}"
            )
            report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
            return

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            reason = f"Không lấy được tick cho {symbol}"
            print(f"[MT5] {reason}")
            report_runtime_status(config, license_client, symbol, signal, "error", reason)
            return

        price = tick.ask if direction == "BUY" else tick.bid
        volume, lot_basis = order_volume(config, symbol, direction, signal)
        if volume <= 0:
            reason = f"lot basis={lot_basis} produced volume={volume}"
            print(f"[BOT] {symbol} skip | {reason}")
            report_runtime_status(config, license_client, symbol, signal, "skipped", reason)
            return

        print(
            f"[SIGNAL] {direction} {symbol} #{batch_index + 1}/{orders_to_send} | "
            f"entry={price} sl={sl_price} tp={tp_price} confidence={confidence:.2f} "
            f"prob={signal_probability(signal):.2f} risk={signal_risk(signal):.2f} "
            f"spread={current_spread:.1f} volume={volume} lot_basis={lot_basis}"
        )

        if config.dry_run:
            print("[DRY_RUN] Không gửi lệnh thật. Set DRY_RUN=false để bật auto trade.")
            report_runtime_status(config, license_client, symbol, signal, "dry_run", "Dry run: tín hiệu đạt, không gửi lệnh thật")
            continue

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": float(sl_price) if sl_price else 0.0,
            "tp": float(tp_price) if tp_price else 0.0,
            "deviation": config.deviation,
            "magic": config.magic,
            "comment": f"ForexBot AI batch {batch_index + 1}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            reason = f"order_send failed: {mt5.last_error()}"
            print(f"[MT5] {reason}")
            report_runtime_status(config, license_client, symbol, signal, "error", reason)
            return

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            reason = f"Order rejected | retcode={result.retcode} comment={result.comment}"
            print(f"[MT5] {reason}")
            report_runtime_status(config, license_client, symbol, signal, "rejected", reason)
            return

        position_ticket = result.order or result.deal
        ticket = str(position_ticket)
        print(f"[MT5] Order OK | ticket={ticket}")
        report_runtime_status(config, license_client, symbol, signal, "opened", f"Order OK ticket={ticket}")
        license_client.report_trade(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            entry_price=float(result.price or price),
            lot_size=volume,
            sl_price=float(sl_price) if sl_price else None,
            tp_price=float(tp_price) if tp_price else None,
            status="open",
            note=(
                f"AI batch {batch_index + 1}/{orders_to_send} {signal['trend']} "
                f"confidence={confidence:.2f} prob={signal_probability(signal):.2f} "
                f"risk={signal_risk(signal):.2f}: {signal['reason']}"
            ),
        )


def coerce_command_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


RUNTIME_CONFIG_FIELDS = {
    "lot_size": float,
    "loop_seconds": int,
    "max_spread_points": float,
    "min_confidence": float,
    "max_positions_per_symbol": int,
    "max_total_positions": int,
    "orders_per_signal": int,
    "force_both_sides": coerce_command_bool,
    "force_alternate_sides": coerce_command_bool,
    "allow_hedging": coerce_command_bool,
    "hedge_rebalance_enabled": coerce_command_bool,
    "hedge_rebalance_bypass_risk": coerce_command_bool,
    "batch_fixed_lot": coerce_command_bool,
    "close_losers_enabled": coerce_command_bool,
    "close_winners_enabled": coerce_command_bool,
    "basket_close_enabled": coerce_command_bool,
    "winner_min_profit_money": float,
    "winner_max_profit_money": float,
    "winner_min_profit_points": float,
    "loser_max_loss_money": float,
    "loser_max_loss_points": float,
    "basket_min_net_profit_money": float,
    "basket_max_net_loss_money": float,
    "basket_profit_loss_ratio": float,
    "max_equity_drawdown_percent": float,
    "max_daily_loss_percent": float,
    "max_symbol_floating_loss": float,
    "pyramid_lot_multiplier": float,
    "trend_lot_multiplier": float,
    "sideway_lot_multiplier": float,
    "counter_trend_lot_multiplier": float,
}


def apply_runtime_config(config: BotConfig, payload: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for key, value in payload.items():
        normalized_key = str(key).strip()
        if normalized_key == "symbols":
            if isinstance(value, str):
                symbols = [item.strip() for item in value.split(",") if item.strip()]
            elif isinstance(value, list):
                symbols = [str(item).strip() for item in value if str(item).strip()]
            else:
                raise ValueError("symbols phải là chuỗi hoặc list")
            if not symbols:
                raise ValueError("symbols không được rỗng")
            for symbol in symbols:
                ensure_symbol(symbol)
            config.symbols = symbols
            changed.append(f"symbols={','.join(symbols)}")
            continue

        converter = RUNTIME_CONFIG_FIELDS.get(normalized_key)
        if converter is None:
            continue
        converted = converter(value)
        setattr(config, normalized_key, converted)
        changed.append(f"{normalized_key}={converted}")
    return changed


def close_positions_by_command(
    config: BotConfig,
    license_client: LicenseClient,
    reason: str,
    symbol: str | None = None,
) -> int:
    positions = bot_positions(symbol, config.magic) if symbol else all_bot_positions(config.magic)
    closed_count = 0
    for position in sorted(positions, key=lambda item: float(item.profit or 0.0), reverse=True):
        if close_position(config, license_client, position, reason):
            closed_count += 1
    return closed_count


def process_bot_commands(
    config: BotConfig,
    license_client: LicenseClient,
    runtime_state: dict[str, Any],
) -> None:
    now = time.time()
    last_poll = float(runtime_state.get("last_command_poll", 0.0))
    if now - last_poll < config.command_poll_seconds:
        return
    runtime_state["last_command_poll"] = now

    commands = license_client.fetch_commands()
    for command in commands:
        command_id = int(command.get("id"))
        action = str(command.get("action") or "").lower()
        payload = command.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        try:
            if action == "pause":
                runtime_state["paused"] = True
                result = "Bot paused: new orders disabled, position management still running"
            elif action == "resume":
                runtime_state["paused"] = False
                result = "Bot resumed"
            elif action == "close_all":
                count = close_positions_by_command(config, license_client, "admin command close_all")
                result = f"Closed {count} bot positions"
            elif action == "close_symbol":
                symbol = str(command.get("symbol") or payload.get("symbol") or "").strip()
                if not symbol:
                    raise ValueError("close_symbol thiếu symbol")
                count = close_positions_by_command(
                    config,
                    license_client,
                    f"admin command close_symbol {symbol}",
                    symbol=symbol,
                )
                result = f"Closed {count} {symbol} positions"
            elif action == "set_config":
                changed = apply_runtime_config(config, payload)
                if not changed:
                    result = "No supported config keys changed"
                else:
                    result = "Updated " + ", ".join(changed)
            else:
                raise ValueError(f"Unsupported command action: {action}")

            print(f"[COMMAND] #{command_id} {action} done | {result}")
            license_client.ack_command(command_id, "done", result)
        except Exception as exc:
            result = str(exc)
            print(f"[COMMAND] #{command_id} {action} failed | {result}")
            license_client.ack_command(command_id, "failed", result)


def main() -> None:
    config = load_config()
    mt_account = config.mt_account or (str(config.mt5_login) if config.mt5_login else None)

    license_client = LicenseClient(
        server_url=config.server_url,
        license_key=config.license_key,
        mt_account=mt_account,
    )
    license_client.verify()

    connect_mt5(config)

    account = mt5.account_info()
    actual_mt_account = str(account.login) if account else None
    if mt_account and actual_mt_account and mt_account != actual_mt_account:
        print(f"[MT5] Sai tài khoản: license/script yêu cầu {mt_account}, terminal đang login {actual_mt_account}")
        mt5.shutdown()
        sys.exit(1)

    license_client.start_ping(interval_seconds=300)

    for symbol in config.symbols:
        ensure_symbol(symbol)
    sync_live_positions(config, license_client)

    print(
        f"[BOT] Running | symbols={','.join(config.symbols)} timeframe={config.timeframe} "
        f"ensemble={','.join(config.ensemble_timeframes)} strategy={config.strategy} "
        f"news_filter={config.news_filter_enabled} max_symbol_positions={config.max_positions_per_symbol} "
        f"max_total_positions={config.max_total_positions} orders_per_signal={config.orders_per_signal} "
        f"hedging={config.allow_hedging} force_both_sides={config.force_both_sides} "
        f"force_alternate_sides={config.force_alternate_sides} "
        f"hedge_rebalance={config.hedge_rebalance_enabled}/{config.hedge_rebalance_bypass_risk} "
        f"trend_filter={config.trend_filter_enabled} adx_period={config.adx_period} "
        f"adx_sideway_level={config.adx_sideway_level} "
        f"session_utc={format_session_ranges(config.trade_sessions_utc) if config.trade_session_enabled else 'disabled'} "
        f"one_trade_per_bar={config.one_trade_per_bar} "
        f"command_poll={config.command_poll_seconds}s "
        f"dry_run={config.dry_run}"
    )

    runtime_state: dict[str, Any] = {"paused": False, "last_command_poll": 0.0, "last_pause_log": 0.0}

    try:
        while True:
            process_bot_commands(config, license_client, runtime_state)
            sync_live_positions(config, license_client)
            if runtime_state.get("paused"):
                now = time.time()
                if now - float(runtime_state.get("last_pause_log", 0.0)) >= 30:
                    print("[COMMAND] Bot paused by admin | managing existing positions only")
                    runtime_state["last_pause_log"] = now
                manage_account_basket_profit(config, license_client)
                for symbol in config.symbols:
                    if ensure_symbol(symbol):
                        report_runtime_status(config, license_client, symbol, None, "paused", "Bot paused by command")
                        manage_open_positions(config, license_client, symbol, None)
                time.sleep(config.loop_seconds)
                continue

            if manage_account_basket_profit(config, license_client):
                time.sleep(config.loop_seconds)
                continue

            for symbol in config.symbols:
                if not ensure_symbol(symbol):
                    continue
                try:
                    signal = analyze_signal(config, license_client, symbol)
                    market_state = get_market_state(symbol, config)
                    signal = filter_signals(config, market_state, signal)
                    manage_open_positions(config, license_client, symbol, signal)
                    if (
                        len(bot_positions(symbol, config.magic)) >= config.max_positions_per_symbol
                        or len(all_bot_positions(config.magic)) >= config.max_total_positions
                    ):
                        report_runtime_status(
                            config,
                            license_client,
                            symbol,
                            signal,
                            "skipped",
                            "position limit reached before opening a new order",
                        )
                        continue
                    if config.force_both_sides:
                        if config.force_alternate_sides:
                            directions, rebalancing = forced_direction_order(config, symbol, signal)
                            stats = hedge_side_stats(symbol, config.magic)
                            if rebalancing:
                                print(
                                    f"[HEDGE] {symbol} rebalance priority={directions[0]} "
                                    f"BUY count={stats['BUY']['count']:.0f} lot={stats['BUY']['lot']:.2f} "
                                    f"loss={stats['BUY']['loss']:.2f} | "
                                    f"SELL count={stats['SELL']['count']:.0f} lot={stats['SELL']['lot']:.2f} "
                                    f"loss={stats['SELL']['loss']:.2f}"
                                )
                            else:
                                print(
                                    f"[FORCE] {symbol} alternating hedge orders "
                                    f"{'/'.join(directions)} count={config.orders_per_signal}"
                                )
                            for _ in range(config.orders_per_signal):
                                directions, rebalancing = forced_direction_order(config, symbol, signal)
                                for direction in directions:
                                    side_signal = filter_signals(
                                        config,
                                        market_state,
                                        forced_signal(config, symbol, direction, signal),
                                    )
                                    send_order(
                                        config,
                                        license_client,
                                        side_signal,
                                        orders_override=1,
                                        hedge_rebalance=rebalancing,
                                    )
                        else:
                            print(f"[FORCE] {symbol} opening hedge pair BUY+SELL regardless of signal={signal.get('signal')}")
                            buy_signal = filter_signals(config, market_state, forced_signal(config, symbol, "BUY", signal))
                            sell_signal = filter_signals(config, market_state, forced_signal(config, symbol, "SELL", signal))
                            send_order(config, license_client, buy_signal)
                            send_order(config, license_client, sell_signal)
                    else:
                        send_order(config, license_client, signal)
                except Exception as exc:
                    print(f"[BOT] {symbol} error: {exc}")
            time.sleep(config.loop_seconds)
    except KeyboardInterrupt:
        print("[BOT] Stopping...")
    finally:
        license_client.stop_ping()
        mt5.shutdown()


if __name__ == "__main__":
    main()
