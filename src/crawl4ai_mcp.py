"""
Main entry point for the Crawl4AI RAG MCP Server.

This file initializes the server, loads the configuration, and registers all the tools
from their respective modules.
"""
import os
import sys
import asyncio
import argparse
from dotenv import load_dotenv

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path, override=True)

# Import the server instance and the tools
from src.core.server import mcp
from src.tools import crawling_tools, kg_tools

def main():
    """Run the MCP server based on the configured transport."""
    parser = argparse.ArgumentParser(description="Crawl4AI MCP Server")
    parser.add_argument('--host', default=os.getenv("HOST", "0.0.0.0"), help='Host to bind to')
    parser.add_argument('--port', type=int, default=int(os.getenv("PORT", 8051)), help='Port to bind to')
    
    args = parser.parse_args()
    
    # Ensure tools are imported and registered before starting the server
    # The import statements at the top ensure decorators are executed
    
    mcp.run(transport="sse", host=args.host, port=args.port, path="/mcp/")

if __name__ == "__main__":
    # Ensure the knowledge_graphs directory is in the path for conditional imports
    knowledge_graphs_path = os.path.join(project_root, 'knowledge_graphs')
    sys.path.append(knowledge_graphs_path)
    
    main()