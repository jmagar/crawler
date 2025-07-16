# FastMCP Query Parameters Support

This document explains how to access query parameters in FastMCP resources, since the framework doesn't natively support them.

## Overview

FastMCP resources support:
- ✅ **Path parameters**: `sources://{path}` → `path` becomes a function parameter
- ✅ **Function parameters with defaults**: Optional parameters with default values
- ✅ **Wildcard parameters**: `{path*}` for multi-segment paths
- ❌ **Query parameters**: `?limit=50&source_filter=github.com` (not natively supported)

## Solution

We've implemented a custom solution using the `get_http_request()` function from `fastmcp.server.dependencies` to access query parameters manually.

### Implementation

1. **Utility Function**: `/src/utils/fastmcp_utils.py`
   - `get_query_parameters()`: Extracts and converts query parameters
   - `get_pagination_params()`: Helper for pagination parameters
   - `get_request_info()`: General request information

2. **Usage in Resources**: 
   ```python
   from src.utils.fastmcp_utils import get_query_parameters
   
   @mcp.resource("sources://{path}")
   async def sources_resource(path: str, context: Context) -> str:
       query_params = get_query_parameters()
       
       limit = query_params.get("limit", 100)
       source_filter = query_params.get("source_filter")
       
       # Use the parameters...
   ```

## Supported Query Parameters

### Sources Resources

#### `/sources://overview`
- `limit`: Number of sources to return (default: from config)

#### `/sources://urls`
- `limit`: Number of URLs to return (default: 100)
- `source_filter`: Filter by source domain (e.g., "github.com")
- `offset`: Pagination offset (default: 0)

#### `/sources://stats`
- `source_filter`: Filter statistics by source domain

## Examples

### Basic Usage
```bash
# Get first 50 sources
curl "http://localhost:8051/sources://overview?limit=50"

# Get URLs from GitHub only
curl "http://localhost:8051/sources://urls?source_filter=github.com&limit=20"

# Get statistics for a specific source
curl "http://localhost:8051/sources://stats?source_filter=docs.python.org"
```

### Advanced Usage with Pagination
```bash
# Get page 2 of URLs (20 per page)
curl "http://localhost:8051/sources://urls?limit=20&offset=20"

# Combine filters and pagination
curl "http://localhost:8051/sources://urls?source_filter=github.com&limit=10&offset=30"
```

## Type Conversion

The `get_query_parameters()` function automatically converts common parameter types:

- **Numeric parameters**: `limit`, `offset`, `page`, `size`, `count`, `max_results`
- **Boolean parameters**: `include_archived`, `has_code`, `recursive`, `enabled`
- **String parameters**: All others remain as strings

## Error Handling

The implementation includes robust error handling:
- Returns empty dict if no HTTP request context is available
- Logs debug messages for troubleshooting
- Gracefully handles type conversion errors
- Provides sensible defaults for all parameters

## Limitations

1. **Transport Dependency**: Only works with HTTP/SSE transport, not STDIO
2. **No OpenAPI Integration**: Query parameters won't appear in generated OpenAPI schemas
3. **Manual Documentation**: Parameter documentation must be maintained manually

## Alternative Approaches

### Option 1: Path-based Parameters (Recommended for simple cases)
```python
@mcp.resource("sources://{path}/{limit}")
async def sources_with_limit(path: str, limit: int = 100, context: Context) -> str:
    # limit is now a path parameter
```

### Option 2: Resource Templates with Multiple Routes
```python
@mcp.resource("sources://{path}/filtered/{filter}")
@mcp.resource("sources://{path}")
async def sources_resource(path: str, filter: str = None, context: Context) -> str:
    # Different routes for different parameter combinations
```

### Option 3: Single Parameter JSON String
```python
@mcp.resource("sources://{path}/{params}")
async def sources_resource(path: str, params: str = "{}", context: Context) -> str:
    import json
    query_params = json.loads(params)
    # Use query_params dict
```

## Best Practices

1. **Always Provide Defaults**: Every query parameter should have a sensible default
2. **Validate Parameters**: Check parameter types and ranges
3. **Document Parameters**: Include parameter documentation in docstrings
4. **Use Helper Functions**: Leverage `get_pagination_params()` for common patterns
5. **Log Debug Information**: Log parameter values for troubleshooting

## Future Considerations

This solution may need updates if:
- FastMCP adds native query parameter support
- Transport layer changes affect request access
- New parameter types need special handling

For the most up-to-date information, check the FastMCP documentation and this implementation.