"""
Core server setup, context, and lifecycle management.
"""
import os
import logging
import concurrent.futures
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Optional, Any

from fastmcp import FastMCP
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.utilities.logging import get_logger
from qdrant_client import QdrantClient
from starlette.routing import Route
from sentence_transformers import CrossEncoder
from crawl4ai import AsyncWebCrawler, BrowserConfig

from src.core.validation import validate_neo4j_connection, format_neo4j_error
from src.utils import get_qdrant_client, setup_qdrant_collections


# Conditional import for knowledge graph components
if os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true":
    from knowledge_graph_validator import KnowledgeGraphValidator
    from parse_repo_into_neo4j import DirectNeo4jExtractor

# Get the logger
logger = get_logger(__name__)
log_level = os.getenv("FASTMCP_LOG_LEVEL", "INFO").upper()
logger.setLevel(log_level)

# Create a handler
handler = logging.StreamHandler()
handler.setLevel(log_level)

# Create a formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(handler)

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
    """
    browser_config = BrowserConfig(headless=True, verbose=False)
    crawler = AsyncWebCrawler(config=browser_config)
    await crawler.__aenter__()
    
    qdrant_client = get_qdrant_client()
    setup_qdrant_collections(qdrant_client)
    
    reranking_model = None
    if os.getenv("USE_RERANKING", "false") == "true":
        try:
            reranking_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        except Exception as e:
            print(f"Failed to load reranking model: {e}")

    knowledge_validator = None
    repo_extractor = None
    if os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true" and validate_neo4j_connection():
        try:
            neo4j_uri = os.getenv("NEO4J_URI")
            neo4j_user = os.getenv("NEO4J_USER")
            neo4j_password = os.getenv("NEO4J_PASSWORD")
            knowledge_validator = KnowledgeGraphValidator(neo4j_uri, neo4j_user, neo4j_password)
            await knowledge_validator.initialize()
            repo_extractor = DirectNeo4jExtractor(neo4j_uri, neo4j_user, neo4j_password)
            await repo_extractor.initialize()
            print("✓ Knowledge graph components initialized")
        except Exception as e:
            print(f"Failed to initialize Neo4j components: {format_neo4j_error(e)}")

    process_pool = concurrent.futures.ProcessPoolExecutor()

    try:
        yield Crawl4AIContext(
            crawler=crawler,
            qdrant_client=qdrant_client,
            reranking_model=reranking_model,
            knowledge_validator=knowledge_validator,
            repo_extractor=repo_extractor,
            process_pool=process_pool
        )
    finally:
        process_pool.shutdown(wait=True)
        qdrant_client.close()
        await crawler.__aexit__(None, None, None)
        if knowledge_validator:
            await knowledge_validator.close()
        if repo_extractor:
            await repo_extractor.close()

mcp = FastMCP(
    "mcp-crawl4ai-rag",
    lifespan=crawl4ai_lifespan,
    middleware=[TimingMiddleware()],
)

async def health_check(request):
    """Health check endpoint."""
    return {"status": "ok"}

mcp._additional_http_routes.append(Route("/health", health_check))

