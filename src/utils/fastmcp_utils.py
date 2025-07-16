"""
FastMCP utility functions for enhanced functionality.
"""
from typing import Dict, Any, Optional
from urllib.parse import parse_qs, urlparse


def get_query_parameters() -> Dict[str, Any]:
    """
    Extract query parameters from the current HTTP request.
    
    Since FastMCP doesn't natively support query parameters in resource URIs,
    this function attempts to extract them from the HTTP request context.
    
    Returns:
        Dict containing query parameters with automatic type conversion:
        - Numeric strings are converted to integers
        - "true"/"false" strings are converted to booleans
        - Single-item lists are flattened to single values
        
    Examples:
        ?limit=50&source_filter=github.com&active=true
        Returns: {"limit": 50, "source_filter": "github.com", "active": True}
    """
    try:
        from fastmcp.server.dependencies import get_http_request
        request = get_http_request()
        
        if request and hasattr(request, 'url'):
            parsed_url = urlparse(str(request.url))
            query_params = parse_qs(parsed_url.query)
            
            # Process and convert parameters
            result = {}
            for key, value_list in query_params.items():
                if len(value_list) == 1:
                    value = value_list[0]
                    # Try to convert to appropriate type
                    result[key] = _convert_query_value(value)
                else:
                    # Multiple values - keep as list with conversion
                    result[key] = [_convert_query_value(v) for v in value_list]
            
            return result
            
    except Exception:
        # If we can't get the request context, return empty dict
        pass
    
    return {}


def _convert_query_value(value: str) -> Any:
    """
    Convert a query parameter value to appropriate Python type.
    
    Args:
        value: String value from query parameter
        
    Returns:
        Converted value (int, bool, or original string)
    """
    # Try integer conversion
    if value.isdigit():
        return int(value)
    
    # Try boolean conversion
    if value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    
    # Return as string
    return value


def get_pagination_params(query_params: Dict[str, Any], 
                         default_limit: int = 100,
                         max_limit: int = 1000) -> Dict[str, int]:
    """
    Extract and validate pagination parameters from query parameters.
    
    Args:
        query_params: Query parameters dictionary
        default_limit: Default limit if not specified
        max_limit: Maximum allowed limit
        
    Returns:
        Dict with 'limit' and 'offset' keys
    """
    limit = min(query_params.get("limit", default_limit), max_limit)
    offset = max(query_params.get("offset", 0), 0)
    
    return {"limit": limit, "offset": offset}