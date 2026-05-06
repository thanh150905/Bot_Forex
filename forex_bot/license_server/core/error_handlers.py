"""
Global error handling + middleware
"""

import traceback
import json
from typing import Callable, Any
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio

from core.logger import app_logger, security_logger
from core.database import AsyncSessionLocal, AppLog
from datetime import datetime, timezone


async def log_app_event(
    level: str,
    module: str,
    message: str,
    context: dict = None,
):
    """Log event vào database"""
    try:
        async with AsyncSessionLocal() as session:
            log = AppLog(
                level=level,
                module=module,
                message=message,
                context=json.dumps(context) if context else None,
            )
            session.add(log)
            await session.commit()
    except Exception as e:
        app_logger.error(f"Failed to log event: {e}")


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware xử lý tất cả exceptions"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        try:
            response = await call_next(request)
            return response
        except RequestValidationError as e:
            app_logger.warning(f"Validation error: {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": "Validation error", "errors": str(e)},
            )
        except Exception as e:
            app_logger.error(f"Unhandled exception: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
            
            # Log to database
            await log_app_event(
                level="ERROR",
                module="middleware",
                message=f"{type(e).__name__}: {str(e)}",
                context={
                    "path": request.url.path,
                    "method": request.method,
                    "client_ip": request.client.host if request.client else "unknown",
                },
            )
            
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error", "error_id": id(e)},
            )


def safe_async(func: Callable) -> Callable:
    """Decorator để wrap async functions với error handling"""
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            app_logger.error(
                f"Error in {func.__name__}: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            )
            raise
    return wrapper


def safe_sync(func: Callable) -> Callable:
    """Decorator để wrap sync functions với error handling"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            app_logger.error(
                f"Error in {func.__name__}: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            )
            raise
    return wrapper


async def handle_db_error(error: Exception, operation: str = "database operation"):
    """Xử lý database errors"""
    app_logger.error(f"Database error during {operation}: {str(error)}")
    await log_app_event(
        level="ERROR",
        module="database",
        message=f"{operation}: {type(error).__name__}: {str(error)}",
    )


async def handle_http_error(
    error: Exception,
    url: str = "",
    method: str = "GET",
    retry: bool = True,
):
    """Xử lý HTTP request errors"""
    app_logger.warning(f"HTTP error ({method} {url}): {type(error).__name__}: {str(error)}")
    
    if retry:
        await asyncio.sleep(1)  # Retry sau 1 giây
    
    await log_app_event(
        level="WARNING",
        module="http",
        message=f"HTTP {method} {url} failed: {str(error)}",
    )
