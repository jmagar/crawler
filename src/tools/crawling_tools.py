"""
Web crawling and RAG tools for the MCP server.
Enhanced with comprehensive cancellation handling and progress reporting.
"""
import os
import json
import asyncio
import time
from typing import List, Dict, Any
from urllib.parse import urlparse

from fastmcp import Context
from crawl4ai import CrawlerRunConfig, CacheMode

from src.core.server import mcp
from src.core.crawling import (
    is_txt,
    is_sitemap,
    parse_sitemap,
    crawl_markdown_file,
    crawl_batch,
    crawl_recursive_internal_links,
    get_enhanced_crawler_config,
    crawl_single_with_filtering
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
    
    try:
        # Validate context and get components
        if not hasattr(ctx.request_context, 'lifespan_context'):
            return json.dumps({"success": False, "url": url, "error": "Server not properly initialized"}, indent=2)
        
        # Report initial progress
        await ctx.report_progress(progress=0, total=100)
            
        crawler = ctx.request_context.lifespan_context.crawler
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        
        if not crawler or not qdrant_client:
            return json.dumps({"success": False, "url": url, "error": "Required components not available"}, indent=2)
        
        # Report crawling progress
        await ctx.report_progress(progress=10, total=100)
        
        run_config = get_enhanced_crawler_config()
        result = await crawler.arun(url=url, config=run_config)
        
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
            await ctx.report_progress(progress=80, total=100)
            
            # Use asyncio.shield to protect critical cleanup from cancellation
            await asyncio.shield(
                add_documents_to_qdrant(qdrant_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
            )
            
            code_blocks_stored = 0
            if os.getenv("USE_AGENTIC_RAG", "false") == "true":
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

@mcp.tool()
async def crawl(ctx: Context, url: str, max_depth: int = 3, max_concurrent: int = 10, chunk_size: int = 5000) -> str:
    """
    Intelligently crawl a URL and store content in Qdrant.
    Enhanced with interruption handling and recovery.
    """
    start_time = time.time()
    crawl_results = []
    try:
        # Validate context and get components
        if not hasattr(ctx.request_context, 'lifespan_context'):
            return json.dumps({"success": False, "url": url, "error": "Server not properly initialized"}, indent=2)
            
        crawler = ctx.request_context.lifespan_context.crawler
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        
        if not crawler or not qdrant_client:
            return json.dumps({"success": False, "url": url, "error": "Required components not available"}, indent=2)
        
        await ctx.report_progress(progress=0, total=100, message="Starting crawl...")
        
        # Determine crawl strategy based on URL type
        try:
            if is_txt(url):
                await ctx.report_progress(progress=10, total=100, message="Processing text file...")
                crawl_results = await crawl_markdown_file(crawler, url)
            elif is_sitemap(url):
                await ctx.report_progress(progress=10, total=100, message="Parsing sitemap...")
                sitemap_urls = parse_sitemap(url, max_urls=50)  # Limit sitemap URLs
                if sitemap_urls:
                    await ctx.report_progress(progress=15, total=100, message=f"Crawling {len(sitemap_urls)} URLs from sitemap...")
                    crawl_results = await crawl_batch(crawler, sitemap_urls, max_concurrent=min(max_concurrent, 50))
            else:
                await ctx.report_progress(progress=10, total=100, message="Starting recursive crawl...")
                crawl_results = await crawl_recursive_internal_links(
                    crawler, [url], 
                    max_depth=min(max_depth, 3),  # Increased depth limit
                    max_concurrent=min(max_concurrent, 50)
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
        # Handle graceful cancellation
        elapsed_time = time.time() - start_time
        return json.dumps({
            "success": False, 
            "url": url, 
            "error": "Crawl was cancelled",
            "elapsed_time_seconds": round(elapsed_time, 2),
            "partial_results": {
                "pages_crawled": len(crawl_results),
                "chunks_stored": 0
            }
        }, indent=2)
        
    except asyncio.CancelledError:
        # Handle cancellation gracefully
        await ctx.warning(f"Crawling cancelled for {url}")
        elapsed_time = time.time() - start_time
        return json.dumps({
            "success": False, 
            "url": url, 
            "error": "Operation cancelled by user",
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

@mcp.tool()
async def available_sources(ctx: Context) -> str:
    """
    Get all available sources from the Qdrant sources collection.
    """
    try:
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        scroll_result = qdrant_client.scroll(
            collection_name='sources',
            with_payload=True,
            limit=200
        )
        sources = [point.payload for point in scroll_result[0]]
        return json.dumps({"success": True, "sources": sources}, indent=2)
    except asyncio.CancelledError:
        # Handle cancellation gracefully
        await ctx.warning("Available sources query cancelled")
        return json.dumps({"success": False, "error": "Operation cancelled by user"}, indent=2)
    except Exception as e:
        await ctx.error(f"Failed to get available sources: {str(e)}")
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@mcp.tool()
async def rag_query(ctx: Context, query: str, source: str = None, match_count: int = 5) -> str:
    """
    Perform a RAG query on the stored content in Qdrant.
    """
    try:
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        reranking_model = ctx.request_context.lifespan_context.reranking_model
        process_pool = ctx.request_context.lifespan_context.process_pool
        
        filter_metadata = {"source": source} if source else None
        
        results = await search_documents(
            client=qdrant_client,
            query=query,
            match_count=match_count,
            filter_metadata=filter_metadata
        )
        
        use_reranking = os.getenv("USE_RERANKING", "false") == "true"
        if use_reranking and reranking_model:
            results = await rerank_results(process_pool, reranking_model, query, results, content_key="content")

        return json.dumps({
            "success": True,
            "query": query,
            "results": results
        }, indent=2)
    except asyncio.CancelledError:
        # Handle cancellation gracefully
        await ctx.warning(f"RAG query cancelled for: {query}")
        return json.dumps({"success": False, "query": query, "error": "Operation cancelled by user"}, indent=2)
    except Exception as e:
        await ctx.error(f"RAG query failed for '{query}': {str(e)}")
        return json.dumps({"success": False, "query": query, "error": str(e)}, indent=2)

@mcp.tool()
async def search_code_examples(ctx: Context, query: str, source_id: str = None, match_count: int = 5) -> str:
    """
    Search for code examples in Qdrant.
    """
    if os.getenv("USE_AGENTIC_RAG", "false") != "true":
        return json.dumps({"success": False, "error": "Agentic RAG is not enabled."}, indent=2)

    try:
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        reranking_model = ctx.request_context.lifespan_context.reranking_model
        process_pool = ctx.request_context.lifespan_context.process_pool

        results = await search_code_examples_util(
            client=qdrant_client,
            query=query,
            match_count=match_count,
            source_id=source_id
        )

        use_reranking = os.getenv("USE_RERANKING", "false") == "true"
        if use_reranking and reranking_model:
            results = await rerank_results(process_pool, reranking_model, query, results, content_key="content")

        return json.dumps({"success": True, "query": query, "results": results}, indent=2)
    except asyncio.CancelledError:
        # Handle cancellation gracefully
        await ctx.warning(f"Code search cancelled for: {query}")
        return json.dumps({"success": False, "query": query, "error": "Operation cancelled by user"}, indent=2)
    except Exception as e:
        await ctx.error(f"Code search failed for '{query}': {str(e)}")
        return json.dumps({"success": False, "query": query, "error": str(e)}, indent=2)

