"""
Custom middleware for handling cancellation and proper cleanup in FastMCP.
"""
import asyncio
import time
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.utilities.logging import get_logger

logger = get_logger(__name__)

class CancellationHandlingMiddleware(Middleware):
    """
    Middleware to handle cancellation gracefully and prevent server crashes.
    
    This middleware:
    1. Catches CancelledError exceptions from tools
    2. Prevents double response issues
    3. Logs cancellation events properly
    4. Ensures proper cleanup on cancellation
    """
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Handle tool calls with cancellation protection."""
        start_time = time.perf_counter()
        
        try:
            logger.debug(f"Starting tool call: {getattr(context, 'method', 'unknown')}")
            result = await call_next(context)
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(f"Tool call completed in {duration_ms:.2f}ms")
            return result
            
        except asyncio.CancelledError:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(f"Tool call cancelled after {duration_ms:.2f}ms")
            
            # Return proper cancellation response instead of crashing
            return {
                "success": False,
                "error": "Operation cancelled by client",
                "elapsed_time_ms": round(duration_ms, 2)
            }
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Tool call failed after {duration_ms:.2f}ms: {e}")
            raise
    
    async def on_request(self, context: MiddlewareContext, call_next):
        """Handle all requests with cancellation protection."""
        try:
            return await call_next(context)
        except asyncio.CancelledError:
            logger.warning(f"Request cancelled: {getattr(context, 'method', 'unknown')}")
            # Let tools handle their own cancellation responses
            raise