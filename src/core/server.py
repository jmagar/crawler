"""
Core server setup, context, and lifecycle management with proper cancellation handling.
"""
import os
import logging
import multiprocessing
import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Optional, Any

from fastmcp import FastMCP
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.utilities.logging import get_logger
from src.core.cancellation_middleware import CancellationHandlingMiddleware
from qdrant_client import QdrantClient
from starlette.routing import Route
from sentence_transformers import CrossEncoder
from crawl4ai import AsyncWebCrawler, BrowserConfig

from src.core.validation import validate_neo4j_connection, format_neo4j_error
from src.core.timeout_utils import TimeoutConfig
from src.core.timeout_middleware import TimeoutMiddleware
from src.utils import get_qdrant_client, setup_qdrant_collections
from src.resources import register_source_resources


# Conditional import for knowledge graph components
if os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true":
    from knowledge_graph_validator import KnowledgeGraphValidator
    from parse_repo_into_neo4j import DirectNeo4jExtractor

# Get the logger and configure file logging
logger = get_logger(__name__)
log_level = os.getenv("FASTMCP_LOG_LEVEL", "DEBUG").upper()
logger.setLevel(log_level)

# Setup file logging for server events
import os
from datetime import datetime
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
server_log_file = os.path.join(log_dir, f'server_{timestamp}.log')

# Create file handler
file_handler = logging.FileHandler(server_log_file, mode='w')
file_handler.setLevel(log_level)

# Create stream handler
stream_handler = logging.StreamHandler()
stream_handler.setLevel(log_level)

# Create a formatter and add it to both handlers
formatter = logging.Formatter('%(asctime)s [%(levelname)8s] %(name)s:%(lineno)d - %(message)s')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

logger.info(f"🔍 SERVER LOGGING - Writing to: {server_log_file}")

@dataclass
class Crawl4AIContext:
    """Context for the Crawl4AI MCP server."""
    crawler: AsyncWebCrawler
    qdrant_client: QdrantClient
    reranking_model: Optional[CrossEncoder]
    knowledge_validator: Optional[Any]
    repo_extractor: Optional[Any]
    process_pool: concurrent.futures.ProcessPoolExecutor

def log_handler(message: logging.LogRecord):
    """Handle logs from the MCP server."""
    if message.levelname.lower() == "error":
        logger.error(message.msg)
    elif message.levelname.lower() == "info":
        logger.info(message.msg)
    elif message.levelname.lower() == "debug":
        logger.debug(message.msg)
    else:
        logger.info(message.msg)

@asynccontextmanager
async def crawl4ai_lifespan(server: FastMCP) -> AsyncIterator[Crawl4AIContext]:
    """
    Manages the application's lifecycle for all necessary clients and resources.
    Enhanced with proper error handling and cleanup for interrupted operations.
    """
    logger.info("🚀🚀🚀 CRAWL4AI LIFESPAN STARTING 🚀🚀🚀")
    logger.info(f"🔍 Server instance: {server}")
    logger.info(f"🔍 Current task: {asyncio.current_task()}")
    
    import traceback
    logger.info("🔍 Lifespan stack trace:")
    for line in traceback.format_stack():
        logger.info(f"  {line.strip()}")
    
    # Initialize components with proper error handling
    browser_config = BrowserConfig(
        headless=True, 
        verbose=False,
        browser_type="chromium",  # Explicit browser type
        sleep_on_close=False,  # Don't wait on browser close
    )
    
    crawler = None
    qdrant_client = None
    reranking_model = None
    knowledge_validator = None
    repo_extractor = None
    process_pool = None
    
    try:
        # Initialize crawler with retry logic
        logger.info("📡 Initializing web crawler...")
        crawler = AsyncWebCrawler(config=browser_config)
        await crawler.__aenter__()
        logger.info("✓ Web crawler initialized")
        
        # Initialize Qdrant client
        logger.info("🗄️ Connecting to Qdrant...")
        qdrant_client = get_qdrant_client()
        setup_qdrant_collections(qdrant_client)
        logger.info("✓ Qdrant client initialized")
        
        # Initialize reranking model if enabled
        if os.getenv("USE_RERANKING", "false") == "true":
            logger.info("🔄 Loading reranking model...")
            try:
                reranking_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
                logger.info("✓ Reranking model loaded")
            except Exception as e:
                logger.warning(f"Failed to load reranking model: {e}")

        # Initialize knowledge graph components if enabled
        if os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true" and validate_neo4j_connection():
            logger.info("🕸️ Initializing knowledge graph components...")
            try:
                neo4j_uri = os.getenv("NEO4J_URI")
                neo4j_user = os.getenv("NEO4J_USER")
                neo4j_password = os.getenv("NEO4J_PASSWORD")
                
                knowledge_validator = KnowledgeGraphValidator(neo4j_uri, neo4j_user, neo4j_password)
                await knowledge_validator.initialize()
                
                repo_extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
                await repo_extractor.initialize()
                
                logger.info("✓ Knowledge graph components initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Neo4j components: {format_neo4j_error(e)}")

        # Initialize process pool
        logger.info("⚡ Initializing process pool...")
        process_pool = concurrent.futures.ProcessPoolExecutor()
        logger.info("✓ Process pool initialized")
        
        logger.info("🎉 All components initialized successfully!")

        yield Crawl4AIContext(
            crawler=crawler,
            qdrant_client=qdrant_client,
            reranking_model=reranking_model,
            knowledge_validator=knowledge_validator,
            repo_extractor=repo_extractor,
            process_pool=process_pool
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize server components: {e}")
        raise
        
    finally:
        logger.info("🧹 Starting cleanup...")
        
        # Cleanup in reverse order of initialization
        if process_pool:
            try:
                logger.info("🔄 Shutting down process pool...")
                process_pool.shutdown(wait=True)
                logger.info("✓ Process pool shutdown")
            except Exception as e:
                logger.error(f"Error shutting down process pool: {e}")

        if knowledge_validator:
            try:
                logger.info("🕸️ Closing knowledge validator...")
                await knowledge_validator.close()
                logger.info("✓ Knowledge validator closed")
            except Exception as e:
                logger.error(f"Error closing knowledge validator: {e}")

        if repo_extractor:
            try:
                logger.info("📊 Closing repository extractor...")
                await repo_extractor.close()
                logger.info("✓ Repository extractor closed")
            except Exception as e:
                logger.error(f"Error closing repository extractor: {e}")

        if qdrant_client:
            try:
                logger.info("🗄️ Closing Qdrant client...")
                qdrant_client.close()
                logger.info("✓ Qdrant client closed")
            except Exception as e:
                logger.error(f"Error closing Qdrant client: {e}")

        if crawler:
            try:
                logger.info("📡 Closing web crawler...")
                # Use asyncio.shield to protect cleanup from cancellation
                await asyncio.shield(
                    asyncio.wait_for(crawler.__aexit__(None, None, None), timeout=TimeoutConfig.SERVER_CLEANUP_TIMEOUT)
                )
                logger.info("✓ Web crawler closed")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Web crawler close timeout, forcing shutdown")
            except asyncio.CancelledError:
                logger.warning("⚠️ Web crawler close cancelled, forcing shutdown")
            except Exception as e:
                logger.error(f"Error closing web crawler: {e}")

        logger.info("✨ Cleanup completed")

# Create the FastMCP server with cancellation handling middleware
mcp = FastMCP(
    "mcp-crawl4ai-rag",
    lifespan=crawl4ai_lifespan,
    middleware=[TimingMiddleware(), CancellationHandlingMiddleware()],
)

# CancellationHandlingMiddleware now handles cancellation gracefully without response conflicts

async def health_check(request):
    """Health check endpoint."""
    from starlette.responses import JSONResponse
    try:
        return JSONResponse({"status": "ok"})
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

mcp._additional_http_routes.append(Route("/health", health_check))

# Register MCP resources
register_source_resources(mcp)
logger.info("📋 MCP resources registered successfully")

