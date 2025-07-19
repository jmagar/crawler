"""
FastMCP enhanced logging and monitoring utilities.
"""
import json
import time
import logging
import asyncio
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from fastmcp import Context


@dataclass
class OperationMetrics:
    """Metrics for MCP operations."""
    operation_id: str
    tool_name: str
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    success: bool = False
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    input_size: Optional[int] = None
    output_size: Optional[int] = None
    memory_usage: Optional[int] = None
    context_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.context_data is None:
            self.context_data = {}
    
    def complete(self, success: bool = True, error: Exception = None):
        """Mark operation as completed."""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        
        if error:
            self.error_type = type(error).__name__
            self.error_message = str(error)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class MCPLogger:
    """Enhanced logger for MCP operations with FastMCP patterns."""
    
    def __init__(self, tool_name: str, enable_metrics: bool = True):
        """
        Initialize MCP logger.
        
        Args:
            tool_name: Name of the MCP tool
            enable_metrics: Whether to collect operation metrics
        """
        self.tool_name = tool_name
        self.enable_metrics = enable_metrics
        self.logger = logging.getLogger(f"mcp.{tool_name}")
        
        # Configure structured logging
        self._setup_structured_logging()
        
        # Metrics collection
        self.metrics: Dict[str, OperationMetrics] = {}
        self.operation_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.performance_history = deque(maxlen=1000)  # Keep last 1000 operations
        
        # Thread safety
        self._metrics_lock = threading.Lock()
    
    def _setup_structured_logging(self):
        """Setup structured logging format."""
        # Create custom formatter for structured logs
        class StructuredFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                    "level": record.levelname,
                    "tool": getattr(record, 'tool_name', 'unknown'),
                    "operation_id": getattr(record, 'operation_id', None),
                    "message": record.getMessage(),
                }
                
                # Add extra fields if present
                if hasattr(record, 'extra_data'):
                    log_entry.update(record.extra_data)
                
                return json.dumps(log_entry)
        
        # Only add handler if not already present
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            handler = logging.StreamHandler()
            handler.setFormatter(StructuredFormatter())
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def start_operation(self, operation_id: str, context_data: Dict[str, Any] = None) -> OperationMetrics:
        """
        Start tracking an operation.
        
        Args:
            operation_id: Unique operation identifier
            context_data: Additional context information
            
        Returns:
            OperationMetrics object
        """
        metrics = OperationMetrics(
            operation_id=operation_id,
            tool_name=self.tool_name,
            start_time=time.time(),
            context_data=context_data or {}
        )
        
        if self.enable_metrics:
            with self._metrics_lock:
                self.metrics[operation_id] = metrics
                self.operation_counts[self.tool_name] += 1
        
        self.info(
            f"Operation started: {operation_id}",
            operation_id=operation_id,
            extra_data={"event": "operation_start", "context": context_data}
        )
        
        return metrics
    
    def complete_operation(
        self,
        operation_id: str,
        success: bool = True,
        error: Exception = None,
        output_data: Any = None
    ):
        """
        Complete an operation and record metrics.
        
        Args:
            operation_id: Operation identifier
            success: Whether operation was successful
            error: Exception if operation failed
            output_data: Operation output for size calculation
        """
        if self.enable_metrics and operation_id in self.metrics:
            with self._metrics_lock:
                metrics = self.metrics[operation_id]
                metrics.complete(success=success, error=error)
                
                # Calculate output size if possible
                if output_data is not None:
                    try:
                        if isinstance(output_data, str):
                            metrics.output_size = len(output_data.encode('utf-8'))
                        elif isinstance(output_data, (dict, list)):
                            metrics.output_size = len(json.dumps(output_data).encode('utf-8'))
                    except Exception:
                        pass  # Ignore size calculation errors
                
                # Add to performance history
                self.performance_history.append(metrics.to_dict())
                
                # Track error counts
                if not success and error:
                    self.error_counts[type(error).__name__] += 1
        
        # Log completion
        level = "info" if success else "error"
        message = f"Operation completed: {operation_id}"
        extra_data = {
            "event": "operation_complete",
            "success": success,
            "duration": getattr(self.metrics.get(operation_id), 'duration', None)
        }
        
        if error:
            extra_data["error_type"] = type(error).__name__
            extra_data["error_message"] = str(error)
        
        getattr(self, level)(message, operation_id=operation_id, extra_data=extra_data)
    
    def log_progress(self, operation_id: str, progress: int, total: int, message: str = None):
        """
        Log operation progress.
        
        Args:
            operation_id: Operation identifier
            progress: Current progress value
            total: Total progress value
            message: Progress message
        """
        percentage = (progress / total) * 100 if total > 0 else 0
        
        self.info(
            f"Progress update: {message or 'In progress'}",
            operation_id=operation_id,
            extra_data={
                "event": "progress_update",
                "progress": progress,
                "total": total,
                "percentage": round(percentage, 1),
                "message": message
            }
        )
    
    def log_resource_usage(self, operation_id: str, resource_type: str, usage_data: Dict[str, Any]):
        """
        Log resource usage information.
        
        Args:
            operation_id: Operation identifier
            resource_type: Type of resource (memory, cpu, disk, etc.)
            usage_data: Resource usage data
        """
        self.debug(
            f"Resource usage - {resource_type}",
            operation_id=operation_id,
            extra_data={
                "event": "resource_usage",
                "resource_type": resource_type,
                **usage_data
            }
        )
    
    def log_external_call(
        self,
        operation_id: str,
        service_name: str,
        endpoint: str,
        duration: float,
        success: bool,
        response_size: int = None
    ):
        """
        Log external service calls.
        
        Args:
            operation_id: Operation identifier
            service_name: Name of external service
            endpoint: Service endpoint
            duration: Call duration in seconds
            success: Whether call was successful
            response_size: Size of response in bytes
        """
        self.info(
            f"External call to {service_name}: {endpoint}",
            operation_id=operation_id,
            extra_data={
                "event": "external_call",
                "service_name": service_name,
                "endpoint": endpoint,
                "duration": round(duration, 3),
                "success": success,
                "response_size": response_size
            }
        )
    
    def info(self, message: str, operation_id: str = None, extra_data: Dict[str, Any] = None):
        """Log info message with structured data."""
        self._log(logging.INFO, message, operation_id, extra_data)
    
    def warning(self, message: str, operation_id: str = None, extra_data: Dict[str, Any] = None):
        """Log warning message with structured data."""
        self._log(logging.WARNING, message, operation_id, extra_data)
    
    def error(self, message: str, operation_id: str = None, extra_data: Dict[str, Any] = None):
        """Log error message with structured data."""
        self._log(logging.ERROR, message, operation_id, extra_data)
    
    def debug(self, message: str, operation_id: str = None, extra_data: Dict[str, Any] = None):
        """Log debug message with structured data."""
        self._log(logging.DEBUG, message, operation_id, extra_data)
    
    def _log(self, level: int, message: str, operation_id: str = None, extra_data: Dict[str, Any] = None):
        """Internal logging method."""
        extra = {
            "tool_name": self.tool_name,
            "operation_id": operation_id,
            "extra_data": extra_data or {}
        }
        self.logger.log(level, message, extra=extra)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of collected metrics."""
        with self._metrics_lock:
            total_operations = sum(self.operation_counts.values())
            total_errors = sum(self.error_counts.values())
            
            # Calculate average duration from completed operations
            completed_operations = [m for m in self.metrics.values() if m.duration is not None]
            avg_duration = (
                sum(m.duration for m in completed_operations) / len(completed_operations)
                if completed_operations else 0
            )
            
            return {
                "tool_name": self.tool_name,
                "total_operations": total_operations,
                "total_errors": total_errors,
                "success_rate": (total_operations - total_errors) / total_operations if total_operations > 0 else 0,
                "average_duration_seconds": round(avg_duration, 3),
                "operation_counts": dict(self.operation_counts),
                "error_counts": dict(self.error_counts),
                "active_operations": len([m for m in self.metrics.values() if m.end_time is None])
            }


class OperationMonitor:
    """Monitor and track MCP operations across the entire server."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.loggers: Dict[str, MCPLogger] = {}
            self.global_metrics = {
                "server_start_time": time.time(),
                "total_operations": 0,
                "total_errors": 0,
                "operations_by_tool": defaultdict(int),
                "errors_by_tool": defaultdict(int)
            }
            self.initialized = True
    
    def get_logger(self, tool_name: str) -> MCPLogger:
        """Get or create logger for a tool."""
        if tool_name not in self.loggers:
            self.loggers[tool_name] = MCPLogger(tool_name)
        return self.loggers[tool_name]
    
    def get_server_metrics(self) -> Dict[str, Any]:
        """Get comprehensive server metrics."""
        uptime = time.time() - self.global_metrics["server_start_time"]
        
        # Aggregate metrics from all loggers
        tool_summaries = {}
        for tool_name, logger in self.loggers.items():
            tool_summaries[tool_name] = logger.get_metrics_summary()
        
        return {
            "server_uptime_seconds": round(uptime, 1),
            "server_uptime_human": self._format_duration(uptime),
            "global_metrics": dict(self.global_metrics),
            "tool_metrics": tool_summaries,
            "active_tools": list(self.loggers.keys()),
            "timestamp": time.time()
        }
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        else:
            return f"{seconds/3600:.1f}h"


@asynccontextmanager
async def log_operation(
    ctx: Context,
    tool_name: str,
    operation_name: str = None,
    context_data: Dict[str, Any] = None
):
    """
    Async context manager for automatic operation logging.
    
    Usage:
        async with log_operation(ctx, "my_tool", "my_operation") as logger:
            # Your operation code here
            logger.info("Step completed")
    """
    logger = OperationMonitor().get_logger(tool_name)
    operation_id = operation_name or f"{tool_name}_{int(time.time())}"
    
    metrics = logger.start_operation(operation_id, context_data)
    
    try:
        yield logger
        logger.complete_operation(operation_id, success=True)
    except Exception as e:
        logger.complete_operation(operation_id, success=False, error=e)
        raise


def log_tool_performance(func):
    """
    Decorator for automatic tool performance logging.
    
    Usage:
        @log_tool_performance
        async def my_tool(ctx: Context, ...):
            # Tool implementation
    """
    async def wrapper(*args, **kwargs):
        # Extract context and tool name
        ctx = args[0] if args and isinstance(args[0], Context) else None
        tool_name = func.__name__
        
        if ctx:
            async with log_operation(ctx, tool_name, func.__name__) as logger:
                return await func(*args, **kwargs)
        else:
            return await func(*args, **kwargs)
    
    return wrapper


def setup_mcp_logging(log_level: str = "INFO", enable_structured: bool = True):
    """
    Setup MCP server logging configuration.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        enable_structured: Whether to use structured JSON logging
    """
    root_logger = logging.getLogger("mcp")
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    if enable_structured:
        # JSON formatter for structured logging
        class JSONFormatter(logging.Formatter):
            def format(self, record):
                log_entry = {
                    "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                }
                
                # Add exception info if present
                if record.exc_info:
                    log_entry["exception"] = self.formatException(record.exc_info)
                
                return json.dumps(log_entry)
        
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        root_logger.addHandler(handler)
    
    # Configure specific loggers
    logging.getLogger("mcp.server").info("MCP logging configured")
    logging.getLogger("mcp.metrics").info("MCP metrics collection enabled")