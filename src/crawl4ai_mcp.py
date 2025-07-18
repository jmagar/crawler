"""
Main entry point for the Crawl4AI RAG MCP Server.

This file initializes the server, loads the configuration, and registers all the tools
from their respective modules.
"""
import os
import sys
import asyncio
import argparse
import signal
import multiprocessing
import logging
import traceback
from datetime import datetime
from dotenv import load_dotenv

# Add the project root to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
dotenv_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path, override=True)

# Setup comprehensive logging to file
def setup_file_logging():
    """Setup file logging with rotating logs and comprehensive debug output."""
    log_dir = os.path.join(project_root, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f'mcp_server_{timestamp}.log')
    
    # Configure root logger with comprehensive format
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)8s] %(name)s:%(lineno)d - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='w'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific loggers to debug level
    logging.getLogger('fastmcp').setLevel(logging.DEBUG)
    logging.getLogger('crawl4ai').setLevel(logging.DEBUG)
    logging.getLogger('qdrant_client').setLevel(logging.DEBUG)
    logging.getLogger('asyncio').setLevel(logging.INFO)
    
    logger = logging.getLogger(__name__)
    logger.info(f"🔍 LOGGING STARTED - Writing to: {log_file}")
    logger.info(f"🔍 Project root: {project_root}")
    logger.info(f"🔍 Environment file: {dotenv_path}")
    logger.info(f"🔍 Python path: {sys.path[:3]}")
    
    return logger

# Initialize logging immediately
logger = setup_file_logging()

# Import the server instance and the tools
from src.core.server import mcp
from src.tools import crawling_tools, kg_tools

def main():
    """Run the MCP server based on the configured transport."""
    logger.info("🚀 MAIN FUNCTION STARTED")
    
    parser = argparse.ArgumentParser(description="Crawl4AI MCP Server")
    parser.add_argument('--host', default=os.getenv("HOST", "0.0.0.0"), help='Host to bind to')
    parser.add_argument('--port', type=int, default=int(os.getenv("PORT", 8051)), help='Port to bind to')
    
    args = parser.parse_args()
    logger.info(f"🔧 Server args: host={args.host}, port={args.port}")
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.critical(f"🛑 SIGNAL RECEIVED: {signum}")
        logger.critical(f"🛑 Signal frame: {frame}")
        logger.critical(f"🛑 Current stack trace:")
        for line in traceback.format_stack():
            logger.critical(line.strip())
        print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logger.info("🔧 Signal handlers registered")
    
    # Ensure tools are imported and registered before starting the server
    # The import statements at the top ensure decorators are executed
    logger.info("🔧 Tools imported and registered")
    
    try:
        logger.info(f"🚀 STARTING MCP SERVER: transport=sse, host={args.host}, port={args.port}, path=/mcp/")
        mcp.run(transport="sse", host=args.host, port=args.port, path="/mcp/")
        logger.info("🏁 MCP SERVER RUN COMPLETED NORMALLY")
    except KeyboardInterrupt:
        logger.warning("🛑 KEYBOARD INTERRUPT RECEIVED")
        print("\n🛑 Keyboard interrupt received, shutting down...")
    except Exception as e:
        logger.critical(f"❌ CRITICAL SERVER ERROR: {e}")
        logger.critical(f"❌ Exception type: {type(e)}")
        logger.critical(f"❌ Full stack trace:")
        for line in traceback.format_exc().split('\n'):
            if line.strip():
                logger.critical(line)
        print(f"\n❌ Server error: {e}")
        sys.exit(1)
    finally:
        logger.info("🏁 MAIN FUNCTION CLEANUP")

if __name__ == "__main__":
    # Set multiprocessing start method to avoid CUDA fork issues
    multiprocessing.set_start_method('spawn', force=True)
    
    # Ensure the knowledge_graphs directory is in the path for conditional imports
    knowledge_graphs_path = os.path.join(project_root, 'knowledge_graphs')
    sys.path.append(knowledge_graphs_path)
    
    main()