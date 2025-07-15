"""
Web crawling helper functions.
"""
from typing import List, Optional
from urllib.parse import urlparse, urldefrag
from xml.etree import ElementTree
import requests
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, MemoryAdaptiveDispatcher, CrawlResult
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import BM25ContentFilter, PruningContentFilter
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

def get_enhanced_crawler_config(use_content_filtering: bool = True) -> CrawlerRunConfig:
    """Get an enhanced crawler configuration with better markdown generation."""
    
    # Configure markdown generator with better options
    markdown_options = {
        'ignore_links': False,  # Keep links for reference
        'ignore_images': False,  # Keep image references
        'body_width': 0,  # No line wrapping
        'unicode_snob': True,  # Better Unicode handling
        'escape_all': False,  # Don't escape markdown
        'reference_links': True,  # Use reference-style links
        'mark_code': True,  # Preserve code formatting
    }
    
    markdown_generator = DefaultMarkdownGenerator(options=markdown_options)
    
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        stream=False,
        markdown_generator=markdown_generator,
    )
    
    # Add content filtering if enabled
    if use_content_filtering and os.getenv("USE_CONTENT_FILTERING", "true").lower() == "true":
        try:
            # Use BM25 filter for better content extraction
            content_filter = BM25ContentFilter(
                bm25_threshold=1.0,  # Threshold for relevance
                top_k=10  # Keep top 10 relevant sections
            )
            config.content_filter = content_filter
        except Exception as e:
            print(f"Warning: Could not initialize content filter: {e}")
    
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

async def crawl_single_with_filtering(crawler: AsyncWebCrawler, url: str, query: Optional[str] = None) -> CrawlResult:
    """Crawl a single page with optional query-based content filtering."""
    
    config = get_enhanced_crawler_config()
    
    # If a query is provided, use it for content filtering
    if query and os.getenv("USE_QUERY_FILTERING", "false").lower() == "true":
        try:
            # Use BM25 filter with query for better relevance
            content_filter = BM25ContentFilter(
                bm25_threshold=0.5,
                top_k=15,
                query=query  # Focus on query-relevant content
            )
            config.content_filter = content_filter
        except Exception as e:
            print(f"Warning: Could not initialize query-based filter: {e}")
    
    result = await crawler.arun(url=url, config=config)
    return result
