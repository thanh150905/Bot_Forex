"""
Offline backtest for the rule-based AI strategies.

Input CSV columns: time, open, high, low, close, volume
Example:
  python backtest_strategy.py --csv data/XAUUSDm_M1.csv --strategy scalping --bars 100
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1] / "license_server"
sys.path.insert(0, str(SERVER_DIR))

from ai_engine.indicators import Candle  # noqa: E402
from ai_engine.scalping import classify_scalping  # noqa: E402
from ai_engine.trend import classify_trend  # noqa: E402


@dataclass
class Position:
    direction: str
    entry: float
    sl: float | None
    tp: float | None
    opened_index: int


def load_candles(path: Path) -> list[Candle]:
    candles: list[Candle] = []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candles.append(
                Candle(
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                    time=row.get("time"),
                )
            )
    return candles


def classify(candles: list[Candle], strategy: str):
    if strategy == "scalping":
        return classify_scalping(candles)
    return classify_trend(candles)


def exit_position(position: Position, candle: Candle, max_hold_bars: int, index: int) -> tuple[bool, float, str]:
    if position.direction == "BUY":
        if position.sl and candle.low <= position.sl:
            return True, position.sl, "sl"
        if position.tp and candle.high >= position.tp:
            return True, position.tp, "tp"
    else:
        if position.sl and candle.high >= position.sl:
            return True, position.sl, "sl"
        if position.tp and candle.low <= position.tp:
            return True, position.tp, "tp"

    if max_hold_bars > 0 and index - position.opened_index >= max_hold_bars:
        return True, candle.close, "time"
    return False, candle.close, ""


def pnl_points(position: Position, exit_price: float, point: float) -> float:
    if position.direction == "BUY":
        return (exit_price - position.entry) / point
    return (position.entry - exit_price) / point


def run_backtest(args: argparse.Namespace) -> dict[str, float | int]:
    candles = load_candles(Path(args.csv))
    if len(candles) < args.bars + 2:
        raise SystemExit("Not enough candles for selected bars window")

    trades = []
    position: Position | None = None
    equity_points = 0.0
    peak_equity = 0.0
    max_drawdown = 0.0

    for index in range(args.bars, len(candles)):
        candle = candles[index]
        if position:
            should_exit, exit_price, reason = exit_position(position, candle, args.max_hold_bars, index)
            if should_exit:
                points = pnl_points(position, exit_price, args.point)
                equity_points += points - args.spread_points
                peak_equity = max(peak_equity, equity_points)
                max_drawdown = max(max_drawdown, peak_equity - equity_points)
                trades.append(points - args.spread_points)
                position = None
                if args.verbose:
                    print(f"close {reason} points={points - args.spread_points:.1f}")

        if position:
            continue

        result = classify(candles[index - args.bars:index], args.strategy)
        probability = float(result.indicators.get("estimated_probability", result.confidence))
        risk = float(result.indicators.get("risk_score", 1.0 - result.confidence))
        if result.signal not in {"BUY", "SELL"}:
            continue
        if result.confidence < args.min_confidence:
            continue
        if probability < args.min_probability:
            continue
        if risk > args.max_risk:
            continue

        position = Position(
            direction=result.signal,
            entry=candle.close,
            sl=result.sl_price,
            tp=result.tp_price,
            opened_index=index,
        )
        if args.verbose:
            print(f"open {result.signal} entry={candle.close} confidence={result.confidence:.2f}")

    wins = [value for value in trades if value > 0]
    losses = [value for value in trades if value <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "candles": len(candles),
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_percent": round(len(wins) / len(trades) * 100, 2) if trades else 0,
        "net_points": round(sum(trades), 1),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else 0,
        "max_drawdown_points": round(max_drawdown, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--strategy", choices=["scalping", "trend"], default="scalping")
    parser.add_argument("--bars", type=int, default=100)
    parser.add_argument("--point", type=float, default=0.01)
    parser.add_argument("--spread-points", type=float, default=30)
    parser.add_argument("--max-hold-bars", type=int, default=20)
    parser.add_argument("--min-confidence", type=float, default=0.68)
    parser.add_argument("--min-probability", type=float, default=0.58)
    parser.add_argument("--max-risk", type=float, default=0.55)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    result = run_backtest(args)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
