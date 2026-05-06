"""
Risk Management Module for Forex Bot
Quản lý: Position sizing, Max DD, Daily loss, Max positions, Basket management
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from datetime import datetime, timezone


@dataclass
class Position:
    """Một position đang mở"""
    ticket: str
    symbol: str
    direction: str           # "BUY" | "SELL"
    entry_price: float
    lot_size: float
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    floating_profit: float = 0.0
    

@dataclass
class RiskConfig:
    """Risk management configuration"""
    account_balance: float = 10000.0              # Balance khởi đầu
    max_equity_drawdown_percent: float = 20.0     # Max DD từ equity peak: 20%
    max_daily_loss_percent: float = 5.0           # Max daily loss: 5%
    max_symbol_floating_loss: float = 500.0       # Max floating loss per symbol: 500$
    max_positions_per_symbol: int = 3             # Max 3 positions per symbol
    max_total_positions: int = 10                 # Max 10 total positions
    lot_multiplier_uptrend: float = 1.5           # Lot multiplier in uptrend
    lot_multiplier_downtrend: float = 1.0         # Lot multiplier in downtrend
    lot_multiplier_sideway: float = 0.7           # Lot multiplier when ranging
    min_lot_size: float = 0.01                    # Min lot size
    max_lot_size: float = 5.0                     # Max lot size
    risk_per_trade_percent: float = 2.0           # Risk 2% per trade (via position sizing)


@dataclass
class PortfolioMetrics:
    """Portfolio metrics"""
    current_balance: float = 0.0
    total_equity: float = 0.0
    floating_profit: float = 0.0
    total_positions: int = 0
    symbols_with_positions: dict = field(default_factory=dict)  # {symbol: [positions]}
    daily_loss: float = 0.0
    peak_equity: float = 0.0
    current_drawdown_percent: float = 0.0


class RiskManager:
    """
    Quản lý risk cho bot
    """
    
    def __init__(self, config: RiskConfig):
        self.config = config
        self.positions: List[Position] = []
        self.metrics = PortfolioMetrics(
            current_balance=config.account_balance,
            total_equity=config.account_balance,
            peak_equity=config.account_balance,
        )
        self.daily_loss = 0.0
        self.session_start_time = datetime.now(timezone.utc)
        
    def add_position(self, position: Position) -> Tuple[bool, str]:
        """
        Thêm position mới, với checks
        
        Returns:
            (is_allowed, reason)
        """
        # Check 1: Max positions per symbol
        symbol_positions = [p for p in self.positions if p.symbol == position.symbol]
        if len(symbol_positions) >= self.config.max_positions_per_symbol:
            return False, f"Max {self.config.max_positions_per_symbol} positions for {position.symbol} reached"
        
        # Check 2: Max total positions
        if len(self.positions) >= self.config.max_total_positions:
            return False, f"Max {self.config.max_total_positions} total positions reached"
        
        # Check 3: Symbol floating loss limit
        symbol_floating_loss = sum(p.floating_profit for p in symbol_positions)
        if symbol_floating_loss + position.floating_profit < -self.config.max_symbol_floating_loss:
            return False, f"Symbol {position.symbol} max floating loss limit would be exceeded"
        
        # Check 4: Equity drawdown
        if self._would_exceed_equity_dd(position):
            return False, f"Max equity drawdown limit ({self.config.max_equity_drawdown_percent}%) would be exceeded"
        
        # Check 5: Daily loss limit
        if self._would_exceed_daily_loss():
            return False, f"Daily loss limit ({self.config.max_daily_loss_percent}%) reached for today"
        
        self.positions.append(position)
        return True, "Position added successfully"
    
    def close_position(self, ticket: str, close_price: float) -> Optional[float]:
        """
        Đóng position bằng ticket
        
        Returns:
            Profit/loss or None if not found
        """
        position = None
        for i, p in enumerate(self.positions):
            if p.ticket == ticket:
                position = p
                self.positions.pop(i)
                break
        
        if not position:
            return None
        
        # Calculate P&L
        if position.direction == "BUY":
            pnl = (close_price - position.entry_price) * position.lot_size * 100_000
        else:  # SELL
            pnl = (position.entry_price - close_price) * position.lot_size * 100_000
        
        self.daily_loss += pnl
        return pnl
    
    def update_floating(self, ticket: str, current_price: float):
        """Cập nhật floating profit/loss cho position"""
        for p in self.positions:
            if p.ticket == ticket:
                if p.direction == "BUY":
                    p.floating_profit = (current_price - p.entry_price) * p.lot_size * 100_000
                else:  # SELL
                    p.floating_profit = (p.entry_price - current_price) * p.lot_size * 100_000
                break
    
    def get_equity(self) -> float:
        """Calculate current equity"""
        total_floating = sum(p.floating_profit for p in self.positions)
        return self.metrics.current_balance + total_floating
    
    def calculate_lot_size(self, signal_confidence: float, trend: str) -> float:
        """
        Tính lot size dựa trên confidence + trend
        
        Args:
            signal_confidence: Confidence [0.0, 1.0]
            trend: "trending_up", "trending_down", "ranging"
        
        Returns:
            Adjusted lot size
        """
        base_lot = self.config.min_lot_size
        
        # Apply trend multiplier
        if trend == "trending_up":
            base_lot *= self.config.lot_multiplier_uptrend
        elif trend == "trending_down":
            base_lot *= self.config.lot_multiplier_downtrend
        else:  # ranging
            base_lot *= self.config.lot_multiplier_sideway
        
        # Apply confidence adjustment (higher confidence = larger position)
        confidence_adjusted = base_lot * (0.5 + confidence)  # 0.5x to 1.5x
        
        # Clamp to [min, max]
        return max(self.config.min_lot_size, min(self.config.max_lot_size, confidence_adjusted))
    
    def should_close_losers(self) -> List[str]:
        """
        Identify losing positions that should be closed
        
        Returns:
            List of tickets to close
        """
        to_close = []
        for p in self.positions:
            if p.floating_profit < -self.config.max_symbol_floating_loss * 0.5:  # Close if loss > 50% of limit
                to_close.append(p.ticket)
        return to_close
    
    def should_take_profits(self, tp_percent: float = 50.0) -> List[str]:
        """
        Identify winning positions that reached TP
        
        Args:
            tp_percent: Take profit after X% of TP reached
        
        Returns:
            List of tickets to close
        """
        to_close = []
        for p in self.positions:
            if p.tp_price is None:
                continue
            
            if p.direction == "BUY":
                price_to_tp = p.tp_price - p.entry_price
                current_to_entry = p.tp_price - p.entry_price  # Assumed we're at TP
                if current_to_entry >= price_to_tp * (tp_percent / 100.0):
                    to_close.append(p.ticket)
            else:  # SELL
                price_to_tp = p.entry_price - p.tp_price
                if price_to_tp >= price_to_tp * (tp_percent / 100.0):
                    to_close.append(p.ticket)
        
        return to_close
    
    def get_statistics(self) -> dict:
        """Get current portfolio statistics"""
        equity = self.get_equity()
        peak_equity = max(equity, self.metrics.peak_equity)
        drawdown = ((peak_equity - equity) / peak_equity) * 100 if peak_equity > 0 else 0
        
        total_floating = sum(p.floating_profit for p in self.positions)
        
        return {
            "balance": self.metrics.current_balance,
            "equity": equity,
            "floating_profit": total_floating,
            "peak_equity": peak_equity,
            "drawdown_percent": drawdown,
            "daily_loss": self.daily_loss,
            "open_positions": len(self.positions),
            "max_positions": self.config.max_total_positions,
        }
    
    def _would_exceed_equity_dd(self, new_position: Position) -> bool:
        """Check if new position would breach max DD"""
        current_equity = self.get_equity()
        potential_loss = abs(min(0, new_position.floating_profit))
        new_equity = current_equity - potential_loss
        
        peak = self.metrics.peak_equity
        if peak <= 0:
            return False
        
        max_dd_amount = peak * (self.config.max_equity_drawdown_percent / 100.0)
        return (peak - new_equity) > max_dd_amount
    
    def _would_exceed_daily_loss(self) -> bool:
        """Check if already hit daily loss limit"""
        max_daily_loss = self.metrics.current_balance * (self.config.max_daily_loss_percent / 100.0)
        return self.daily_loss < -max_daily_loss
    
    def reset_daily_metrics(self):
        """Call this at end of trading day"""
        self.daily_loss = 0.0
        self.session_start_time = datetime.now(timezone.utc)


# Helper functions

def calculate_atr_based_lot(
    atr: float,
    current_price: float,
    account_balance: float,
    risk_percent: float = 2.0,
    pip_value: float = 10.0,  # XAU = $10 per pip
) -> float:
    """
    Calculate lot size based on ATR and risk per trade
    
    Args:
        atr: Average True Range
        current_price: Current price
        account_balance: Account balance
        risk_percent: Risk per trade (%)
        pip_value: Value per pip
    
    Returns:
        Recommended lot size
    """
    risk_amount = account_balance * (risk_percent / 100.0)
    sl_distance_pips = (atr / current_price) * 10_000
    
    if sl_distance_pips <= 0:
        return 0.01
    
    lot_size = risk_amount / (sl_distance_pips * pip_value)
    
    # Clamp to reasonable range
    return max(0.01, min(5.0, lot_size))
