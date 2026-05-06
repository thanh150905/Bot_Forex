"""
API Rate Limiting - Prevent abuse
"""

from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
from functools import wraps
import asyncio

from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse


class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests: Dict[str, list] = {}
    
    def _get_client_id(self, request: Request) -> str:
        """Get unique client identifier"""
        if request.client:
            return request.client.host
        return "unknown"
    
    async def check_rate_limit(
        self,
        request: Request,
        max_requests: int,
        window_seconds: int,
    ) -> Optional[HTTPException]:
        """
        Check if client exceeded rate limit
        
        Args:
            request: FastAPI request
            max_requests: Max requests allowed
            window_seconds: Time window
        
        Returns:
            HTTPException if limit exceeded, None otherwise
        """
        client_id = self._get_client_id(request)
        now = datetime.now(timezone.utc)
        
        # Initialize client history
        if client_id not in self.requests:
            self.requests[client_id] = []
        
        # Remove old requests outside window
        cutoff = now - timedelta(seconds=window_seconds)
        self.requests[client_id] = [
            ts for ts in self.requests[client_id]
            if ts > cutoff
        ]
        
        # Check limit
        if len(self.requests[client_id]) >= max_requests:
            return HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s",
            )
        
        # Record this request
        self.requests[client_id].append(now)
        return None
    
    def cleanup_old_entries(self, max_age_hours: int = 24):
        """Remove old client entries to free memory"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        clients_to_delete = []
        
        for client_id, timestamps in self.requests.items():
            # Keep if any timestamp is recent enough
            recent = [ts for ts in timestamps if ts > cutoff]
            if not recent:
                clients_to_delete.append(client_id)
        
        for client_id in clients_to_delete:
            del self.requests[client_id]


# Global rate limiter
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


# Middleware untuk apply rate limiting
class RateLimitMiddleware:
    """Rate limiting middleware"""
    
    def __init__(
        self,
        app,
        max_requests: int = 100,
        window_seconds: int = 60,
        exclude_paths: list = None,
    ):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exclude_paths = exclude_paths or ["/docs", "/openapi.json", "/redoc"]
        self.limiter = get_rate_limiter()
    
    async def __call__(self, request: Request, call_next):
        # Skip rate limiting for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        # Check rate limit
        exception = await self.limiter.check_rate_limit(
            request,
            self.max_requests,
            self.window_seconds,
        )
        
        if exception:
            return JSONResponse(
                status_code=exception.status_code,
                content={"detail": exception.detail},
            )
        
        return await call_next(request)


# Endpoint-specific rate limiting

async def rate_limit_endpoint(
    request: Request,
    max_requests: int,
    window_seconds: int,
) -> Optional[HTTPException]:
    """Check rate limit for specific endpoint"""
    limiter = get_rate_limiter()
    return await limiter.check_rate_limit(request, max_requests, window_seconds)


def rate_limit(max_requests: int, window_seconds: int):
    """Decorator for route rate limiting"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            if request:
                exception = await rate_limit_endpoint(request, max_requests, window_seconds)
                if exception:
                    raise exception
            return await func(*args, request=request, **kwargs)
        return wrapper
    return decorator


# Pre-defined rate limit profiles

RATE_LIMITS = {
    "public": {"max_requests": 30, "window_seconds": 60},      # 30 req/min
    "auth": {"max_requests": 10, "window_seconds": 300},       # 10 req/5min
    "bot": {"max_requests": 100, "window_seconds": 60},        # 100 req/min (bot allowed)
    "api": {"max_requests": 50, "window_seconds": 60},         # 50 req/min
    "strict": {"max_requests": 5, "window_seconds": 60},       # 5 req/min
}


async def apply_rate_limit(
    request: Request,
    profile: str = "public",
) -> Optional[HTTPException]:
    """Apply pre-defined rate limit profile"""
    if profile not in RATE_LIMITS:
        profile = "public"
    
    limits = RATE_LIMITS[profile]
    return await rate_limit_endpoint(
        request,
        limits["max_requests"],
        limits["window_seconds"],
    )
