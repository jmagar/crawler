"""
Web crawling helper functions.
Enhanced with cancellation handling and progress reporting.
"""
import asyncio
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, urldefrag
from xml.etree import ElementTree
import requests
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher, CrawlResult
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import BM25ContentFilter, PruningContentFilter, LLMContentFilter
from crawl4ai import LLMConfig
import os

def is_sitemap(url: str) -> bool:
    return url.endswith('sitemap.xml') or 'sitemap' in urlparse(url).path

def is_txt(url: str) -> bool:
    return url.endswith('.txt')

def parse_sitemap(sitemap_url: str, max_urls: int = 100) -> List[str]:
    """Parse sitemap with URL limit to prevent overwhelming crawls."""
    try:
        resp = requests.get(sitemap_url, timeout=30)
        urls = []
        if resp.status_code == 200:
            try:
                tree = ElementTree.fromstring(resp.content)
                urls = [loc.text for loc in tree.findall('.//{*}loc')][:max_urls]
            except Exception as e:
                print(f"Error parsing sitemap XML: {e}")
        return urls
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return []

def get_enhanced_crawler_config(
    use_content_filtering: bool = True,
    filter_type: str = "bm25",
    user_query: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_api_token: Optional[str] = None
) -> CrawlerRunConfig:
    """Get an enhanced crawler configuration with clean markdown generation.
    
    Args:
        use_content_filtering: Enable content filtering
        filter_type: Type of filter ('bm25', 'pruning', 'llm')
        user_query: Query for BM25 filtering
        llm_provider: LLM provider for LLMContentFilter (e.g., 'openai/gpt-4o')
        llm_api_token: API token for LLM provider
    """
    
    # Configure markdown generator with enhanced options for clean output
    markdown_options = {
        'ignore_links': False,  # Keep links for reference
        'ignore_images': False,  # Keep image references
        'body_width': 0,  # No line wrapping
        'unicode_snob': True,  # Better Unicode handling
        'escape_all': False,  # Don't escape markdown
        'reference_links': True,  # Use reference-style links for citations
        'mark_code': True,  # Preserve code formatting
        'protect_links': True,  # Protect existing markdown links
        'wrap_links': True,  # Wrap long links
    }
    
    content_filter = None
    
    # Configure content filtering based on type
    if use_content_filtering and os.getenv("USE_CONTENT_FILTERING", "false").lower() == "true":
        try:
            if filter_type == "bm25":
                content_filter = BM25ContentFilter(
                    user_query=user_query or "",
                    bm25_threshold=1.2,  # Adjusted for better filtering
                    language="english",
                    use_stemming=True
                )
            elif filter_type == "pruning":
                content_filter = PruningContentFilter(
                    threshold=0.5,
                    threshold_type="fixed",  # or "dynamic" for adaptive filtering
                    min_word_threshold=50
                )
            elif filter_type == "llm" and llm_provider:
                llm_config = LLMConfig(
                    provider=llm_provider,
                    api_token=llm_api_token or os.getenv("OPENAI_API_KEY")
                )
                content_filter = LLMContentFilter(
                    llm_config=llm_config,
                    instruction="""
                    Focus on extracting the core content while preserving structure.
                    Include:
                    - Main content and explanations
                    - Important code examples
                    - Essential technical details
                    - Key concepts and definitions
                    Exclude:
                    - Navigation elements
                    - Sidebars and advertisements
                    - Footer content
                    - Repetitive boilerplate
                    Format the output as clean markdown with proper headers and code blocks.
                    """,
                    chunk_token_threshold=4096,  # Process in chunks for better performance
                    verbose=False
                )
        except Exception as e:
            print(f"Warning: Could not initialize {filter_type} content filter: {e}")
    
    # Create markdown generator with optional content filtering
    markdown_generator = DefaultMarkdownGenerator(
        content_filter=content_filter,
        options=markdown_options
    )
    
    # Configure cache mode based on environment variable
    cache_mode_env = os.getenv("CRAWL4AI_CACHE_MODE", "ENABLED").upper()
    if cache_mode_env == "DISABLED":
        cache_mode = CacheMode.DISABLED
    elif cache_mode_env == "BYPASS":
        cache_mode = CacheMode.BYPASS
    else:
        cache_mode = CacheMode.ENABLED
    
    config = CrawlerRunConfig(
        cache_mode=cache_mode,
        stream=False,
        markdown_generator=markdown_generator,
    )
    
    return config

async def crawl_markdown_file(crawler: AsyncWebCrawler, url: str) -> List[CrawlResult]:
    config = get_enhanced_crawler_config()
    result = await crawler.arun(url=url, config=config)
    return [result] if result.success and result.markdown else []

async def crawl_batch(crawler: AsyncWebCrawler, urls: List[str], max_concurrent: int = 10) -> List[CrawlResult]:
    dispatcher = MemoryAdaptiveDispatcher(max_session_permit=max_concurrent)
    config = get_enhanced_crawler_config()
    results = await crawler.arun_many(urls=urls, config=config, dispatcher=dispatcher)
    return [r for r in results if r.success and r.markdown]

async def crawl_recursive_internal_links(crawler: AsyncWebCrawler, start_urls: List[str], max_depth: int = 3, max_concurrent: int = 10) -> List[CrawlResult]:
    visited = set()
    normalize_url = lambda url: urldefrag(url)[0]
    current_urls = {normalize_url(u) for u in start_urls}
    results_all = []
    for _ in range(max_depth):
        urls_to_crawl = [url for url in current_urls if url not in visited]
        if not urls_to_crawl:
            break
        
        results = await crawl_batch(crawler, urls_to_crawl, max_concurrent)
        next_level_urls = set()
        
        for result in results:
            norm_url = normalize_url(result.url)
            if norm_url not in visited:
                visited.add(norm_url)
                results_all.append(result)
                for link in result.links.get("internal", []):
                    next_url = normalize_url(link["href"])
                    if next_url not in visited:
                        next_level_urls.add(next_url)
        
        current_urls = next_level_urls
    return results_all

async def crawl_single_with_filtering(
    crawler: AsyncWebCrawler, 
    url: str, 
    query: Optional[str] = None,
    filter_type: str = "bm25",
    llm_provider: Optional[str] = None
) -> CrawlResult:
    """Crawl a single page with advanced content filtering options.
    
    Args:
        crawler: AsyncWebCrawler instance
        url: URL to crawl
        query: Query for BM25 filtering
        filter_type: Type of filter ('bm25', 'pruning', 'llm')
        llm_provider: LLM provider for LLMContentFilter
    """
    
    # Use query-based filtering if query is provided
    use_filtering = query is not None or filter_type in ["pruning", "llm"]
    
    config = get_enhanced_crawler_config(
        use_content_filtering=use_filtering,
        filter_type=filter_type,
        user_query=query,
        llm_provider=llm_provider
    )
    
    result = await crawler.arun(url=url, config=config)
    return result

def extract_clean_markdown(result: CrawlResult) -> Dict[str, str]:
    """Extract different types of markdown from CrawlResult.
    
    Returns:
        Dictionary with raw_markdown, fit_markdown, and markdown_with_citations
    """
    if not result.success or not result.markdown:
        return {}
    
    markdown_data = {}
    
    # Handle both string and MarkdownGenerationResult types
    if isinstance(result.markdown, str):
        markdown_data["raw_markdown"] = result.markdown
    else:
        # MarkdownGenerationResult object
        markdown_data["raw_markdown"] = getattr(result.markdown, "raw_markdown", "")
        markdown_data["fit_markdown"] = getattr(result.markdown, "fit_markdown", "")
        markdown_data["markdown_with_citations"] = getattr(result.markdown, "markdown_with_citations", "")
        markdown_data["references"] = getattr(result.markdown, "references_markdown", "")
    
    return {k: v for k, v in markdown_data.items() if v}

async def crawl_with_clean_markdown(
    crawler: AsyncWebCrawler,
    url: str,
    filter_type: str = "pruning",
    user_query: Optional[str] = None,
    llm_provider: Optional[str] = None
) -> Dict[str, Any]:
    """Crawl a URL and return clean markdown with metadata.
    
    Args:
        crawler: AsyncWebCrawler instance
        url: URL to crawl
        filter_type: Content filter type ('bm25', 'pruning', 'llm')
        user_query: Query for BM25 filtering
        llm_provider: LLM provider for AI filtering
        
    Returns:
        Dictionary with markdown content, metadata, and extraction info
    """
    
    result = await crawl_single_with_filtering(
        crawler, url, user_query, filter_type, llm_provider
    )
    
    if not result.success:
        return {
            "success": False,
            "error": result.error_message,
            "url": url
        }
    
    # Extract clean markdown variants
    markdown_content = extract_clean_markdown(result)
    
    # Gather metadata
    response_data = {
        "success": True,
        "url": result.url,
        "title": getattr(result.metadata, "title", "") if result.metadata else "",
        "markdown": markdown_content,
        "filter_type": filter_type,
        "has_filtered_content": bool(markdown_content.get("fit_markdown")),
        "content_stats": {
            "raw_length": len(markdown_content.get("raw_markdown", "")),
            "filtered_length": len(markdown_content.get("fit_markdown", "")),
            "has_citations": bool(markdown_content.get("references")),
            "media_count": len(result.media.get("images", [])) if result.media else 0,
            "internal_links": len(result.links.get("internal", [])) if result.links else 0,
            "external_links": len(result.links.get("external", [])) if result.links else 0,
        }
    }
    
    return response_data
