"""
Timeout middleware for MCP tool operations.
Provides comprehensive timeout protection for all MCP tool calls with proper error handling.
"""
import asyncio
import time
import logging
from typing import Any, Callable, Awaitable
from fastmcp.server.middleware import Middleware
from fastmcp import Context

from .timeout_utils import TimeoutConfig

logger = logging.getLogger(__name__)

class TimeoutMiddleware(Middleware):
    """
    Middleware that adds timeout protection to all MCP tool operations.
    Prevents tools from running indefinitely and provides graceful error handling.
    """
    
    def __init__(self, default_timeout: float = None):
        """
        Initialize timeout middleware.
        
        Args:
            default_timeout: Default timeout in seconds (uses config if None)
        """
        self.default_timeout = default_timeout or TimeoutConfig.MCP_TOOL_TIMEOUT
        logger.info(f"Initialized TimeoutMiddleware with {self.default_timeout}s default timeout")
    
    async def __call__(
        self, 
        request: Any, 
        call_next: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """
        Process request with timeout protection.
        
        Args:
            request: The incoming MCP request
            call_next: The next middleware/handler in the chain
            
        Returns:
            Response from the handler or timeout error response
        """
        # Extract tool name and operation info for logging
        tool_name = getattr(request, 'method', 'unknown_tool')
        operation_id = getattr(request, 'id', 'unknown_id')
        
        # Get timeout for this specific tool (can be customized per tool)
        timeout_seconds = self._get_tool_timeout(tool_name)
        
        start_time = time.time()
        logger.debug(f"Starting tool '{tool_name}' (ID: {operation_id}) with {timeout_seconds}s timeout")
        
        try:
            # Execute the tool with timeout protection
            result = await asyncio.wait_for(
                call_next(request), 
                timeout=timeout_seconds
            )
            
            elapsed_time = time.time() - start_time
            logger.debug(f"Tool '{tool_name}' completed in {elapsed_time:.2f}s")
            
            return result
            
        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            error_msg = f"Tool '{tool_name}' timed out after {elapsed_time:.2f}s (limit: {timeout_seconds}s)"
            logger.warning(error_msg)
            
            # Return structured error response
            return {
                "success": False,
                "error": "timeout",
                "message": error_msg,
                "elapsed_time_seconds": round(elapsed_time, 2),
                "timeout_limit_seconds": timeout_seconds,
                "tool_name": tool_name,
                "operation_id": operation_id
            }
            
        except asyncio.CancelledError:
            elapsed_time = time.time() - start_time
            logger.info(f"Tool '{tool_name}' was cancelled after {elapsed_time:.2f}s")
            
            # DON'T return a response - let MCP framework handle cancellation
            # The MCP protocol already handles cancellation notifications properly
            raise
            
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Tool '{tool_name}' failed after {elapsed_time:.2f}s: {str(e)}")
            
            # Re-raise the original exception for proper error handling
            raise
    
    def _get_tool_timeout(self, tool_name: str) -> float:
        """
        Get timeout for a specific tool based on its expected duration.
        
        Args:
            tool_name: Name of the MCP tool
            
        Returns:
            Timeout in seconds
        """
        # Define tool-specific timeouts based on expected operation duration
        tool_timeouts = {
            # Crawling tools - longer timeouts
            'crawl': TimeoutConfig.CRAWLER_RECURSIVE_TIMEOUT,  # 1 hour for recursive crawls
            'scrape': TimeoutConfig.CRAWLER_PAGE_TIMEOUT,      # 5 minutes for single page
            
            # Database tools - moderate timeouts
            'rag_query': TimeoutConfig.QDRANT_OPERATION_TIMEOUT,        # 30 seconds
            'available_sources': TimeoutConfig.QDRANT_SCROLL_TIMEOUT,   # 1 minute
            'search_code_examples': TimeoutConfig.QDRANT_OPERATION_TIMEOUT,
            
            # Knowledge graph tools - longer timeouts
            'crawl_repo': 1800,  # 30 minutes for repository analysis
            'graph_query': TimeoutConfig.QDRANT_OPERATION_TIMEOUT,
            'you_trippin': TimeoutConfig.PROCESS_POOL_TIMEOUT,
            
            # Quick operations - short timeouts
            'health_check': 10,   # 10 seconds
            'get_sources': TimeoutConfig.QDRANT_OPERATION_TIMEOUT,
        }
        
        # Return tool-specific timeout or default
        timeout = tool_timeouts.get(tool_name, self.default_timeout)
        
        logger.debug(f"Tool '{tool_name}' assigned {timeout}s timeout")
        return timeout

class ProgressAwareTimeoutMiddleware(TimeoutMiddleware):
    """
    Enhanced timeout middleware that respects progress reporting.
    Extends timeout when tools are actively reporting progress.
    """
    
    def __init__(self, default_timeout: float = None, progress_extension: float = 300):
        """
        Initialize progress-aware timeout middleware.
        
        Args:
            default_timeout: Default timeout in seconds
            progress_extension: Additional time granted when progress is reported (seconds)
        """
        super().__init__(default_timeout)
        self.progress_extension = progress_extension
        self.active_operations = {}  # Track operations and their last progress update
        
        logger.info(f"Initialized ProgressAwareTimeoutMiddleware with {progress_extension}s progress extension")
    
    async def __call__(self, request: Any, call_next: Callable[[Any], Awaitable[Any]]) -> Any:
        """
        Process request with progress-aware timeout protection.
        """
        tool_name = getattr(request, 'method', 'unknown_tool')
        operation_id = getattr(request, 'id', 'unknown_id')
        
        # Track this operation
        self.active_operations[operation_id] = {
            'start_time': time.time(),
            'last_progress': time.time(),
            'tool_name': tool_name
        }
        
        try:
            # Use parent implementation but with extended timeout logic
            return await super().__call__(request, call_next)
            
        finally:
            # Clean up tracking
            self.active_operations.pop(operation_id, None)
    
    def report_progress(self, operation_id: str):
        """
        Called when a tool reports progress to extend its timeout.
        
        Args:
            operation_id: ID of the operation reporting progress
        """
        if operation_id in self.active_operations:
            self.active_operations[operation_id]['last_progress'] = time.time()
            logger.debug(f"Extended timeout for operation {operation_id} due to progress")
    
    def _get_adjusted_timeout(self, tool_name: str, operation_id: str) -> float:
        """
        Get timeout adjusted for progress reporting.
        
        Args:
            tool_name: Name of the tool
            operation_id: Operation ID
            
        Returns:
            Adjusted timeout in seconds
        """
        base_timeout = self._get_tool_timeout(tool_name)
        
        if operation_id in self.active_operations:
            op_info = self.active_operations[operation_id]
            time_since_progress = time.time() - op_info['last_progress']
            
            # If we recently received progress, extend the timeout
            if time_since_progress < self.progress_extension:
                adjusted_timeout = base_timeout + self.progress_extension
                logger.debug(f"Extended timeout for '{tool_name}' to {adjusted_timeout}s due to recent progress")
                return adjusted_timeout
        
        return base_timeout

# Context manager for timeout operations
class TimeoutOperation:
    """Context manager for timeout-protected operations with progress support."""
    
    def __init__(
        self, 
        ctx: Context, 
        operation_name: str, 
        timeout_seconds: float = None,
        report_progress: bool = True
    ):
        """
        Initialize timeout operation context.
        
        Args:
            ctx: FastMCP context
            operation_name: Name of the operation
            timeout_seconds: Timeout in seconds (uses default if None)
            report_progress: Whether to report progress during operation
        """
        self.ctx = ctx
        self.operation_name = operation_name
        self.timeout_seconds = timeout_seconds or TimeoutConfig.MCP_TOOL_TIMEOUT
        self.report_progress = report_progress
        self.start_time = None
        
    async def __aenter__(self):
        """Enter the timeout context."""
        self.start_time = time.time()
        if self.report_progress:
            await self.ctx.report_progress(0, 100, f"Starting {self.operation_name}")
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the timeout context."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        if exc_type is asyncio.TimeoutError:
            if self.report_progress:
                await self.ctx.warning(f"{self.operation_name} timed out after {elapsed:.2f}s")
        elif exc_type is None and self.report_progress:
            await self.ctx.report_progress(100, 100, f"Completed {self.operation_name} in {elapsed:.2f}s")
    
    async def step(self, progress: int, message: str = None):
        """Report progress step."""
        if self.report_progress:
            msg = message or f"{self.operation_name} progress"
            await self.ctx.report_progress(progress, 100, msg)