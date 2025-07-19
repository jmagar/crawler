"""
FastMCP standardized error handling and response utilities.
"""
import json
import time
import logging
import traceback
from typing import Dict, Any, Optional, Union
from enum import Enum
from dataclasses import dataclass, asdict
from fastmcp import Context


class ErrorSeverity(Enum):
    """Error severity levels for consistent classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for better organization."""
    VALIDATION = "validation"
    NETWORK = "network"
    DATABASE = "database"
    FILESYSTEM = "filesystem"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    EXTERNAL_API = "external_api"
    INTERNAL = "internal"
    CANCELLATION = "cancellation"


@dataclass
class StandardError:
    """Standardized error structure for consistent error responses."""
    success: bool = False
    error_type: str = "UnknownError"
    error_message: str = "An unknown error occurred"
    error_code: Optional[str] = None
    error_category: str = ErrorCategory.INTERNAL.value
    severity: str = ErrorSeverity.MEDIUM.value
    tool_name: Optional[str] = None
    operation_id: Optional[str] = None
    timestamp: float = None
    context: Dict[str, Any] = None
    suggestions: list = None
    retry_possible: bool = False
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.context is None:
            self.context = {}
        if self.suggestions is None:
            self.suggestions = []
    
    def to_json(self, indent: int = 2) -> str:
        """Convert error to JSON string."""
        return json.dumps(asdict(self), indent=indent)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary."""
        return asdict(self)


class MCPErrorHandler:
    """Centralized error handler for MCP tools with FastMCP patterns."""
    
    def __init__(self, tool_name: str, operation_id: str = None):
        """
        Initialize error handler for a specific tool.
        
        Args:
            tool_name: Name of the MCP tool
            operation_id: Optional operation identifier
        """
        self.tool_name = tool_name
        self.operation_id = operation_id or f"{tool_name}_{int(time.time())}"
        self.logger = logging.getLogger(f"mcp.{tool_name}")
    
    def create_error(
        self,
        error: Union[Exception, str],
        category: ErrorCategory = ErrorCategory.INTERNAL,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        error_code: str = None,
        context: Dict[str, Any] = None,
        suggestions: list = None,
        retry_possible: bool = False
    ) -> StandardError:
        """
        Create a standardized error response.
        
        Args:
            error: Exception or error message
            category: Error category
            severity: Error severity level
            error_code: Optional error code
            context: Additional context information
            suggestions: List of suggested solutions
            retry_possible: Whether the operation can be retried
            
        Returns:
            StandardError object
        """
        if isinstance(error, Exception):
            error_message = str(error)
            error_type = type(error).__name__
        else:
            error_message = str(error)
            error_type = "GeneralError"
        
        # Enhanced context with tool information
        enhanced_context = {
            "tool_name": self.tool_name,
            "operation_id": self.operation_id,
            **(context or {})
        }
        
        return StandardError(
            error_type=error_type,
            error_message=error_message,
            error_code=error_code,
            error_category=category.value,
            severity=severity.value,
            tool_name=self.tool_name,
            operation_id=self.operation_id,
            context=enhanced_context,
            suggestions=suggestions or [],
            retry_possible=retry_possible
        )
    
    def handle_validation_error(
        self,
        error: Union[Exception, str],
        field_name: str = None,
        provided_value: Any = None
    ) -> StandardError:
        """Handle validation errors with specific context."""
        context = {}
        if field_name:
            context["field_name"] = field_name
        if provided_value is not None:
            context["provided_value"] = str(provided_value)
        
        suggestions = [
            "Check the parameter values and types",
            "Refer to the tool documentation for valid parameters"
        ]
        
        return self.create_error(
            error=error,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            error_code="VALIDATION_FAILED",
            context=context,
            suggestions=suggestions,
            retry_possible=True
        )
    
    def handle_network_error(
        self,
        error: Union[Exception, str],
        url: str = None,
        timeout_seconds: float = None
    ) -> StandardError:
        """Handle network-related errors."""
        context = {}
        if url:
            context["url"] = url
        if timeout_seconds:
            context["timeout_seconds"] = timeout_seconds
        
        suggestions = [
            "Check your internet connection",
            "Verify the URL is accessible",
            "Try increasing the timeout value"
        ]
        
        return self.create_error(
            error=error,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.HIGH,
            error_code="NETWORK_ERROR",
            context=context,
            suggestions=suggestions,
            retry_possible=True
        )
    
    def handle_database_error(
        self,
        error: Union[Exception, str],
        collection_name: str = None,
        operation_type: str = None
    ) -> StandardError:
        """Handle database-related errors."""
        context = {}
        if collection_name:
            context["collection_name"] = collection_name
        if operation_type:
            context["operation_type"] = operation_type
        
        suggestions = [
            "Check database connection",
            "Verify collection exists and is accessible",
            "Check database service status"
        ]
        
        return self.create_error(
            error=error,
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.HIGH,
            error_code="DATABASE_ERROR",
            context=context,
            suggestions=suggestions,
            retry_possible=True
        )
    
    def handle_timeout_error(
        self,
        error: Union[Exception, str],
        timeout_seconds: float = None,
        operation_name: str = None
    ) -> StandardError:
        """Handle timeout errors."""
        context = {}
        if timeout_seconds:
            context["timeout_seconds"] = timeout_seconds
        if operation_name:
            context["operation_name"] = operation_name
        
        suggestions = [
            "Try increasing the timeout value",
            "Break down large operations into smaller chunks",
            "Check system resources and performance"
        ]
        
        return self.create_error(
            error=error,
            category=ErrorCategory.TIMEOUT,
            severity=ErrorSeverity.HIGH,
            error_code="OPERATION_TIMEOUT",
            context=context,
            suggestions=suggestions,
            retry_possible=True
        )
    
    def handle_cancellation_error(
        self,
        operation_name: str = None
    ) -> StandardError:
        """Handle operation cancellation."""
        context = {}
        if operation_name:
            context["operation_name"] = operation_name
        
        suggestions = [
            "Operation was cancelled by user or system",
            "You can retry the operation if needed"
        ]
        
        return self.create_error(
            error="Operation was cancelled",
            category=ErrorCategory.CANCELLATION,
            severity=ErrorSeverity.LOW,
            error_code="OPERATION_CANCELLED",
            context=context,
            suggestions=suggestions,
            retry_possible=True
        )
    
    def handle_resource_error(
        self,
        error: Union[Exception, str],
        resource_type: str = None,
        resource_limit: Any = None
    ) -> StandardError:
        """Handle resource-related errors."""
        context = {}
        if resource_type:
            context["resource_type"] = resource_type
        if resource_limit:
            context["resource_limit"] = str(resource_limit)
        
        suggestions = [
            "Check system resources (memory, disk space, etc.)",
            "Reduce the operation scope or batch size",
            "Wait for system resources to become available"
        ]
        
        return self.create_error(
            error=error,
            category=ErrorCategory.RESOURCE,
            severity=ErrorSeverity.HIGH,
            error_code="RESOURCE_ERROR",
            context=context,
            suggestions=suggestions,
            retry_possible=True
        )
    
    async def log_and_report_error(
        self,
        ctx: Context,
        error: StandardError,
        include_traceback: bool = False
    ) -> str:
        """
        Log error and report to FastMCP context.
        
        Args:
            ctx: FastMCP context
            error: Standardized error object
            include_traceback: Whether to include full traceback
            
        Returns:
            JSON error response string
        """
        # Log the error with appropriate level
        if error.severity == ErrorSeverity.CRITICAL.value:
            self.logger.critical(f"[{error.error_code}] {error.error_message}")
        elif error.severity == ErrorSeverity.HIGH.value:
            self.logger.error(f"[{error.error_code}] {error.error_message}")
        elif error.severity == ErrorSeverity.MEDIUM.value:
            self.logger.warning(f"[{error.error_code}] {error.error_message}")
        else:
            self.logger.info(f"[{error.error_code}] {error.error_message}")
        
        # Log context information
        if error.context:
            self.logger.debug(f"Error context: {error.context}")
        
        # Include traceback if requested and available
        if include_traceback:
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
        
        # Report to FastMCP context
        try:
            await ctx.error(f"{error.error_message} (Code: {error.error_code})")
        except Exception as report_error:
            self.logger.warning(f"Failed to report error to MCP context: {report_error}")
        
        return error.to_json()


def create_success_response(
    tool_name: str,
    data: Dict[str, Any] = None,
    message: str = None,
    operation_id: str = None,
    elapsed_time: float = None
) -> str:
    """
    Create a standardized success response.
    
    Args:
        tool_name: Name of the MCP tool
        data: Response data
        message: Success message
        operation_id: Operation identifier
        elapsed_time: Operation duration in seconds
        
    Returns:
        JSON success response string
    """
    response = {
        "success": True,
        "tool_name": tool_name,
        "timestamp": time.time(),
        **(data or {})
    }
    
    if message:
        response["message"] = message
    if operation_id:
        response["operation_id"] = operation_id
    if elapsed_time is not None:
        response["elapsed_time_seconds"] = round(elapsed_time, 3)
    
    return json.dumps(response, indent=2)


def get_error_suggestions_by_category(category: ErrorCategory) -> list:
    """Get general suggestions based on error category."""
    suggestions_map = {
        ErrorCategory.VALIDATION: [
            "Check parameter types and values",
            "Refer to tool documentation",
            "Validate input format"
        ],
        ErrorCategory.NETWORK: [
            "Check internet connection",
            "Verify URL accessibility",
            "Try again later"
        ],
        ErrorCategory.DATABASE: [
            "Check database connection",
            "Verify service status",
            "Check permissions"
        ],
        ErrorCategory.FILESYSTEM: [
            "Check file permissions",
            "Verify path exists",
            "Check disk space"
        ],
        ErrorCategory.TIMEOUT: [
            "Increase timeout value",
            "Reduce operation scope",
            "Check system performance"
        ],
        ErrorCategory.RESOURCE: [
            "Free up system resources",
            "Reduce batch size",
            "Wait and retry"
        ]
    }
    
    return suggestions_map.get(category, ["Contact support if the problem persists"])