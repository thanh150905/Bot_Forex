"""
Connection retry logic with exponential backoff
"""

import asyncio
import time
from typing import Callable, Optional, Any, Coroutine, TypeVar
from functools import wraps
import random

from core.logger import app_logger


T = TypeVar("T")


class RetryConfig:
    """Configuration for retry logic"""
    
    def __init__(
        self,
        max_attempts: int = 5,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        jitter: bool = True,
    ):
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number"""
        delay = self.initial_delay * (self.backoff_multiplier ** (attempt - 1))
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            # Add random jitter: ±20%
            jitter_amount = delay * 0.2
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(0, delay)


async def async_retry(
    func: Callable[..., Coroutine[Any, Any, T]],
    *args,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable] = None,
    **kwargs,
) -> T:
    """
    Retry async function with exponential backoff
    
    Args:
        func: Async function to retry
        args: Positional arguments
        config: RetryConfig (default: sensible defaults)
        on_retry: Callback on each retry
        kwargs: Keyword arguments
    
    Returns:
        Function result
    
    Raises:
        Last exception if all retries fail
    """
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt < config.max_attempts:
                delay = config.get_delay(attempt)
                app_logger.warning(
                    f"Attempt {attempt}/{config.max_attempts} failed: {type(e).__name__}: {str(e)}. "
                    f"Retrying in {delay:.1f}s..."
                )
                
                if on_retry:
                    on_retry(attempt, delay, e)
                
                await asyncio.sleep(delay)
            else:
                app_logger.error(
                    f"All {config.max_attempts} attempts failed: {type(e).__name__}: {str(e)}"
                )
    
    raise last_exception


def retry_async(config: Optional[RetryConfig] = None, on_retry: Optional[Callable] = None):
    """
    Decorator for async function retry
    
    Usage:
        @retry_async(config=RetryConfig(max_attempts=3))
        async def connect_to_server():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await async_retry(func, *args, config=config, on_retry=on_retry, **kwargs)
        return wrapper
    return decorator


def sync_retry(
    func: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable] = None,
    **kwargs,
) -> T:
    """Retry synchronous function with exponential backoff"""
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt < config.max_attempts:
                delay = config.get_delay(attempt)
                app_logger.warning(
                    f"Attempt {attempt}/{config.max_attempts} failed: {type(e).__name__}: {str(e)}. "
                    f"Retrying in {delay:.1f}s..."
                )
                
                if on_retry:
                    on_retry(attempt, delay, e)
                
                time.sleep(delay)
            else:
                app_logger.error(
                    f"All {config.max_attempts} attempts failed: {type(e).__name__}: {str(e)}"
                )
    
    raise last_exception


def retry(config: Optional[RetryConfig] = None, on_retry: Optional[Callable] = None):
    """Decorator for sync function retry"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return sync_retry(func, *args, config=config, on_retry=on_retry, **kwargs)
        return wrapper
    return decorator


# Specific retry helpers

async def retry_http_request(
    client,
    method: str,
    url: str,
    max_retries: int = 3,
    timeout: float = 10.0,
    **kwargs,
):
    """Retry HTTP request with specific error handling"""
    config = RetryConfig(
        max_attempts=max_retries,
        initial_delay=0.5,
        max_delay=10.0,
    )
    
    async def _request():
        return await client.request(method, url, timeout=timeout, **kwargs)
    
    return await async_retry(_request, config=config)


async def retry_db_transaction(
    db_session,
    operation: Callable,
    max_retries: int = 3,
):
    """Retry database transaction (handles deadlocks)"""
    config = RetryConfig(
        max_attempts=max_retries,
        initial_delay=0.1,
        max_delay=5.0,
    )
    
    async def _transaction():
        try:
            result = await operation(db_session)
            await db_session.commit()
            return result
        except Exception:
            await db_session.rollback()
            raise
    
    return await async_retry(_transaction, config=config)


async def retry_connection(
    connect_func: Callable,
    max_retries: int = 5,
    timeout: float = 30.0,
) -> Any:
    """Retry connection with specific timeout"""
    config = RetryConfig(
        max_attempts=max_retries,
        initial_delay=1.0,
        max_delay=30.0,
    )
    
    async def _connect():
        return await asyncio.wait_for(connect_func(), timeout=timeout)
    
    return await async_retry(_connect, config=config)


class ConnectionPool:
    """Simple connection pool with retry logic"""
    
    def __init__(self, create_connection: Callable, max_size: int = 5):
        self.create_connection = create_connection
        self.max_size = max_size
        self.connections = []
        self.lock = asyncio.Lock()
    
    async def get_connection(self, timeout: float = 30.0) -> Any:
        """Get connection from pool or create new one"""
        async with self.lock:
            # Return existing if available
            if self.connections:
                return self.connections.pop()
            
            # Create new if under limit
            if len(self.connections) < self.max_size:
                conn = await retry_connection(self.create_connection, timeout=timeout)
                return conn
        
        # Wait for connection to be available
        await asyncio.sleep(0.1)
        return await self.get_connection(timeout)
    
    async def return_connection(self, connection: Any):
        """Return connection to pool"""
        async with self.lock:
            if len(self.connections) < self.max_size:
                self.connections.append(connection)
            else:
                # Close if pool is full
                try:
                    await connection.close()
                except:
                    pass
    
    async def close_all(self):
        """Close all connections"""
        async with self.lock:
            for conn in self.connections:
                try:
                    await conn.close()
                except:
                    pass
            self.connections.clear()
