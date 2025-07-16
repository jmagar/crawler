"""
MCP Resources for exposing crawled sources and URL data.
Provides comprehensive access to sources, URLs, and metadata through FastMCP resources.
"""

import json
import logging
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, parse_qs
from qdrant_client import QdrantClient
from qdrant_client import models

from fastmcp import FastMCP, Context

from src.utils.qdrant_utils import DOCUMENTS_COLLECTION, SOURCES_COLLECTION, DEFAULT_SOURCES_LIMIT
from src.utils.fastmcp_utils import get_query_parameters, get_pagination_params

logger = logging.getLogger(__name__)


def register_source_resources(mcp: FastMCP):
    """Register all source-related MCP resources."""
    
    @mcp.resource("sources://{path}")
    async def sources_resource(path: str, context: Context) -> str:
        """
        Unified handler for all sources resources.
        
        Paths:
        - overview: All sources with metadata
        - urls: All crawled URLs with filtering
        - stats: Content statistics
        
        Query Parameters:
        - limit: Number of results to return (default: varies by endpoint)
        - source_filter: Filter by source domain (e.g., github.com)
        - offset: Pagination offset (default: 0)
        """
        try:
            qdrant_client: QdrantClient = context.lifespan_context.qdrant_client
            
            # Parse query parameters from the HTTP request
            query_params = get_query_parameters()
            
            if path == "overview":
                limit = query_params.get("limit", DEFAULT_SOURCES_LIMIT)
                return await handle_sources_overview(qdrant_client, limit=limit)
            elif path == "urls":
                limit = query_params.get("limit", 100)
                source_filter = query_params.get("source_filter")
                offset = query_params.get("offset", 0)
                return await handle_all_urls(qdrant_client, limit=limit, source_filter=source_filter, offset=offset)
            elif path == "stats":
                source_filter = query_params.get("source_filter")
                return await handle_source_statistics(qdrant_client, source_filter=source_filter)
            else:
                return json.dumps({"error": "Unknown resource path"}, indent=2)
                
        except Exception as e:
            logger.error(f"Error in sources resource handler: {e}")
            return json.dumps({"error": str(e)}, indent=2)

    logger.info("✅ Source resources registered: sources://overview, sources://urls, sources://stats")


async def handle_sources_overview(qdrant_client: QdrantClient, limit: int = DEFAULT_SOURCES_LIMIT) -> str:
    """
    Provides an overview of all crawled sources with metadata.
    
    Args:
        qdrant_client: The Qdrant client instance
        limit: Maximum number of sources to fetch per batch (default from config)
    """
    try:
        sources = []
        total_sources = 0
        total_words = 0
        next_page_offset = None
        
        # Use pagination to handle large datasets efficiently
        while True:
            scroll_result = qdrant_client.scroll(
                collection_name=SOURCES_COLLECTION,
                with_payload=True,
                limit=limit,
                offset=next_page_offset
            )
            
            # Extract points and next offset
            points, next_page_offset = scroll_result
            
            if not points:
                break
                
            for point in points:
                source_data = point.payload
                sources.append({
                    "source_id": source_data.get("source_id"),
                    "summary": source_data.get("summary", "No summary available"),
                    "total_words": source_data.get("total_words", 0),
                    "updated_at": source_data.get("updated_at"),
                    "domain": source_data.get("source_id", "").split("/")[0] if source_data.get("source_id") else "unknown"
                })
                total_sources += 1
                total_words += source_data.get("total_words", 0)
            
            # If no next page offset, we've retrieved all sources
            if next_page_offset is None:
                break
        
        # Sort sources by total words (most content first)
        sources.sort(key=lambda x: x["total_words"], reverse=True)
        
        overview_data = {
            "summary": {
                "total_sources": total_sources,
                "total_words": total_words,
                "avg_words_per_source": total_words // total_sources if total_sources > 0 else 0
            },
            "sources": sources
        }
        
        return json.dumps(overview_data, indent=2)
        
    except Exception as e:
        logger.error(f"Error generating sources overview: {e}")
        error_data = {
            "error": str(e),
            "sources": []
        }
        return json.dumps(error_data, indent=2)


async def handle_all_urls(qdrant_client: QdrantClient, limit: int = 100, source_filter: str = None, offset: int = 0) -> str:
    """
    Provides a comprehensive list of all crawled URLs across all sources.
    
    Args:
        qdrant_client: The Qdrant client instance
        limit: Maximum number of URLs to return (default: 100)
        source_filter: Filter by source domain (e.g., 'github.com')
        offset: Pagination offset (default: 0)
    """
    try:
        
        # Build filter conditions
        filter_conditions = []
        if source_filter:
            filter_conditions.append(
                models.FieldCondition(
                    key="source",
                    match=models.MatchValue(value=source_filter)
                )
            )
        
        # Query documents collection for URLs
        scroll_result = qdrant_client.scroll(
            collection_name=DOCUMENTS_COLLECTION,
            with_payload=True,
            limit=limit,
            offset=offset,
            scroll_filter=models.Filter(must=filter_conditions) if filter_conditions else None
        )
        
        urls_data = []
        seen_urls = set()
        
        for point in scroll_result[0]:
            payload = point.payload
            url = payload.get("url")
            
            if url and url not in seen_urls:
                seen_urls.add(url)
                urls_data.append({
                    "url": url,
                    "source": payload.get("source", "unknown"),
                    "word_count": payload.get("word_count", 0),
                    "char_count": payload.get("char_count", 0),
                    "has_code": payload.get("has_code", False),
                    "headers": payload.get("headers", ""),
                    "content_preview": (payload.get("content", ""))[:200] + "..." if len(payload.get("content", "")) > 200 else payload.get("content", "")
                })
        
        # Sort URLs by word count (most content first)
        urls_data.sort(key=lambda x: x["word_count"], reverse=True)
        
        result_data = {
            "query_info": {
                "total_returned": len(urls_data),
                "limit": limit,
                "offset": offset,
                "source_filter": source_filter
            },
            "urls": urls_data
        }
        
        description = f"List of {len(urls_data)} URLs"
        if source_filter:
            description += f" from {source_filter}"
            
        return json.dumps(result_data, indent=2)
        
    except Exception as e:
        logger.error(f"Error retrieving URLs: {e}")
        error_data = {
            "error": str(e),
            "urls": []
        }
        return json.dumps(error_data, indent=2)


async def handle_source_statistics(qdrant_client: QdrantClient, source_filter: str = None) -> str:
    """
    Provides detailed statistics about crawled content.
    
    Args:
        qdrant_client: The Qdrant client instance
        source_filter: Filter by source domain (e.g., 'github.com')
    """
    try:
        
        # Get document statistics
        filter_conditions = []
        if source_filter:
            filter_conditions.append(
                models.FieldCondition(
                    key="source",
                    match=models.MatchValue(value=source_filter)
                )
            )
        
        scroll_result = qdrant_client.scroll(
            collection_name=DOCUMENTS_COLLECTION,
            with_payload=True,
            limit=1000,  # Get enough for good statistics
            scroll_filter=models.Filter(must=filter_conditions) if filter_conditions else None
        )
        
        # Calculate statistics
        total_chunks = 0
        total_words = 0
        total_chars = 0
        sources_stats = {}
        content_types = {"has_code": 0, "no_code": 0}
        url_count = 0
        seen_urls = set()
        
        for point in scroll_result[0]:
            payload = point.payload
            source = payload.get("source", "unknown")
            url = payload.get("url")
            word_count = payload.get("word_count", 0)
            char_count = payload.get("char_count", 0)
            has_code = payload.get("has_code", False)
            
            total_chunks += 1
            total_words += word_count
            total_chars += char_count
            
            if url and url not in seen_urls:
                seen_urls.add(url)
                url_count += 1
            
            if has_code:
                content_types["has_code"] += 1
            else:
                content_types["no_code"] += 1
            
            if source not in sources_stats:
                sources_stats[source] = {
                    "chunks": 0,
                    "words": 0,
                    "chars": 0,
                    "urls": set()
                }
            
            sources_stats[source]["chunks"] += 1
            sources_stats[source]["words"] += word_count
            sources_stats[source]["chars"] += char_count
            if url:
                sources_stats[source]["urls"].add(url)
        
        # Format source stats
        formatted_sources = {}
        for source, stats in sources_stats.items():
            formatted_sources[source] = {
                "chunks": stats["chunks"],
                "words": stats["words"],
                "chars": stats["chars"],
                "unique_urls": len(stats["urls"]),
                "avg_words_per_chunk": stats["words"] // stats["chunks"] if stats["chunks"] > 0 else 0
            }
        
        stats_data = {
            "overview": {
                "total_chunks": total_chunks,
                "total_words": total_words,
                "total_chars": total_chars,
                "unique_urls": url_count,
                "avg_words_per_chunk": total_words // total_chunks if total_chunks > 0 else 0,
                "avg_chars_per_chunk": total_chars // total_chunks if total_chunks > 0 else 0
            },
            "content_types": content_types,
            "sources": formatted_sources,
            "filter_applied": source_filter
        }
        
        description = f"Statistics for {total_chunks} chunks from {len(formatted_sources)} sources"
        if source_filter:
            description = f"Statistics for {source_filter}: {total_chunks} chunks"
        
        return json.dumps(stats_data, indent=2)
        
    except Exception as e:
        logger.error(f"Error generating statistics: {e}")
        error_data = {
            "error": str(e),
            "stats": {}
        }
        return json.dumps(error_data, indent=2)