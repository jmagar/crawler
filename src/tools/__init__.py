"""
Tools module for the Crawl4AI MCP server.

This module ensures that all tools are properly imported and registered
when the tools package is imported.
"""

# Import all tools to ensure they get registered with the MCP server
from . import crawling_tools
from . import kg_tools

__all__ = ["crawling_tools", "kg_tools"]