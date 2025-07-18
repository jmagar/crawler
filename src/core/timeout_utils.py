"""
Timeout utility functions for handling async operations with configurable timeouts.
Provides centralized timeout management with environment variable configuration.
"""
import asyncio
import os
import time
import logging
from typing import TypeVar, Awaitable, Optional, Union
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')

class TimeoutConfig:
    """Centralized timeout configuration with environment variable support."""
    
    # Crawling timeouts (seconds)
    CRAWLER_PAGE_TIMEOUT = float(os.getenv("CRAWLER_PAGE_TIMEOUT", "300"))
    CRAWLER_BATCH_TIMEOUT = float(os.getenv("CRAWLER_BATCH_TIMEOUT", "1800"))
    CRAWLER_RECURSIVE_TIMEOUT = float(os.getenv("CRAWLER_RECURSIVE_TIMEOUT", "3600"))
    CRAWLER_SITEMAP_TIMEOUT = float(os.getenv("CRAWLER_SITEMAP_TIMEOUT", "60"))
    CRAWLER_DIRECTORY_TIMEOUT = float(os.getenv("CRAWLER_DIRECTORY_TIMEOUT", "600"))
    
    # Browser timeouts (milliseconds for crawl4ai compatibility)
    BROWSER_PAGE_TIMEOUT = int(os.getenv("BROWSER_PAGE_TIMEOUT", "300000"))
    BROWSER_WAIT_FOR_TIMEOUT = int(os.getenv("BROWSER_WAIT_FOR_TIMEOUT", "30000"))
    BROWSER_NAVIGATION_TIMEOUT = int(os.getenv("BROWSER_NAVIGATION_TIMEOUT", "60000"))
    
    # Database timeouts (seconds)
    QDRANT_OPERATION_TIMEOUT = float(os.getenv("QDRANT_OPERATION_TIMEOUT", "30"))
    QDRANT_BATCH_TIMEOUT = float(os.getenv("QDRANT_BATCH_TIMEOUT", "120"))
    QDRANT_SCROLL_TIMEOUT = float(os.getenv("QDRANT_SCROLL_TIMEOUT", "60"))
    
    # Server and process timeouts (seconds)
    SERVER_CLEANUP_TIMEOUT = float(os.getenv("SERVER_CLEANUP_TIMEOUT", "30"))
    PROCESS_POOL_TIMEOUT = float(os.getenv("PROCESS_POOL_TIMEOUT", "60"))
    MCP_TOOL_TIMEOUT = float(os.getenv("MCP_TOOL_TIMEOUT", "600"))
    
    # HTTP timeouts (seconds)
    HTTP_CLIENT_TIMEOUT = float(os.getenv("HTTP_CLIENT_TIMEOUT", "120"))
    HTTP_EMBEDDING_TIMEOUT = float(os.getenv("HTTP_EMBEDDING_TIMEOUT", "180"))
    
    # Retry configuration
    CRAWLER_MAX_RETRIES = int(os.getenv("CRAWLER_MAX_RETRIES", "3"))
    CRAWLER_RETRY_DELAY = float(os.getenv("CRAWLER_RETRY_DELAY", "5"))

async def with_timeout(
    coro: Awaitable[T], 
    timeout_seconds: Optional[float] = None,
    operation_name: str = "operation",
    raise_on_timeout: bool = True
) -> T:
    """
    Wrap async operations with timeout handling and logging.
    
    Args:
        coro: The coroutine to execute
        timeout_seconds: Timeout in seconds (uses default if None)
        operation_name: Name for logging purposes
        raise_on_timeout: Whether to raise TimeoutError or return None
        
    Returns:
        Result of the coroutine
        
    Raises:
        TimeoutError: If timeout occurs and raise_on_timeout is True
    """
    if timeout_seconds is None:
        timeout_seconds = TimeoutConfig.CRAWLER_PAGE_TIMEOUT
    
    start_time = time.time()
    
    try:
        logger.debug(f"Starting {operation_name} with {timeout_seconds}s timeout")
        result = await asyncio.wait_for(coro, timeout=timeout_seconds)
        elapsed = time.time() - start_time
        logger.debug(f"Completed {operation_name} in {elapsed:.2f}s")
        return result
        
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        error_msg = f"{operation_name} timed out after {elapsed:.2f}s (limit: {timeout_seconds}s)"
        logger.warning(error_msg)
        
        if raise_on_timeout:
            raise TimeoutError(error_msg)
        return None
        
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"{operation_name} failed after {elapsed:.2f}s: {str(e)}")
        raise

async def with_retries(
    coro_func: callable,
    *args,
    max_retries: int = None,
    base_delay: float = None,
    timeout_per_attempt: float = None,
    operation_name: str = "operation",
    **kwargs
) -> T:
    """
    Execute async operation with retries and exponential backoff.
    
    Args:
        coro_func: Async function to call
        *args: Arguments to pass to coro_func
        max_retries: Maximum retry attempts (uses config default if None)
        base_delay: Base delay between retries (uses config default if None)
        timeout_per_attempt: Timeout for each attempt (uses config default if None)
        operation_name: Name for logging purposes
        **kwargs: Keyword arguments to pass to coro_func
        
    Returns:
        Result of successful execution
        
    Raises:
        The last exception encountered if all retries fail
    """
    if max_retries is None:
        max_retries = TimeoutConfig.CRAWLER_MAX_RETRIES
    if base_delay is None:
        base_delay = TimeoutConfig.CRAWLER_RETRY_DELAY
    if timeout_per_attempt is None:
        timeout_per_attempt = TimeoutConfig.CRAWLER_PAGE_TIMEOUT
    
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
                logger.info(f"Retrying {operation_name} (attempt {attempt + 1}/{max_retries + 1}) after {delay}s delay")
                await asyncio.sleep(delay)
            
            coro = coro_func(*args, **kwargs)
            return await with_timeout(
                coro,
                timeout_seconds=timeout_per_attempt,
                operation_name=f"{operation_name} (attempt {attempt + 1})",
                raise_on_timeout=True
            )
            
        except (TimeoutError, asyncio.TimeoutError) as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(f"{operation_name} attempt {attempt + 1} timed out, retrying...")
            continue
            
        except Exception as e:
            last_exception = e
            # Don't retry on non-timeout errors for now
            logger.error(f"{operation_name} failed with non-timeout error: {str(e)}")
            break
    
    # All retries exhausted
    logger.error(f"{operation_name} failed after {max_retries + 1} attempts")
    raise last_exception

def timeout_decorator(
    timeout_seconds: Optional[float] = None,
    operation_name: Optional[str] = None,
    raise_on_timeout: bool = True
):
    """
    Decorator for adding timeout protection to async functions.
    
    Args:
        timeout_seconds: Timeout in seconds
        operation_name: Name for logging (uses function name if None)
        raise_on_timeout: Whether to raise on timeout
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            name = operation_name or f"{func.__module__}.{func.__name__}"
            coro = func(*args, **kwargs)
            return await with_timeout(
                coro,
                timeout_seconds=timeout_seconds,
                operation_name=name,
                raise_on_timeout=raise_on_timeout
            )
        return wrapper
    return decorator

class TimeoutContext:
    """Context manager for timeout operations with automatic cleanup."""
    
    def __init__(self, timeout_seconds: float, operation_name: str = "operation"):
        self.timeout_seconds = timeout_seconds
        self.operation_name = operation_name
        self.start_time = None
        self.task = None
    
    async def __aenter__(self):
        self.start_time = time.time()
        logger.debug(f"Starting {self.operation_name} with {self.timeout_seconds}s timeout")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        if exc_type == asyncio.TimeoutError:
            logger.warning(f"{self.operation_name} timed out after {elapsed:.2f}s")
        elif exc_type is None:
            logger.debug(f"{self.operation_name} completed in {elapsed:.2f}s")
        else:
            logger.error(f"{self.operation_name} failed after {elapsed:.2f}s: {str(exc_val)}")
    
    async def run(self, coro: Awaitable[T]) -> T:
        """Execute coroutine within this timeout context."""
        return await asyncio.wait_for(coro, timeout=self.timeout_seconds)

# Convenience functions for common timeout scenarios
async def with_crawler_timeout(coro: Awaitable[T], operation_name: str = "crawler operation") -> T:
    """Execute with crawler-specific timeout."""
    return await with_timeout(
        coro, 
        timeout_seconds=TimeoutConfig.CRAWLER_PAGE_TIMEOUT,
        operation_name=operation_name
    )

async def with_batch_timeout(coro: Awaitable[T], operation_name: str = "batch operation") -> T:
    """Execute with batch operation timeout."""
    return await with_timeout(
        coro,
        timeout_seconds=TimeoutConfig.CRAWLER_BATCH_TIMEOUT,
        operation_name=operation_name
    )

async def with_database_timeout(coro: Awaitable[T], operation_name: str = "database operation") -> T:
    """Execute with database operation timeout."""
    return await with_timeout(
        coro,
        timeout_seconds=TimeoutConfig.QDRANT_OPERATION_TIMEOUT,
        operation_name=operation_name
    )

async def with_process_timeout(coro: Awaitable[T], operation_name: str = "process operation") -> T:
    """Execute with process operation timeout."""
    return await with_timeout(
        coro,
        timeout_seconds=TimeoutConfig.PROCESS_POOL_TIMEOUT,
        operation_name=operation_name
    )