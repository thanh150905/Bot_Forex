"""
Unit tests for core modules
Run with: pytest tests/ -v
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Test Risk Manager
from bot_client.risk_manager import RiskManager, RiskConfig, Position


class TestRiskManager:
    """Test risk management"""
    
    @pytest.fixture
    def risk_manager(self):
        config = RiskConfig(
            account_balance=10000,
            max_positions_per_symbol=3,
            max_total_positions=10,
        )
        return RiskManager(config)
    
    def test_add_position_success(self, risk_manager):
        """Test adding position within limits"""
        pos = Position(
            ticket="1",
            symbol="EURUSD",
            direction="BUY",
            entry_price=1.0850,
            lot_size=0.1,
            opened_at=datetime.now(timezone.utc),
        )
        
        allowed, msg = risk_manager.add_position(pos)
        assert allowed, msg
        assert len(risk_manager.positions) == 1
    
    def test_max_positions_per_symbol(self, risk_manager):
        """Test max positions per symbol enforcement"""
        for i in range(4):
            pos = Position(
                ticket=str(i),
                symbol="EURUSD",
                direction="BUY",
                entry_price=1.0850,
                lot_size=0.1,
                opened_at=datetime.now(timezone.utc),
            )
            allowed, msg = risk_manager.add_position(pos)
            
            if i < 3:
                assert allowed
            else:
                assert not allowed
    
    def test_lot_size_calculation(self, risk_manager):
        """Test lot size based on confidence"""
        lot_bullish = risk_manager.calculate_lot_size(0.9, "trending_up")
        lot_bearish = risk_manager.calculate_lot_size(0.9, "trending_down")
        lot_ranging = risk_manager.calculate_lot_size(0.9, "ranging")
        
        assert lot_bullish > lot_bearish
        assert lot_bullish > lot_ranging
    
    def test_equity_drawdown(self, risk_manager):
        """Test equity and drawdown calculation"""
        stats = risk_manager.get_statistics()
        
        assert stats["equity"] == 10000
        assert stats["drawdown_percent"] == 0


# Test Trade Analytics
from bot_client.trade_analytics import TradeAnalytics, Trade


class TestTradeAnalytics:
    """Test trade history tracking"""
    
    @pytest.fixture
    def analytics(self):
        return TradeAnalytics()
    
    def test_add_trade(self, analytics):
        """Test adding trade"""
        trade = Trade(
            ticket="1",
            symbol="EURUSD",
            direction="BUY",
            entry_price=1.0850,
            entry_time=datetime.now(timezone.utc),
            lot_size=0.1,
        )
        
        analytics.add_trade(trade)
        assert len(analytics.trades) == 1
    
    def test_close_trade(self, analytics):
        """Test closing trade"""
        trade = Trade(
            ticket="1",
            symbol="EURUSD",
            direction="BUY",
            entry_price=1.0850,
            entry_time=datetime.now(timezone.utc),
            lot_size=1.0,
        )
        
        analytics.add_trade(trade)
        result = analytics.close_trade("1", 1.0950, "TP")
        
        assert result is not None
        assert result.status == "closed"
        assert result.profit_loss > 0
    
    def test_statistics(self, analytics):
        """Test statistics calculation"""
        # Add winning trade
        trade1 = Trade(
            ticket="1",
            symbol="EURUSD",
            direction="BUY",
            entry_price=1.0850,
            entry_time=datetime.now(timezone.utc),
            lot_size=1.0,
        )
        analytics.add_trade(trade1)
        analytics.close_trade("1", 1.0950, "TP")
        
        # Add losing trade
        trade2 = Trade(
            ticket="2",
            symbol="EURUSD",
            direction="SELL",
            entry_price=1.0950,
            entry_time=datetime.now(timezone.utc),
            lot_size=1.0,
        )
        analytics.add_trade(trade2)
        analytics.close_trade("2", 1.0900, "SL")
        
        stats = analytics.get_statistics()
        
        assert stats["closed_trades"] == 2
        assert stats["wins"] == 1
        assert stats["losses"] == 1
        assert stats["win_rate"] == 50.0


# Test Database Backup
from license_server.core.backup import DatabaseBackup


class TestDatabaseBackup:
    """Test backup functionality"""
    
    @pytest.fixture
    def backup_manager(self, tmp_path):
        db_path = tmp_path / "test.db"
        db_path.touch()
        return DatabaseBackup(db_path, tmp_path / "backups")
    
    def test_backup_creation(self, backup_manager):
        """Test creating backup"""
        result = asyncio.run(backup_manager.create_backup(compress=True))
        
        assert result is not None
        assert result.exists()
        assert result.suffix == ".gz"
    
    def test_list_backups(self, backup_manager):
        """Test listing backups"""
        asyncio.run(backup_manager.create_backup(compress=True))
        backups = backup_manager.list_backups()
        
        assert len(backups) > 0
        assert "name" in backups[0]
        assert "size" in backups[0]


# Test Rate Limiter
from license_server.core.rate_limiter import RateLimiter, RATE_LIMITS
from fastapi import Request
from unittest.mock import Mock


class TestRateLimiter:
    """Test rate limiting"""
    
    @pytest.fixture
    def limiter(self):
        return RateLimiter()
    
    @pytest.mark.asyncio
    async def test_rate_limit_allowed(self, limiter):
        """Test rate limit when under threshold"""
        request = Mock(spec=Request)
        request.client.host = "127.0.0.1"
        
        exception = await limiter.check_rate_limit(request, max_requests=5, window_seconds=60)
        assert exception is None
    
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, limiter):
        """Test rate limit when exceeded"""
        request = Mock(spec=Request)
        request.client.host = "127.0.0.1"
        
        # Max out the limit
        for _ in range(3):
            await limiter.check_rate_limit(request, max_requests=2, window_seconds=60)
        
        # This should fail
        exception = await limiter.check_rate_limit(request, max_requests=2, window_seconds=60)
        assert exception is not None


# Test Retry Logic
from license_server.core.retry_logic import RetryConfig, sync_retry


class TestRetryLogic:
    """Test retry mechanism"""
    
    def test_retry_success_on_first_attempt(self):
        """Test function succeeds on first attempt"""
        call_count = 0
        
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = sync_retry(
            test_func,
            config=RetryConfig(max_attempts=3),
        )
        
        assert result == "success"
        assert call_count == 1
    
    def test_retry_succeeds_after_failures(self):
        """Test function succeeds after retries"""
        call_count = 0
        
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"
        
        result = sync_retry(
            test_func,
            config=RetryConfig(max_attempts=5, initial_delay=0.01),
        )
        
        assert result == "success"
        assert call_count == 3
    
    def test_retry_exhaustion(self):
        """Test retries are exhausted"""
        def test_func():
            raise Exception("Persistent failure")
        
        with pytest.raises(Exception):
            sync_retry(
                test_func,
                config=RetryConfig(max_attempts=2, initial_delay=0.01),
            )


# Test Email Utils
from license_server.core.email_utils import send_code_email, is_smtp_configured


class TestEmailUtils:
    """Test email functionality"""
    
    @pytest.mark.asyncio
    async def test_smtp_configured_check(self):
        """Test SMTP configuration check"""
        # This will return False if not configured
        result = is_smtp_configured()
        assert isinstance(result, bool)
    
    @pytest.mark.asyncio
    async def test_send_code_email_no_smtp(self):
        """Test email send fails gracefully without SMTP"""
        # Should handle gracefully when SMTP not configured
        result = await send_code_email("test@example.com", "123456", "user_login")
        # Result depends on SMTP config, but shouldn't crash
        assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
