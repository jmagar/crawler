"""
Web crawling and RAG tools for the MCP server.
Enhanced with comprehensive cancellation handling and progress reporting.
"""
import os
import json
import asyncio
import time
import logging
import traceback
from typing import List, Dict, Any
from urllib.parse import urlparse
from datetime import datetime

from fastmcp import Context
from crawl4ai import CrawlerRunConfig, CacheMode
from src.core.timeout_utils import with_crawler_timeout, with_batch_timeout, with_timeout, TimeoutConfig
from src.core.validation import validate_crawl_dir_params
from src.utils.progress_utils import ProgressReporter
from src.utils.error_handling import MCPErrorHandler, ErrorCategory, ErrorSeverity, create_success_response
from src.utils.logging_utils import log_operation, MCPLogger, OperationMonitor

try:
    from qdrant_client.http.exceptions import ResponseHandlingException as QdrantException
except ImportError:
    # Fallback if qdrant exceptions not available
    class QdrantException(Exception):
        pass

# Setup file logging for tools
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
os.makedirs(log_dir, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
tools_log_file = os.path.join(log_dir, f'tools_{timestamp}.log')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Add file handler for tools
tools_file_handler = logging.FileHandler(tools_log_file, mode='w')
tools_file_handler.setLevel(logging.DEBUG)
tools_formatter = logging.Formatter('%(asctime)s [%(levelname)8s] %(name)s:%(lineno)d - %(message)s')
tools_file_handler.setFormatter(tools_formatter)
logger.addHandler(tools_file_handler)

logger.info(f"🔍 TOOLS LOGGING - Writing to: {tools_log_file}")

from src.core.server import mcp
from src.core.crawling import (
    is_txt,
    is_sitemap,
    parse_sitemap,
    crawl_markdown_file,
    crawl_batch,
    crawl_recursive_internal_links,
    get_enhanced_crawler_config,
    crawl_single_with_filtering,
    crawl_directory,
    convert_directory_content_to_crawl_results
)
from src.core.processing import (
    smart_chunk_markdown,
    extract_section_info,
    rerank_results,
    get_chunking_strategy
)
from src.utils import (
    add_documents_to_qdrant,
    search_documents,
    extract_code_blocks,
    generate_code_example_summary,
    add_code_examples_to_qdrant,
    update_source_info,
    extract_source_summary,
    search_code_examples as search_code_examples_util
)

@mcp.tool()
async def scrape(ctx: Context, url: str) -> str:
    """
    Crawl a single web page and store its content in Qdrant.
    Enhanced with proper cancellation handling and progress reporting.
    """
    start_time = time.time()
    operation_id = f"scrape_{url}_{int(start_time)}"
    logger.info(f"🚀🚀🚀 SCRAPE TOOL STARTED: {url} 🚀🚀🚀")
    logger.info(f"🔍 Context: {ctx}")
    logger.info(f"🔍 Request context: {getattr(ctx, 'request_context', 'MISSING')}")
    
    try:
        # Validate context and get components
        logger.info("🔍 Validating context...")
        if not hasattr(ctx.request_context, 'lifespan_context'):
            logger.error("❌ Server not properly initialized - missing lifespan_context")
            return json.dumps({"success": False, "url": url, "error": "Server not properly initialized"}, indent=2)
        
        lifespan_ctx = ctx.request_context.lifespan_context
        
        # Register this operation to prevent premature cleanup
        async with lifespan_ctx.cleanup_lock:
            lifespan_ctx.active_operations.add(operation_id)
            logger.info(f"🔒 Registered operation {operation_id}, active operations: {len(lifespan_ctx.active_operations)}")
        
        # Report initial progress
        await ctx.report_progress(progress=0, total=100)
            
        crawler = lifespan_ctx.crawler
        qdrant_client = lifespan_ctx.qdrant_client
        
        if not crawler or not qdrant_client:
            return json.dumps({"success": False, "url": url, "error": "Required components not available"}, indent=2)
        
        # Report crawling progress
        await ctx.report_progress(progress=10, total=100)
        
        run_config = get_enhanced_crawler_config()
        result = await with_crawler_timeout(
            crawler.arun(url=url, config=run_config),
            operation_name=f"scrape {url}"
        )
        
        # Report crawling completed
        await ctx.report_progress(progress=50, total=100)
        
        if result.success and result.markdown:
            source_id = urlparse(url).netloc or urlparse(url).path
            # Use improved chunking strategy
            chunking_strategy = os.getenv("CHUNKING_STRATEGY", "smart")
            chunks = smart_chunk_markdown(result.markdown, chunk_size=5000, strategy=chunking_strategy)
            
            urls, chunk_numbers, contents, metadatas = [], [], [], []
            total_word_count = 0
            
            for i, chunk in enumerate(chunks):
                urls.append(url)
                chunk_numbers.append(i)
                contents.append(chunk)
                meta = extract_section_info(chunk)
                meta["url"] = url
                meta["source"] = source_id
                metadatas.append(meta)
                total_word_count += meta.get("word_count", 0)
            
            url_to_full_document = {url: result.markdown}
            
            elapsed_time = time.time() - start_time
            source_summary = await extract_source_summary(source_id, result.markdown[:5000])
            await update_source_info(qdrant_client, source_id, source_summary, total_word_count, elapsed_time)
            
            # Report processing progress
            await ctx.report_progress(progress=70, total=100, message="Storing documents in vector database...")
            
            # Use asyncio.shield to protect critical cleanup from cancellation
            await asyncio.shield(
                add_documents_to_qdrant(qdrant_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
            )
            await ctx.report_progress(progress=80, total=100, message="Documents stored successfully")
            
            code_blocks_stored = 0
            if os.getenv("USE_AGENTIC_RAG", "false") == "true":
                await ctx.report_progress(progress=85, total=100, message="Extracting code examples...")
                code_blocks = extract_code_blocks(result.markdown)
                if code_blocks:
                    code_urls, code_chunk_numbers, code_examples_list, code_summaries, code_metadatas = [], [], [], [], []
                    summary_tasks = [generate_code_example_summary(block['code'], block['context_before'], block['context_after']) for block in code_blocks]
                    summaries = await asyncio.gather(*summary_tasks)

                    for i, block in enumerate(code_blocks):
                        code_urls.append(url)
                        code_chunk_numbers.append(i)
                        code_examples_list.append(block['code'])
                        code_summaries.append(summaries[i])
                        code_metadatas.append({"url": url, "source": source_id, "language": block['language']})
                    
                    await add_code_examples_to_qdrant(qdrant_client, code_urls, code_chunk_numbers, code_examples_list, code_summaries, code_metadatas)
                    code_blocks_stored = len(code_blocks)
                    await ctx.report_progress(progress=95, total=100, message=f"Stored {code_blocks_stored} code examples")

            await ctx.report_progress(progress=100, total=100, message="Scrape completed successfully")
            return json.dumps({
                "success": True,
                "url": url,
                "chunks_stored": len(chunks),
                "code_examples_stored": code_blocks_stored,
            }, indent=2)
        else:
            return json.dumps({"success": False, "url": url, "error": result.error_message}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)
    
    finally:
        # Always unregister the operation to prevent cleanup blocks
        try:
            if 'lifespan_ctx' in locals() and hasattr(lifespan_ctx, 'active_operations'):
                async with lifespan_ctx.cleanup_lock:
                    lifespan_ctx.active_operations.discard(operation_id)
                    logger.info(f"🔓 Unregistered operation {operation_id}, remaining: {len(lifespan_ctx.active_operations)}")
        except Exception as cleanup_error:
            logger.error(f"Error during operation cleanup: {cleanup_error}")

@mcp.tool()
async def crawl(ctx: Context, url: str, max_depth: int = 3, max_concurrent: int = 10, chunk_size: int = 5000) -> str:
    """
    Intelligently crawl a URL and store content in Qdrant.
    Enhanced with interruption handling and recovery.
    """
    start_time = time.time()
    crawl_results = []
    operation_id = f"crawl_{url}_{int(start_time)}"
    
    try:
        # Validate context and get components
        if not hasattr(ctx.request_context, 'lifespan_context'):
            return json.dumps({"success": False, "url": url, "error": "Server not properly initialized"}, indent=2)
            
        lifespan_ctx = ctx.request_context.lifespan_context
        crawler = lifespan_ctx.crawler
        qdrant_client = lifespan_ctx.qdrant_client
        
        if not crawler or not qdrant_client:
            return json.dumps({"success": False, "url": url, "error": "Required components not available"}, indent=2)
        
        # Register this operation to prevent premature cleanup
        async with lifespan_ctx.cleanup_lock:
            lifespan_ctx.active_operations.add(operation_id)
            logger.info(f"🔒 Registered operation {operation_id}, active operations: {len(lifespan_ctx.active_operations)}")
        
        await ctx.report_progress(progress=0, total=100, message="Starting crawl...")
        
        # Determine crawl strategy based on URL type
        try:
            if is_txt(url):
                await ctx.report_progress(progress=10, total=100, message="Processing text file...")
                crawl_results = await with_crawler_timeout(
                    crawl_markdown_file(crawler, url),
                    operation_name=f"crawl text file {url}"
                )
            elif is_sitemap(url):
                await ctx.report_progress(progress=10, total=100, message="Parsing sitemap...")
                sitemap_urls = parse_sitemap(url, max_urls=50)  # Limit sitemap URLs
                if sitemap_urls:
                    await ctx.report_progress(progress=15, total=100, message=f"Crawling {len(sitemap_urls)} URLs from sitemap...")
                    crawl_results = await with_batch_timeout(
                        crawl_batch(crawler, sitemap_urls, max_concurrent=min(max_concurrent, 50)),
                        operation_name=f"crawl sitemap batch {url}"
                    )
            else:
                await ctx.report_progress(progress=10, total=100, message="Starting recursive crawl...")
                crawl_results = await with_timeout(
                    crawl_recursive_internal_links(
                        crawler, [url], 
                        max_depth=min(max_depth, 3),  # Increased depth limit
                        max_concurrent=min(max_concurrent, 50)
                    ),
                    timeout_seconds=TimeoutConfig.CRAWLER_RECURSIVE_TIMEOUT,
                    operation_name=f"recursive crawl {url}"
                )
        except Exception as crawl_error:
            print(f"Crawl error: {crawl_error}")
            # If crawl partially succeeded, continue with what we have
            if not crawl_results:
                return json.dumps({"success": False, "url": url, "error": f"Crawl failed: {str(crawl_error)}"}, indent=2)

        if not crawl_results:
            return json.dumps({"success": False, "url": url, "error": "No content found or crawl was interrupted"}, indent=2)

        await ctx.report_progress(progress=25, total=100, message=f"Processing {len(crawl_results)} documents...")

        # Process crawled content with error handling
        source_content_map = {}
        source_word_counts = {}
        all_urls, all_chunk_numbers, all_contents, all_metadatas = [], [], [], []
        
        processed_docs = 0
        for doc in crawl_results:
            try:
                if not doc.markdown or not doc.url:
                    continue
                    
                source_url = doc.url
                md = doc.markdown
                
                # Use improved chunking strategy
                chunking_strategy = os.getenv("CHUNKING_STRATEGY", "smart")
                chunks = smart_chunk_markdown(md, chunk_size=chunk_size, strategy=chunking_strategy)
                source_id = urlparse(source_url).netloc or urlparse(source_url).path
                
                if source_id not in source_content_map:
                    source_content_map[source_id] = md[:5000]
                    source_word_counts[source_id] = 0

                for i, chunk in enumerate(chunks):
                    all_urls.append(source_url)
                    all_chunk_numbers.append(i)
                    all_contents.append(chunk)
                    meta = extract_section_info(chunk)
                    meta["url"] = source_url
                    meta["source"] = source_id
                    all_metadatas.append(meta)
                    source_word_counts[source_id] += meta.get("word_count", 0)
                
                processed_docs += 1
                if processed_docs % 5 == 0:  # Progress update every 5 docs
                    progress = 25 + (processed_docs / len(crawl_results)) * 25
                    await ctx.report_progress(progress=int(progress), total=100, message=f"Processed {processed_docs}/{len(crawl_results)} documents...")
                    
            except Exception as doc_error:
                print(f"Error processing document {doc.url}: {doc_error}")
                continue

        if not all_contents:
            return json.dumps({"success": False, "url": url, "error": "No valid content extracted from crawled pages"}, indent=2)

        url_to_full_document = {doc.url: doc.markdown for doc in crawl_results if doc.markdown}

        await ctx.report_progress(progress=50, total=100, message="Updating source info...")

        # Update source information with error handling
        elapsed_time = time.time() - start_time
        for source_id, content in source_content_map.items():
            try:
                summary = await extract_source_summary(source_id, content)
                await update_source_info(qdrant_client, source_id, summary, source_word_counts.get(source_id, 0), elapsed_time)
            except Exception as source_error:
                print(f"Error updating source {source_id}: {source_error}")

        await ctx.report_progress(progress=75, total=100, message="Adding documents to Qdrant...")
        
        try:
            await add_documents_to_qdrant(qdrant_client, all_urls, all_chunk_numbers, all_contents, all_metadatas, url_to_full_document)
        except Exception as db_error:
            return json.dumps({"success": False, "url": url, "error": f"Failed to store documents: {str(db_error)}"}, indent=2)

        # Process code examples if enabled
        code_examples_stored = 0
        if os.getenv("USE_AGENTIC_RAG", "false") == "true":
            try:
                await ctx.report_progress(progress=85, total=100, message="Processing code examples...")
                
                all_code_blocks_data = []
                for doc in crawl_results:
                    if doc.markdown:
                        code_blocks = extract_code_blocks(doc.markdown)
                        for block in code_blocks:
                            block['source_url'] = doc.url
                            all_code_blocks_data.append(block)
                
                if all_code_blocks_data:
                    code_urls, code_chunk_numbers, code_examples_list, code_summaries, code_metadatas = [], [], [], [], []
                    
                    # Limit code examples to prevent overload
                    limited_code_blocks = all_code_blocks_data[:100]  # Max 100 code examples
                    
                    summary_tasks = [generate_code_example_summary(block['code'], block['context_before'], block['context_after']) for block in limited_code_blocks]
                    summaries = await asyncio.gather(*summary_tasks, return_exceptions=True)

                    for i, block in enumerate(limited_code_blocks):
                        if isinstance(summaries[i], Exception):
                            continue
                            
                        source_url = block['source_url']
                        source_id = urlparse(source_url).netloc or urlparse(source_url).path
                        code_urls.append(source_url)
                        code_chunk_numbers.append(i)
                        code_examples_list.append(block['code'])
                        code_summaries.append(summaries[i])
                        code_metadatas.append({"url": source_url, "source": source_id, "language": block['language']})
                    
                    if code_urls:
                        await add_code_examples_to_qdrant(qdrant_client, code_urls, code_chunk_numbers, code_examples_list, code_summaries, code_metadatas)
                        code_examples_stored = len(code_urls)
                        
            except Exception as code_error:
                print(f"Error processing code examples: {code_error}")

        elapsed_time = time.time() - start_time
        await ctx.report_progress(progress=100, total=100, message=f"Crawl complete in {elapsed_time:.2f}s.")

        return json.dumps({
            "success": True,
            "url": url,
            "pages_crawled": len(crawl_results),
            "chunks_stored": len(all_contents),
            "code_examples_stored": code_examples_stored,
            "elapsed_time_seconds": round(elapsed_time, 2)
        }, indent=2)
        
    except asyncio.CancelledError:
        # Let cancellation propagate to MCP framework - don't return a response
        elapsed_time = time.time() - start_time
        logger.warning(f"🛑🛑🛑 CRAWL CANCELLED: {url} after {elapsed_time:.2f}s 🛑🛑🛑")
        logger.warning("🔍 Current stack trace on cancellation:")
        for line in traceback.format_stack():
            logger.warning(f"  {line.strip()}")
        logger.warning("🛑 Re-raising CancelledError to MCP framework")
        raise
        
    except TimeoutError:
        # Handle timeouts with proper response
        elapsed_time = time.time() - start_time
        return json.dumps({
            "success": False, 
            "url": url, 
            "error": "Crawl operation timed out",
            "elapsed_time_seconds": round(elapsed_time, 2),
            "partial_results": {
                "pages_crawled": len(crawl_results) if 'crawl_results' in locals() else 0,
                "chunks_stored": 0
            }
        }, indent=2)
        
        
    except Exception as e:
        await ctx.error(f"Crawling failed for {url}: {str(e)}")
        elapsed_time = time.time() - start_time
        return json.dumps({
            "success": False, 
            "url": url, 
            "error": str(e),
            "elapsed_time_seconds": round(elapsed_time, 2),
            "partial_results": {
                "pages_crawled": len(crawl_results) if 'crawl_results' in locals() else 0,
                "chunks_stored": 0
            }
        }, indent=2)
    
    finally:
        # Always unregister the operation to prevent cleanup blocks
        try:
            if 'lifespan_ctx' in locals() and hasattr(lifespan_ctx, 'active_operations'):
                async with lifespan_ctx.cleanup_lock:
                    lifespan_ctx.active_operations.discard(operation_id)
                    logger.info(f"🔓 Unregistered operation {operation_id}, remaining: {len(lifespan_ctx.active_operations)}")
        except Exception as cleanup_error:
            logger.error(f"Error during operation cleanup: {cleanup_error}")

@mcp.tool()
async def available_sources(ctx: Context) -> str:
    """
    Get all available sources from the Qdrant sources collection.
    """
    try:
        reporter = ProgressReporter(ctx, "available_sources", 100)
        await reporter.start("Fetching available sources...")
        
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        
        await reporter.update(30, "Querying sources collection...")
        scroll_result = qdrant_client.scroll(
            collection_name='sources',
            with_payload=True,
            limit=200
        )
        
        await reporter.update(80, "Processing source data...")
        sources = [point.payload for point in scroll_result[0]]
        
        await reporter.complete(f"Found {len(sources)} sources")
        return create_success_response(
            tool_name="available_sources",
            data={"sources": sources, "count": len(sources)},
            message=f"Found {len(sources)} available sources"
        )
    except asyncio.CancelledError:
        # Handle cancellation with standardized error
        error_handler = MCPErrorHandler("available_sources")
        error = error_handler.handle_cancellation_error("available_sources")
        return await error_handler.log_and_report_error(ctx, error)
    except Exception as e:
        # Handle general errors with standardized error handling
        error_handler = MCPErrorHandler("available_sources")
        if "QdrantException" in str(type(e)):
            error = error_handler.handle_database_error(e, "sources", "scroll")
        else:
            error = error_handler.create_error(
                e,
                category=ErrorCategory.INTERNAL,
                error_code="SOURCES_FETCH_FAILED"
            )
        return await error_handler.log_and_report_error(ctx, error)

@mcp.tool()
async def rag_query(ctx: Context, query: str, source: str = None, match_count: int = 5) -> str:
    """
    Perform a RAG query on the stored content in Qdrant.
    """
    start_time = time.time()
    operation_id = f"rag_query_{hash(query)}_{int(start_time)}"
    
    try:
        # Validate context and get components
        if not hasattr(ctx.request_context, 'lifespan_context'):
            return json.dumps({"success": False, "error": "Server not properly initialized"}, indent=2)
            
        lifespan_ctx = ctx.request_context.lifespan_context
        qdrant_client = lifespan_ctx.qdrant_client
        reranking_model = lifespan_ctx.reranking_model
        process_pool = lifespan_ctx.process_pool
        
        await ctx.report_progress(progress=0, total=100, message="Starting RAG query...")
        
        # Register this operation for reranking queries to prevent cleanup interference
        use_reranking = os.getenv("USE_RERANKING", "false") == "true"
        if use_reranking and reranking_model:
            async with lifespan_ctx.cleanup_lock:
                lifespan_ctx.active_operations.add(operation_id)
                logger.info(f"🔒 Registered operation {operation_id}, active operations: {len(lifespan_ctx.active_operations)}")
        
        await ctx.report_progress(progress=20, total=100, message="Searching vector database...")
        filter_metadata = {"source": source} if source else None
        
        results = await search_documents(
            client=qdrant_client,
            query=query,
            match_count=match_count,
            filter_metadata=filter_metadata
        )
        
        await ctx.report_progress(progress=60, total=100, message=f"Found {len(results)} initial matches")
        
        if use_reranking and reranking_model:
            await ctx.report_progress(progress=70, total=100, message="Reranking results for relevance...")
            results = await rerank_results(process_pool, reranking_model, query, results, content_key="content")
            await ctx.report_progress(progress=95, total=100, message="Reranking complete")
        
        await ctx.report_progress(progress=100, total=100, message="Query completed successfully")

        return create_success_response(
            tool_name="rag_query",
            data={
                "query": query,
                "source": source,
                "match_count": match_count,
                "results": results,
                "results_count": len(results),
                "reranking_used": use_reranking and reranking_model is not None
            },
            message=f"Found {len(results)} results for query: {query[:50]}..."
        )
    except asyncio.CancelledError:
        # Handle cancellation with standardized error
        error_handler = MCPErrorHandler("rag_query", operation_id)
        error = error_handler.handle_cancellation_error("rag_query")
        return await error_handler.log_and_report_error(ctx, error)
    except Exception as e:
        # Handle general errors with standardized error handling
        error_handler = MCPErrorHandler("rag_query", operation_id)
        if "QdrantException" in str(type(e)) or "qdrant" in str(e).lower():
            error = error_handler.handle_database_error(e, "documents", "search")
        elif "timeout" in str(e).lower():
            error = error_handler.handle_timeout_error(e, operation_name="rag_search")
        else:
            error = error_handler.create_error(
                e,
                category=ErrorCategory.INTERNAL,
                error_code="RAG_QUERY_FAILED",
                context={"query": query, "source": source}
            )
        return await error_handler.log_and_report_error(ctx, error)
    
    finally:
        # Always unregister the operation if it was registered
        try:
            if 'lifespan_ctx' in locals() and hasattr(lifespan_ctx, 'active_operations'):
                if operation_id in lifespan_ctx.active_operations:
                    async with lifespan_ctx.cleanup_lock:
                        lifespan_ctx.active_operations.discard(operation_id)
                        logger.info(f"🔓 Unregistered operation {operation_id}, remaining: {len(lifespan_ctx.active_operations)}")
        except Exception as cleanup_error:
            logger.error(f"Error during operation cleanup: {cleanup_error}")

@mcp.tool()
async def search_code_examples(ctx: Context, query: str, source_id: str = None, match_count: int = 5) -> str:
    """
    Search for code examples in Qdrant.
    """
    if os.getenv("USE_AGENTIC_RAG", "false") != "true":
        return json.dumps({"success": False, "error": "Agentic RAG is not enabled."}, indent=2)

    try:
        await ctx.report_progress(progress=0, total=100, message="Starting code example search...")
        
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        reranking_model = ctx.request_context.lifespan_context.reranking_model
        process_pool = ctx.request_context.lifespan_context.process_pool

        await ctx.report_progress(progress=30, total=100, message="Searching code examples in vector database...")
        results = await search_code_examples_util(
            client=qdrant_client,
            query=query,
            match_count=match_count,
            source_id=source_id
        )

        await ctx.report_progress(progress=70, total=100, message=f"Found {len(results)} code examples")
        
        use_reranking = os.getenv("USE_RERANKING", "false") == "true"
        if use_reranking and reranking_model:
            await ctx.report_progress(progress=80, total=100, message="Reranking code examples...")
            results = await rerank_results(process_pool, reranking_model, query, results, content_key="content")

        await ctx.report_progress(progress=100, total=100, message="Code example search completed")
        return create_success_response(
            tool_name="search_code_examples",
            data={
                "query": query,
                "source_id": source_id,
                "match_count": match_count,
                "results": results,
                "results_count": len(results)
            },
            message=f"Found {len(results)} code examples"
        )
    except asyncio.CancelledError:
        # Handle cancellation with standardized error
        error_handler = MCPErrorHandler("search_code_examples")
        error = error_handler.handle_cancellation_error("search_code_examples")
        return await error_handler.log_and_report_error(ctx, error)
    except Exception as e:
        # Handle general errors with standardized error handling
        error_handler = MCPErrorHandler("search_code_examples")
        if "QdrantException" in str(type(e)) or "qdrant" in str(e).lower():
            error = error_handler.handle_database_error(e, "code_examples", "search")
        else:
            error = error_handler.create_error(
                e,
                category=ErrorCategory.INTERNAL,
                error_code="CODE_SEARCH_FAILED",
                context={"query": query, "source_id": source_id}
            )
        return await error_handler.log_and_report_error(ctx, error)

@mcp.tool()
async def crawl_dir(
    ctx: Context, 
    directory_path: str, 
    max_files: int = 500, 
    max_file_size: int = 1048576,  # 1MB in bytes
    exclude_patterns: List[str] = None,
    include_patterns: List[str] = None,
    chunk_size: int = 5000
) -> str:
    """
    Crawl a local directory, process files, generate embeddings, and store in both Qdrant and Neo4j.
    
    Args:
        directory_path: Path to the directory to crawl
        max_files: Maximum number of files to process (default: 500)
        max_file_size: Maximum file size in bytes (default: 1MB)
        exclude_patterns: List of patterns to exclude from crawling
        include_patterns: List of patterns to include (overrides default text file detection)
        chunk_size: Size of chunks for processing (default: 5000)
    """
    start_time = time.time()
    operation_id = f"crawl_dir_{hash(directory_path)}_{int(start_time)}"
    
    # Initialize error handler and enhanced logging
    error_handler = MCPErrorHandler("crawl_dir", operation_id)
    mcp_logger = OperationMonitor().get_logger("crawl_dir")
    
    async with log_operation(ctx, "crawl_dir", operation_id, {"directory_path": directory_path, "max_files": max_files}) as op_logger:
        try:
            # Validate context and get components first
            if not hasattr(ctx.request_context, 'lifespan_context'):
                return json.dumps({"success": False, "error": "Server not properly initialized"}, indent=2)
                
            lifespan_ctx = ctx.request_context.lifespan_context
            
            # Register this operation to prevent premature cleanup
            async with lifespan_ctx.cleanup_lock:
                lifespan_ctx.active_operations.add(operation_id)
                logger.info(f"🔒 Registered operation {operation_id}, active operations: {len(lifespan_ctx.active_operations)}")
            
            # Validate parameters first
            validation_result = validate_crawl_dir_params(
                directory_path=directory_path,
                max_files=max_files,
                max_file_size=max_file_size,
                exclude_patterns=exclude_patterns,
                include_patterns=include_patterns,
                chunk_size=chunk_size
            )
            
            if not validation_result["valid"]:
                error_msg = "; ".join(validation_result["errors"])
                error = error_handler.handle_validation_error(
                    f"Validation failed: {error_msg}",
                    field_name="directory_path",
                    provided_value=directory_path
                )
                return await error_handler.log_and_report_error(ctx, error)
        
            # Use normalized directory path
            directory_path = validation_result["normalized_directory_path"]
            
            # Validate context and get components
            if not hasattr(ctx.request_context, 'lifespan_context'):
                error = error_handler.create_error(
                    "Server not properly initialized - missing lifespan_context",
                    category=ErrorCategory.INTERNAL,
                    severity=ErrorSeverity.CRITICAL,
                    error_code="MISSING_LIFESPAN_CONTEXT"
                )
                return await error_handler.log_and_report_error(ctx, error)
            
            qdrant_client = ctx.request_context.lifespan_context.qdrant_client
            if not qdrant_client:
                error = error_handler.handle_resource_error(
                    "Qdrant client not available",
                    resource_type="qdrant_client"
                )
                return await error_handler.log_and_report_error(ctx, error)
            
            # Report initial progress
            await ctx.report_progress(progress=0, total=100, message="Starting directory crawl...")
            
            await ctx.report_progress(progress=10, total=100, message="Scanning directory for files...")
            
            # Crawl directory to get file contents
            try:
                file_results = await with_timeout(
                    crawl_directory(
                        directory_path=directory_path,
                        max_files=max_files,
                        max_file_size=max_file_size,
                        exclude_patterns=exclude_patterns or [],
                        include_patterns=include_patterns
                    ),
                    timeout_seconds=TimeoutConfig.CRAWLER_DIRECTORY_TIMEOUT,
                    operation_name=f"crawl directory {directory_path}"
                )
            except asyncio.TimeoutError as timeout_error:
                error = error_handler.handle_timeout_error(timeout_error, TimeoutConfig.CRAWLER_DIRECTORY_TIMEOUT, "crawl_directory")
                return await error_handler.log_and_report_error(ctx, error)
            except Exception as crawl_error:
                error = error_handler.create_error(crawl_error, category=ErrorCategory.FILESYSTEM, error_code="DIRECTORY_CRAWL_FAILED")
                return await error_handler.log_and_report_error(ctx, error)
            
            if not file_results:
                error = error_handler.create_error(
                    "No readable text files found in directory",
                    category=ErrorCategory.VALIDATION,
                    error_code="NO_FILES_FOUND",
                    context={"directory_path": directory_path}
                )
                return await error_handler.log_and_report_error(ctx, error)
            
            await ctx.report_progress(progress=25, total=100, message=f"Found {len(file_results)} files, converting to crawl results...")
            
            # Convert to crawl results format for pipeline compatibility
            crawl_results = await convert_directory_content_to_crawl_results(file_results)
            
            await ctx.report_progress(progress=30, total=100, message="Processing files and generating chunks...")
            
            # Process crawled content using extracted helper function
            source_content_map, source_word_counts, all_urls, all_chunk_numbers, all_contents, all_metadatas = await _process_crawl_results(
                ctx, crawl_results, directory_path, chunk_size
            )
            
            if not all_contents:
                error = error_handler.create_error(
                    "No valid content extracted from directory files",
                    category=ErrorCategory.INTERNAL,
                    error_code="NO_CONTENT_EXTRACTED",
                    context={"directory_path": directory_path, "files_processed": len(crawl_results)}
                )
                return await error_handler.log_and_report_error(ctx, error)
            
            await ctx.report_progress(progress=70, total=100, message="Updating source information...")
            
            # Update source information using extracted helper function
            await _update_sources(ctx, source_content_map, source_word_counts, start_time)
            
            await ctx.report_progress(progress=80, total=100, message="Storing documents in Qdrant...")
            
            # Store in Qdrant using existing pipeline
            url_to_full_document = {result.url: result.markdown for result in crawl_results if result.markdown}
            
            try:
                await add_documents_to_qdrant(qdrant_client, all_urls, all_chunk_numbers, all_contents, all_metadatas, url_to_full_document)
            except QdrantException as qdrant_error:
                error = error_handler.handle_database_error(qdrant_error, "documents", "add_documents")
                return await error_handler.log_and_report_error(ctx, error)
            except Exception as db_error:
                error = error_handler.handle_database_error(db_error, "documents", "add_documents")
                return await error_handler.log_and_report_error(ctx, error)
            
            # Process code examples using extracted helper function
            code_examples_stored = await _process_code_examples(ctx, crawl_results, directory_path)
            
            # Store in Neo4j using extracted helper function
            neo4j_stored = await _store_in_neo4j(ctx, directory_path)
            
            elapsed_time = time.time() - start_time
            await ctx.report_progress(progress=100, total=100, message=f"Directory crawl complete in {elapsed_time:.2f}s")
            
            return create_success_response(
                tool_name="crawl_dir",
                data={
                    "directory": directory_path,
                    "files_processed": len(crawl_results),
                    "chunks_stored": len(all_contents),
                    "code_examples_stored": code_examples_stored,
                    "neo4j_stored": neo4j_stored
                },
                operation_id=operation_id,
                elapsed_time=elapsed_time
            )
        
        except asyncio.CancelledError:
            # Handle cancellation with standardized error
            error = error_handler.handle_cancellation_error("crawl_dir")
            return await error_handler.log_and_report_error(ctx, error)
            
        except Exception as e:
            # Handle general errors with standardized error handling
            if "QdrantException" in str(type(e)) or "qdrant" in str(e).lower():
                error = error_handler.handle_database_error(e, "documents", "store")
            elif "timeout" in str(e).lower():
                error = error_handler.handle_timeout_error(
                    e,
                    timeout_seconds=TimeoutConfig.CRAWLER_DIRECTORY_TIMEOUT,
                    operation_name="crawl_directory"
                )
            elif "permission" in str(e).lower() or "access" in str(e).lower():
                error = error_handler.create_error(
                    e,
                    category=ErrorCategory.FILESYSTEM,
                    error_code="DIRECTORY_ACCESS_DENIED",
                    context={"directory_path": directory_path}
                )
            else:
                error = error_handler.create_error(
                    e,
                    category=ErrorCategory.INTERNAL,
                    error_code="CRAWL_DIR_FAILED",
                    context={"directory_path": directory_path}
                )
            return await error_handler.log_and_report_error(ctx, error, include_traceback=True)
        
        finally:
            # Always unregister the operation to prevent cleanup blocks
            try:
                if 'lifespan_ctx' in locals() and hasattr(lifespan_ctx, 'active_operations'):
                    async with lifespan_ctx.cleanup_lock:
                        lifespan_ctx.active_operations.discard(operation_id)
                        mcp_logger.info(f"Unregistered operation {operation_id}, remaining: {len(lifespan_ctx.active_operations)}")
            except Exception as cleanup_error:
                mcp_logger.error(f"Error during operation cleanup: {cleanup_error}")


async def _process_crawl_results(ctx: Context, crawl_results: List[Any], directory_path: str, chunk_size: int) -> tuple:
    """
    Process crawled content using existing pipeline and return structured data.
    
    Args:
        ctx: Context for progress reporting
        crawl_results: List of crawl result objects
        directory_path: Path to the directory being crawled
        chunk_size: Size of chunks for processing
        
    Returns:
        Tuple of (source_content_map, source_word_counts, all_urls, all_chunk_numbers, all_contents, all_metadatas)
    """
    source_content_map = {}
    source_word_counts = {}
    all_urls, all_chunk_numbers, all_contents, all_metadatas = [], [], [], []
    
    processed_files = 0
    for result in crawl_results:
        try:
            if not result.markdown or not result.url:
                continue
            
            source_url = result.url
            md = result.markdown
            
            # Use existing chunking strategy
            chunking_strategy = os.getenv("CHUNKING_STRATEGY", "smart")
            chunks = smart_chunk_markdown(md, chunk_size=chunk_size, strategy=chunking_strategy)
            source_id = f"local_dir:{os.path.basename(directory_path)}"
            
            if source_id not in source_content_map:
                source_content_map[source_id] = md[:5000]
                source_word_counts[source_id] = 0
            
            for i, chunk in enumerate(chunks):
                all_urls.append(source_url)
                all_chunk_numbers.append(i)
                all_contents.append(chunk)
                
                # Enhanced metadata for directory crawling
                meta = extract_section_info(chunk)
                meta["url"] = source_url
                meta["source"] = source_id
                meta["file_metadata"] = result.metadata  # Include original file metadata
                all_metadatas.append(meta)
                source_word_counts[source_id] += meta.get("word_count", 0)
            
            processed_files += 1
            if processed_files % 10 == 0:  # Progress update every 10 files
                progress = 30 + (processed_files / len(crawl_results)) * 40
                await ctx.report_progress(progress=int(progress), total=100, message=f"Processed {processed_files}/{len(crawl_results)} files...")
            
        except (IOError, OSError) as io_error:
            logger.exception(f"⚠️ I/O error processing file {result.url}: {io_error}")
            continue
        except Exception as file_error:
            logger.exception(f"⚠️ Error processing file {result.url}: {file_error}")
            continue
    
    return source_content_map, source_word_counts, all_urls, all_chunk_numbers, all_contents, all_metadatas


async def _process_code_examples(ctx: Context, crawl_results: List[Any], directory_path: str) -> int:
    """
    Process code examples if enabled and return count of stored examples.
    
    Args:
        ctx: Context for progress reporting
        crawl_results: List of crawl result objects
        directory_path: Path to the directory being crawled
        
    Returns:
        Number of code examples stored
    """
    code_examples_stored = 0
    if os.getenv("USE_AGENTIC_RAG", "false") == "true":
        try:
            qdrant_client = ctx.request_context.lifespan_context.qdrant_client
            await ctx.report_progress(progress=85, total=100, message="Processing code examples...")
            
            all_code_blocks_data = []
            for result in crawl_results:
                if result.markdown:
                    code_blocks = extract_code_blocks(result.markdown)
                    for block in code_blocks:
                        block['source_url'] = result.url
                        all_code_blocks_data.append(block)
            
            if all_code_blocks_data:
                # Limit code examples to prevent overload
                limited_code_blocks = all_code_blocks_data[:100]
                
                code_urls, code_chunk_numbers, code_examples_list, code_summaries, code_metadatas = [], [], [], [], []
                summary_tasks = [generate_code_example_summary(block['code'], block['context_before'], block['context_after']) for block in limited_code_blocks]
                summaries = await asyncio.gather(*summary_tasks, return_exceptions=True)
                
                for i, block in enumerate(limited_code_blocks):
                    if isinstance(summaries[i], Exception):
                        continue
                    
                    source_url = block['source_url']
                    source_id = f"local_dir:{os.path.basename(directory_path)}"
                    code_urls.append(source_url)
                    code_chunk_numbers.append(i)
                    code_examples_list.append(block['code'])
                    code_summaries.append(summaries[i])
                    code_metadatas.append({"url": source_url, "source": source_id, "language": block['language']})
                
                if code_urls:
                    await add_code_examples_to_qdrant(qdrant_client, code_urls, code_chunk_numbers, code_examples_list, code_summaries, code_metadatas)
                    code_examples_stored = len(code_urls)
                    
        except Exception as code_error:
            logger.warning(f"⚠️ Error processing code examples: {code_error}")
    
    return code_examples_stored


async def _store_in_neo4j(ctx: Context, directory_path: str) -> bool:
    """
    Store directory data in Neo4j knowledge graph if enabled.
    
    Args:
        ctx: Context for progress reporting
        directory_path: Path to the directory being crawled
        
    Returns:
        True if successfully stored, False otherwise
    """
    neo4j_stored = False
    if os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true":
        try:
            await ctx.report_progress(progress=90, total=100, message="Storing in Neo4j knowledge graph...")
            repo_extractor = ctx.request_context.lifespan_context.repo_extractor
            if repo_extractor:
                # Create a pseudo repo URL for directory
                pseudo_repo_url = f"file://{directory_path}"
                await repo_extractor.analyze_local_directory(directory_path, pseudo_repo_url)
                neo4j_stored = True
        except Exception as neo4j_error:
            logger.warning(f"⚠️ Error storing in Neo4j: {neo4j_error}")
    
    return neo4j_stored


async def _update_sources(ctx: Context, source_content_map: Dict[str, str], source_word_counts: Dict[str, int], start_time: float):
    """
    Update source information in Qdrant.
    
    Args:
        ctx: Context for access to Qdrant client
        source_content_map: Map of source IDs to content
        source_word_counts: Map of source IDs to word counts
        start_time: Start time for elapsed time calculation
    """
    qdrant_client = ctx.request_context.lifespan_context.qdrant_client
    elapsed_time = time.time() - start_time
    
    for source_id, content in source_content_map.items():
        try:
            summary = await extract_source_summary(source_id, content)
            await update_source_info(qdrant_client, source_id, summary, source_word_counts.get(source_id, 0), elapsed_time)
        except Exception as source_error:
            logger.warning(f"⚠️ Error updating source {source_id}: {source_error}")

