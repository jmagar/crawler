# FastMCP Transport Migration: SSE → Streamable HTTP

## Overview
Migrated Crawl4AI MCP Server from deprecated SSE (Server-Sent Events) transport to modern Streamable HTTP transport, following FastMCP best practices.

## Changes Made

### 1. Configuration Updates
- **`.env`**: Changed `TRANSPORT=sse` → `TRANSPORT=http`
- **Added**: `MCP_PATH=/mcp/` configuration option
- **Updated**: Default transport in `src/crawl4ai_mcp.py` to `http`

### 2. Server Startup
- **Enhanced CLI**: Added `--transport` and `--path` arguments
- **Dynamic Transport**: Server now respects environment/CLI transport configuration
- **Flexible Endpoint**: Configurable MCP path (default: `/mcp/`)

### 3. Documentation Updates
- **README.md**: Updated client integration examples
- **Client Examples**: Changed from `/sse` to `/mcp/` endpoints
- **Test Commands**: Updated curl examples to use new endpoints
- **Added**: Legacy SSE support documentation for backwards compatibility

### 4. Development Environment
- **dev.sh**: Updated basic .env template to use HTTP transport
- **Default URL**: Development server now runs on `http://localhost:8051/mcp/`

## Client Migration

### Before (SSE - Deprecated)
```bash
claude mcp add --transport sse crawl4ai-rag http://localhost:8051/sse
```

### After (Streamable HTTP - Recommended)
```bash
claude mcp add --transport http crawl4ai-rag http://localhost:8051/mcp/
```

### Configuration Files
```json
{
  "mcpServers": {
    "crawl4ai-rag": {
      "transport": "http",
      "url": "http://localhost:8051/mcp/"
    }
  }
}
```

## Benefits of Streamable HTTP

1. **Modern Standard**: Recommended by FastMCP documentation
2. **Better Performance**: More efficient than SSE for MCP communication
3. **Web-Native**: Better integration with web-based deployments
4. **Future-Proof**: Actively maintained and developed
5. **Debugging**: Easier to debug with standard HTTP tools

## API Endpoint Changes

| Component | Old SSE Endpoint | New HTTP Endpoint |
|-----------|------------------|-------------------|
| Tools | `POST /tools/{tool_name}` | `POST /mcp/tools/{tool_name}` |
| Resources | `GET /resources/{uri}` | `GET /mcp/resources/{uri}` |
| Health Check | `GET /health` | `GET /health` (unchanged) |

## Testing the Migration

### Health Check
```bash
curl http://localhost:8051/health
```

### Tool Test
```bash
curl -X POST http://localhost:8051/mcp/tools/crawl_single_page \
  -H "Content-Type: application/json" \
  -d '{"url": "https://docs.python.org/3/tutorial/"}'
```

### RAG Query Test
```bash
curl -X POST http://localhost:8051/mcp/tools/perform_rag_query \
  -H "Content-Type: application/json" \
  -d '{"query": "python functions", "match_count": 5}'
```

## Backwards Compatibility

The server still supports SSE transport if needed:
```bash
# Force SSE transport
TRANSPORT=sse uv run src/crawl4ai_mcp.py

# Or via CLI
uv run src/crawl4ai_mcp.py --transport sse
```

## Next Steps

1. **Update Clients**: Migrate any existing MCP clients to use HTTP transport
2. **Monitor Performance**: Compare HTTP vs SSE performance in your environment
3. **Remove SSE**: Consider removing SSE support in future versions once migration is complete

## References

- [FastMCP Documentation](https://gofastmcp.com)
- [FastMCP Transport Guide](https://gofastmcp.com/deployment/running-server)
- [Streamable HTTP Transport](https://gofastmcp.com/transports/http)