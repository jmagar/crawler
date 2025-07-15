"""
Web crawling and RAG tools for the MCP server.
"""
import os
import json
import asyncio
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
async def crawl_single_page(ctx: Context, url: str) -> str:
    """
    Crawl a single web page and store its content in Qdrant.
    """
    try:
        crawler = ctx.request_context.lifespan_context.crawler
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        
        run_config = get_enhanced_crawler_config()
        result = await crawler.arun(url=url, config=run_config)
        
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
            
            source_summary = await extract_source_summary(source_id, result.markdown[:5000])
            await update_source_info(qdrant_client, source_id, source_summary, total_word_count)
            
            await add_documents_to_qdrant(qdrant_client, urls, chunk_numbers, contents, metadatas, url_to_full_document)
            
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
async def smart_crawl_url(ctx: Context, url: str, max_depth: int = 3, max_concurrent: int = 10, chunk_size: int = 5000) -> str:
    """
    Intelligently crawl a URL and store content in Qdrant.
    """
    try:
        crawler = ctx.request_context.lifespan_context.crawler
        qdrant_client = ctx.request_context.lifespan_context.qdrant_client
        
        await ctx.report_progress(progress=0, total=100, message="Starting crawl...")
        
        crawl_results = []
        if is_txt(url):
            crawl_results = await crawl_markdown_file(crawler, url)
        elif is_sitemap(url):
            sitemap_urls = parse_sitemap(url)
            if sitemap_urls:
                crawl_results = await crawl_batch(crawler, sitemap_urls, max_concurrent=max_concurrent)
        else:
            crawl_results = await crawl_recursive_internal_links(crawler, [url], max_depth=max_depth, max_concurrent=max_concurrent)

        if not crawl_results:
            return json.dumps({"success": False, "url": url, "error": "No content found"}, indent=2)

        await ctx.report_progress(progress=25, total=100, message="Processing documents...")

        source_content_map = {}
        source_word_counts = {}
        all_urls, all_chunk_numbers, all_contents, all_metadatas = [], [], [], []
        
        for doc in crawl_results:
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

        url_to_full_document = {doc.url: doc.markdown for doc in crawl_results}

        await ctx.report_progress(progress=50, total=100, message="Updating source info...")

        for source_id, content in source_content_map.items():
            summary = await extract_source_summary(source_id, content)
            await update_source_info(qdrant_client, source_id, summary, source_word_counts.get(source_id, 0))

        await ctx.report_progress(progress=75, total=100, message="Adding documents to Qdrant...")
        await add_documents_to_qdrant(qdrant_client, all_urls, all_chunk_numbers, all_contents, all_metadatas, url_to_full_document)

        code_examples_stored = 0
        if os.getenv("USE_AGENTIC_RAG", "false") == "true":
            all_code_blocks_data = []
            for doc in crawl_results:
                code_blocks = extract_code_blocks(doc.markdown)
                for block in code_blocks:
                    block['source_url'] = doc.url
                    all_code_blocks_data.append(block)
            
            if all_code_blocks_data:
                code_urls, code_chunk_numbers, code_examples_list, code_summaries, code_metadatas = [], [], [], [], []
                
                summary_tasks = [generate_code_example_summary(block['code'], block['context_before'], block['context_after']) for block in all_code_blocks_data]
                summaries = await asyncio.gather(*summary_tasks)

                for i, block in enumerate(all_code_blocks_data):
                    source_url = block['source_url']
                    source_id = urlparse(source_url).netloc or urlparse(source_url).path
                    code_urls.append(source_url)
                    code_chunk_numbers.append(i)
                    code_examples_list.append(block['code'])
                    code_summaries.append(summaries[i])
                    code_metadatas.append({"url": source_url, "source": source_id, "language": block['language']})
                
                await add_code_examples_to_qdrant(qdrant_client, code_urls, code_chunk_numbers, code_examples_list, code_summaries, code_metadatas)
                code_examples_stored = len(all_code_blocks_data)

        await ctx.report_progress(progress=100, total=100, message="Crawl complete.")

        return json.dumps({
            "success": True,
            "url": url,
            "pages_crawled": len(crawl_results),
            "chunks_stored": len(all_contents),
            "code_examples_stored": code_examples_stored
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "url": url, "error": str(e)}, indent=2)

@mcp.tool()
async def get_available_sources(ctx: Context) -> str:
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
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@mcp.tool()
async def perform_rag_query(ctx: Context, query: str, source: str = None, match_count: int = 5) -> str:
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
    except Exception as e:
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
    except Exception as e:
        return json.dumps({"success": False, "query": query, "error": str(e)}, indent=2)

@mcp.tool()
async def test_chunking_strategies(ctx: Context, url: str, strategies: List[str] = None) -> str:
    """
    Test different chunking strategies on a single page to compare results.
    """
    if strategies is None:
        strategies = ["smart", "regex", "sentence", "fixed_word", "sliding"]
    
    try:
        crawler = ctx.request_context.lifespan_context.crawler
        
        # Crawl the page once
        run_config = get_enhanced_crawler_config()
        result = await crawler.arun(url=url, config=run_config)
        
        if not result.success or not result.markdown:
            return json.dumps({"success": False, "error": "Failed to crawl page"}, indent=2)
        
        results = {}
        for strategy in strategies:
            try:
                chunks = smart_chunk_markdown(result.markdown, chunk_size=5000, strategy=strategy)
                results[strategy] = {
                    "chunk_count": len(chunks),
                    "avg_chunk_size": sum(len(chunk) for chunk in chunks) // len(chunks) if chunks else 0,
                    "total_chars": sum(len(chunk) for chunk in chunks),
                    "sample_chunk": chunks[0][:200] + "..." if chunks else ""
                }
            except Exception as e:
                results[strategy] = {"error": str(e)}
        
        return json.dumps({
            "success": True,
            "url": url,
            "original_markdown_length": len(result.markdown),
            "strategy_results": results
        }, indent=2)
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)
