"""
Trade history tracking and analytics
"""

from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
import statistics
import json

from core.logger import bot_logger


@dataclass
class Trade:
    """Trade record"""
    ticket: str
    symbol: str
    direction: str                    # BUY / SELL
    entry_price: float
    entry_time: datetime
    lot_size: float
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    profit_loss: Optional[float] = None
    pips: Optional[float] = None
    reason: Optional[str] = None      # "TP", "SL", "Manual", "Risk"
    status: str = "open"              # open, closed, cancelled
    
    @property
    def duration(self) -> Optional[timedelta]:
        """How long trade was open"""
        if self.exit_time and self.entry_time:
            return self.exit_time - self.entry_time
        return None
    
    @property
    def is_profitable(self) -> Optional[bool]:
        """Is trade profitable?"""
        if self.profit_loss is None:
            return None
        return self.profit_loss > 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        d = asdict(self)
        d['entry_time'] = self.entry_time.isoformat()
        d['exit_time'] = self.exit_time.isoformat() if self.exit_time else None
        d['duration'] = str(self.duration) if self.duration else None
        return d


class TradeAnalytics:
    """Trade history tracking and analysis"""
    
    def __init__(self):
        self.trades: List[Trade] = []
        self.session_start = datetime.now(timezone.utc)
    
    def add_trade(self, trade: Trade):
        """Add trade to history"""
        self.trades.append(trade)
    
    def close_trade(
        self,
        ticket: str,
        exit_price: float,
        reason: str = "Manual",
        pips: Optional[float] = None,
    ) -> Optional[Trade]:
        """Close a trade"""
        for trade in self.trades:
            if trade.ticket == ticket and trade.status == "open":
                trade.exit_price = exit_price
                trade.exit_time = datetime.now(timezone.utc)
                trade.reason = reason
                trade.status = "closed"
                
                # Calculate P&L
                if trade.direction == "BUY":
                    trade.profit_loss = (exit_price - trade.entry_price) * trade.lot_size * 100_000
                else:  # SELL
                    trade.profit_loss = (trade.entry_price - exit_price) * trade.lot_size * 100_000
                
                trade.pips = pips
                
                bot_logger.info(f"Trade closed: {trade.symbol} {reason} | P&L: ${trade.profit_loss:+.2f}")
                return trade
        
        return None
    
    def get_statistics(self, period: Optional[timedelta] = None) -> Dict:
        """
        Get trading statistics
        
        Args:
            period: Filter trades within period (e.g., timedelta(days=1))
        
        Returns:
            Statistics dictionary
        """
        # Filter by period
        if period:
            cutoff = datetime.now(timezone.utc) - period
            trades = [t for t in self.trades if t.entry_time >= cutoff]
        else:
            trades = self.trades
        
        if not trades:
            return self._empty_stats()
        
        # Closed trades
        closed_trades = [t for t in trades if t.status == "closed"]
        
        if not closed_trades:
            return {
                **self._empty_stats(),
                "total_trades": len(trades),
                "open_trades": len(trades),
            }
        
        # Calculate stats
        wins = [t for t in closed_trades if t.is_profitable]
        losses = [t for t in closed_trades if t.is_profitable == False]
        
        win_loss_amounts = [t.profit_loss for t in wins]
        loss_amounts = [t.profit_loss for t in losses]
        
        total_profit = sum(win_loss_amounts)
        total_loss = sum(loss_amounts)
        total_pnl = total_profit + total_loss
        
        durations = [t.duration.total_seconds() for t in closed_trades if t.duration]
        
        stats = {
            "total_trades": len(trades),
            "closed_trades": len(closed_trades),
            "open_trades": len([t for t in trades if t.status == "open"]),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(closed_trades) * 100) if closed_trades else 0,
            "total_profit": total_profit,
            "total_loss": total_loss,
            "total_pnl": total_pnl,
            "avg_win": statistics.mean(win_loss_amounts) if win_loss_amounts else 0,
            "avg_loss": statistics.mean(loss_amounts) if loss_amounts else 0,
            "best_trade": max(win_loss_amounts) if win_loss_amounts else 0,
            "worst_trade": min(loss_amounts) if loss_amounts else 0,
            "profit_factor": total_profit / abs(total_loss) if total_loss < 0 else float('inf') if total_profit > 0 else 0,
            "avg_duration": statistics.mean(durations) if durations else 0,
            "consecutive_wins": self._consecutive_wins(),
            "consecutive_losses": self._consecutive_losses(),
            "max_drawdown": self._calculate_max_drawdown(),
        }
        
        return stats
    
    def get_daily_statistics(self, days: int = 7) -> List[Dict]:
        """Get daily breakdown for last N days"""
        daily_stats = {}
        
        for trade in self.trades:
            day = trade.entry_time.date()
            if day not in daily_stats:
                daily_stats[day] = []
            daily_stats[day].append(trade)
        
        result = []
        for day in sorted(daily_stats.keys(), reverse=True)[:days]:
            day_trades = daily_stats[day]
            closed = [t for t in day_trades if t.status == "closed"]
            
            if not closed:
                continue
            
            wins = [t for t in closed if t.is_profitable]
            losses = [t for t in closed if t.is_profitable == False]
            
            day_pnl = sum(t.profit_loss for t in closed if t.profit_loss)
            
            result.append({
                "date": str(day),
                "trades": len(closed),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": (len(wins) / len(closed) * 100) if closed else 0,
                "pnl": day_pnl,
            })
        
        return result
    
    def get_symbol_statistics(self, symbol: str) -> Dict:
        """Get statistics for specific symbol"""
        symbol_trades = [t for t in self.trades if t.symbol == symbol]
        
        if not symbol_trades:
            return {}
        
        closed = [t for t in symbol_trades if t.status == "closed"]
        if not closed:
            return {"symbol": symbol, "trades": len(symbol_trades), "status": "open_only"}
        
        wins = [t for t in closed if t.is_profitable]
        total_pnl = sum(t.profit_loss for t in closed if t.profit_loss)
        
        return {
            "symbol": symbol,
            "total_trades": len(symbol_trades),
            "closed_trades": len(closed),
            "wins": len(wins),
            "loss_rate": ((len(closed) - len(wins)) / len(closed) * 100) if closed else 0,
            "total_pnl": total_pnl,
        }
    
    def export_trades(self) -> str:
        """Export trades as JSON"""
        trades_dicts = [t.to_dict() for t in self.trades]
        return json.dumps(trades_dicts, indent=2)
    
    def _empty_stats(self) -> Dict:
        """Empty statistics template"""
        return {
            "total_trades": 0,
            "closed_trades": 0,
            "open_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "total_profit": 0,
            "total_loss": 0,
            "total_pnl": 0,
            "profit_factor": 0,
            "max_drawdown": 0,
        }
    
    def _consecutive_wins(self) -> int:
        """Get current consecutive wins"""
        count = 0
        closed_trades = [t for t in reversed(self.trades) if t.status == "closed"]
        
        for trade in closed_trades:
            if trade.is_profitable:
                count += 1
            else:
                break
        
        return count
    
    def _consecutive_losses(self) -> int:
        """Get current consecutive losses"""
        count = 0
        closed_trades = [t for t in reversed(self.trades) if t.status == "closed"]
        
        for trade in closed_trades:
            if not trade.is_profitable:
                count += 1
            else:
                break
        
        return count
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate max drawdown from equity curve"""
        if not self.trades:
            return 0
        
        closed_trades = [t for t in self.trades if t.status == "closed" and t.profit_loss]
        if not closed_trades:
            return 0
        
        equity_curve = [0]
        for trade in sorted(closed_trades, key=lambda t: t.exit_time or datetime.now(timezone.utc)):
            equity_curve.append(equity_curve[-1] + trade.profit_loss)
        
        peak = 0
        max_dd = 0
        
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd
        
        return max_dd
