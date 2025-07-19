"""
Content extractors for different source types.
"""
import asyncio
import logging
import os
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, AsyncIterator, Optional
from urllib.parse import urlparse, urljoin
import time
import aiofiles
import git

# Import existing components
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from src.core.crawling import get_enhanced_crawler_config

# Import our data models
from .data_models import (
    ContentExtractor, ContentSource, ProcessedContent, ContentChunk, 
    StructuralNode, ContentType, ContentFormat, IngestionConfig,
    classify_content_format, generate_node_id, chunk_content
)

logger = logging.getLogger(__name__)


class GitHubRepositoryExtractor(ContentExtractor):
    """Extracts content from GitHub repositories."""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
    
    def supports_source_type(self, source_type: ContentType) -> bool:
        return source_type == ContentType.GITHUB_REPOSITORY
    
    async def extract(self, source: ContentSource) -> ProcessedContent:
        """Extract GitHub repository into both structural and chunk data."""
        logger.info(f"Extracting GitHub repository: {source.source_id}")
        start_time = time.time()
        
        processed = ProcessedContent(source=source)
        
        # Parse repository info
        repo_info = self._parse_repo_url(source.source_id)
        
        # Clone repository temporarily
        temp_dir = None
        try:
            temp_dir = await self._clone_repository(source.source_id)
            
            # Create repository node for Neo4j
            repo_node = StructuralNode(
                node_type="Repository",
                node_id=generate_node_id("Repository", repo_info["full_name"]),
                properties={
                    "name": repo_info["name"],
                    "owner": repo_info["owner"],
                    "full_name": repo_info["full_name"],
                    "url": source.source_id,
                    "source_type": "github",
                    "analyzed_at": time.time()
                }
            )
            processed.structural_nodes.append(repo_node)
            
            # Process repository structure
            await self._process_repository_structure(temp_dir, repo_info, processed)
            
            # Update processing stats
            processing_time = time.time() - start_time
            processed.processing_stats.update({
                "extraction_time": processing_time,
                "extraction_end_time": time.time(),
                "files_processed": len([n for n in processed.structural_nodes if n.node_type == "File"]),
                "directories_processed": len([n for n in processed.structural_nodes if n.node_type == "Directory"])
            })
            
            logger.info(f"GitHub extraction completed in {processing_time:.2f}s: "
                       f"{len(processed.content_chunks)} chunks, {len(processed.structural_nodes)} nodes")
            
            return processed
            
        except Exception as e:
            logger.error(f"GitHub repository extraction failed: {str(e)}")
            raise
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    def _parse_repo_url(self, repo_url: str) -> Dict[str, str]:
        """Parse GitHub repository URL."""
        parsed = urlparse(repo_url)
        path_parts = parsed.path.strip('/').split('/')
        
        if len(path_parts) < 2:
            raise ValueError(f"Invalid repository URL: {repo_url}")
        
        owner = path_parts[0]
        name = path_parts[1].replace('.git', '')
        
        return {
            "owner": owner,
            "name": name,
            "full_name": f"{owner}/{name}",
            "url": repo_url
        }
    
    async def _clone_repository(self, repo_url: str) -> str:
        """Clone repository to temporary directory."""
        temp_dir = tempfile.mkdtemp(prefix="unified_ingestion_")
        
        try:
            # Use asyncio to run git clone in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, 
                lambda: git.Repo.clone_from(repo_url, temp_dir, depth=1)
            )
            return temp_dir
        except Exception as e:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise RuntimeError(f"Failed to clone repository: {str(e)}")
    
    async def _process_repository_structure(self, repo_path: str, repo_info: Dict[str, str], processed: ProcessedContent):
        """Process repository structure into both nodes and chunks."""
        directories_created = set()
        
        # Process files in batches
        async for batch_data in self._stream_repository_files(repo_path):
            # Create directory nodes
            for dir_path in batch_data["directories"]:
                if dir_path not in directories_created:
                    dir_node = StructuralNode(
                        node_type="Directory",
                        node_id=generate_node_id("Directory", f"{repo_info['full_name']}:{dir_path}"),
                        properties={
                            "path": dir_path,
                            "repository": repo_info["name"],
                            "repository_full_name": repo_info["full_name"]
                        }
                    )
                    
                    # Add relationship to repository
                    dir_node.add_relationship("CONTAINED_IN", processed.structural_nodes[0].node_id)
                    
                    processed.structural_nodes.append(dir_node)
                    directories_created.add(dir_path)
            
            # Process files
            for file_info in batch_data["files"]:
                await self._process_file(file_info, repo_info, processed)
            
            # Allow other tasks to run
            await asyncio.sleep(0)
    
    async def _stream_repository_files(self, repo_path: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream repository files in batches."""
        current_batch = {
            "files": [],
            "directories": set(),
        }
        
        for root, dirs, files in os.walk(repo_path):
            # Skip ignored directories
            dirs[:] = [d for d in dirs if not any(pattern in d for pattern in self.config.ignore_patterns)]
            
            rel_root = os.path.relpath(root, repo_path)
            if rel_root != '.':
                current_batch["directories"].add(rel_root)
            
            for file in files:
                if file.startswith('.'):
                    continue
                
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                file_ext = Path(file).suffix.lower()
                
                # Skip files that are too large or unsupported
                try:
                    file_size = os.path.getsize(file_path)
                    if file_size > self.config.max_file_size:
                        continue
                except OSError:
                    continue
                
                file_info = {
                    "path": rel_path,
                    "name": file,
                    "extension": file_ext,
                    "size": file_size,
                    "full_path": file_path
                }
                
                current_batch["files"].append(file_info)
                
                # Yield batch when it reaches batch_size
                if len(current_batch["files"]) >= self.config.batch_size:
                    yield {
                        "files": current_batch["files"],
                        "directories": list(current_batch["directories"])
                    }
                    current_batch = {"files": [], "directories": set()}
        
        # Yield remaining files
        if current_batch["files"]:
            yield {
                "files": current_batch["files"],
                "directories": list(current_batch["directories"])
            }
    
    async def _process_file(self, file_info: Dict[str, Any], repo_info: Dict[str, str], processed: ProcessedContent):
        """Process a single file into both structural node and content chunks."""
        # Create file node for Neo4j
        file_node = StructuralNode(
            node_type="File",
            node_id=generate_node_id("File", f"{repo_info['full_name']}:{file_info['path']}"),
            properties={
                "path": file_info["path"],
                "name": file_info["name"],
                "extension": file_info["extension"],
                "size": file_info["size"],
                "repository": repo_info["name"],
                "repository_full_name": repo_info["full_name"],
                "content_format": classify_content_format(file_info["path"]).value
            }
        )
        
        # Add relationship to repository
        file_node.add_relationship("CONTAINED_IN", processed.structural_nodes[0].node_id)
        
        # Add relationship to parent directory if exists
        parent_dir = str(Path(file_info["path"]).parent)
        if parent_dir != '.':
            parent_dir_id = generate_node_id("Directory", f"{repo_info['full_name']}:{parent_dir}")
            file_node.add_relationship("CONTAINED_IN", parent_dir_id)
        
        processed.structural_nodes.append(file_node)
        
        # Read file content and create chunks for Qdrant
        if file_info["extension"] in self.config.supported_extensions:
            try:
                content = await self._read_file_async(file_info["full_path"])
                if content:
                    content_format = classify_content_format(file_info["path"], content)
                    
                    # Create content chunks
                    chunks = chunk_content(content, chunk_size=1000, overlap=100)
                    for i, chunk_text in enumerate(chunks):
                        chunk = ContentChunk(
                            chunk_id=f"{file_node.node_id}_chunk_{i}",
                            content=chunk_text,
                            content_format=content_format,
                            source_path=file_info["path"],
                            metadata={
                                "repository": repo_info["full_name"],
                                "file_name": file_info["name"],
                                "file_extension": file_info["extension"],
                                "chunk_index": i,
                                "total_chunks": len(chunks),
                                "source_type": "github_repository"
                            }
                        )
                        processed.content_chunks.append(chunk)
                        
            except Exception as e:
                logger.warning(f"Could not read file {file_info['path']}: {str(e)}")
    
    async def _read_file_async(self, file_path: str) -> Optional[str]:
        """Read file content asynchronously."""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = await f.read(self.config.max_file_size)
                return content
        except Exception as e:
            logger.debug(f"Failed to read file {file_path}: {str(e)}")
            return None


class WebPageExtractor(ContentExtractor):
    """Extracts content from web pages."""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
    
    def supports_source_type(self, source_type: ContentType) -> bool:
        return source_type == ContentType.WEB_PAGE
    
    async def extract(self, source: ContentSource) -> ProcessedContent:
        """Extract web page into both structural and chunk data."""
        logger.info(f"Extracting web page: {source.source_id}")
        start_time = time.time()
        
        processed = ProcessedContent(source=source)
        
        # Parse URL info
        parsed_url = urlparse(source.source_id)
        domain = parsed_url.netloc
        path = parsed_url.path or "/"
        
        # Create page node for Neo4j
        page_node = StructuralNode(
            node_type="WebPage",
            node_id=generate_node_id("WebPage", source.source_id),
            properties={
                "url": source.source_id,
                "domain": domain,
                "path": path,
                "source_type": "web_page",
                "analyzed_at": time.time()
            }
        )
        processed.structural_nodes.append(page_node)
        
        # Crawl the page
        try:
            async with AsyncWebCrawler() as crawler:
                config = get_enhanced_crawler_config(
                    use_content_filtering=True,
                    filter_type="bm25"
                )
                
                result = await crawler.arun(url=source.source_id, config=config)
                
                if result.success and result.markdown:
                    # Update page node with extracted metadata
                    page_node.properties.update({
                        "title": getattr(result, 'title', ''),
                        "content_length": len(result.markdown),
                        "crawled_at": time.time()
                    })
                    
                    # Create content chunks for Qdrant
                    chunks = chunk_content(result.markdown, chunk_size=1000, overlap=100)
                    for i, chunk_text in enumerate(chunks):
                        chunk = ContentChunk(
                            chunk_id=f"{page_node.node_id}_chunk_{i}",
                            content=chunk_text,
                            content_format=ContentFormat.MARKDOWN,
                            source_path=source.source_id,
                            metadata={
                                "url": source.source_id,
                                "domain": domain,
                                "title": getattr(result, 'title', ''),
                                "chunk_index": i,
                                "total_chunks": len(chunks),
                                "source_type": "web_page"
                            }
                        )
                        processed.content_chunks.append(chunk)
                
                else:
                    raise RuntimeError(f"Failed to crawl web page: {source.source_id}")
        
        except Exception as e:
            logger.error(f"Web page extraction failed: {str(e)}")
            raise
        
        # Update processing stats
        processing_time = time.time() - start_time
        processed.processing_stats.update({
            "extraction_time": processing_time,
            "extraction_end_time": time.time()
        })
        
        logger.info(f"Web page extraction completed in {processing_time:.2f}s: "
                   f"{len(processed.content_chunks)} chunks, {len(processed.structural_nodes)} nodes")
        
        return processed


class LocalFolderExtractor(ContentExtractor):
    """Extracts content from local folders."""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
    
    def supports_source_type(self, source_type: ContentType) -> bool:
        return source_type in (ContentType.LOCAL_FOLDER, ContentType.LOCAL_FILE)
    
    async def extract(self, source: ContentSource) -> ProcessedContent:
        """Extract local folder/file into both structural and chunk data."""
        logger.info(f"Extracting local content: {source.source_id}")
        start_time = time.time()
        
        processed = ProcessedContent(source=source)
        
        source_path = Path(source.source_id)
        
        if source.source_type == ContentType.LOCAL_FILE:
            # Handle single file
            await self._process_single_file(source_path, processed)
        else:
            # Handle folder
            await self._process_folder(source_path, processed)
        
        # Update processing stats
        processing_time = time.time() - start_time
        processed.processing_stats.update({
            "extraction_time": processing_time,
            "extraction_end_time": time.time()
        })
        
        logger.info(f"Local extraction completed in {processing_time:.2f}s: "
                   f"{len(processed.content_chunks)} chunks, {len(processed.structural_nodes)} nodes")
        
        return processed
    
    async def _process_single_file(self, file_path: Path, processed: ProcessedContent):
        """Process a single local file."""
        # Create file node
        file_node = StructuralNode(
            node_type="LocalFile",
            node_id=generate_node_id("LocalFile", str(file_path)),
            properties={
                "path": str(file_path),
                "name": file_path.name,
                "extension": file_path.suffix.lower(),
                "size": file_path.stat().st_size if file_path.exists() else 0,
                "source_type": "local_file",
                "analyzed_at": time.time()
            }
        )
        processed.structural_nodes.append(file_node)
        
        # Read content and create chunks
        if file_path.suffix.lower() in self.config.supported_extensions:
            content = await self._read_local_file(file_path)
            if content:
                content_format = classify_content_format(str(file_path), content)
                chunks = chunk_content(content, chunk_size=1000, overlap=100)
                
                for i, chunk_text in enumerate(chunks):
                    chunk = ContentChunk(
                        chunk_id=f"{file_node.node_id}_chunk_{i}",
                        content=chunk_text,
                        content_format=content_format,
                        source_path=str(file_path),
                        metadata={
                            "file_name": file_path.name,
                            "file_extension": file_path.suffix.lower(),
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "source_type": "local_file"
                        }
                    )
                    processed.content_chunks.append(chunk)
    
    async def _process_folder(self, folder_path: Path, processed: ProcessedContent):
        """Process a local folder."""
        # Create folder node
        folder_node = StructuralNode(
            node_type="LocalFolder",
            node_id=generate_node_id("LocalFolder", str(folder_path)),
            properties={
                "path": str(folder_path),
                "name": folder_path.name,
                "source_type": "local_folder",
                "analyzed_at": time.time()
            }
        )
        processed.structural_nodes.append(folder_node)
        
        # Process files and subdirectories
        for item in folder_path.rglob("*"):
            # Skip ignored patterns
            if any(pattern in str(item) for pattern in self.config.ignore_patterns):
                continue
            
            if item.is_file():
                # Check file size
                try:
                    if item.stat().st_size > self.config.max_file_size:
                        continue
                except OSError:
                    continue
                
                # Create file node
                file_node = StructuralNode(
                    node_type="LocalFile",
                    node_id=generate_node_id("LocalFile", str(item)),
                    properties={
                        "path": str(item),
                        "name": item.name,
                        "extension": item.suffix.lower(),
                        "size": item.stat().st_size,
                        "relative_path": str(item.relative_to(folder_path)),
                        "source_type": "local_file"
                    }
                )
                
                # Add relationship to folder
                file_node.add_relationship("CONTAINED_IN", folder_node.node_id)
                processed.structural_nodes.append(file_node)
                
                # Process content if supported
                if item.suffix.lower() in self.config.supported_extensions:
                    content = await self._read_local_file(item)
                    if content:
                        content_format = classify_content_format(str(item), content)
                        chunks = chunk_content(content, chunk_size=1000, overlap=100)
                        
                        for i, chunk_text in enumerate(chunks):
                            chunk = ContentChunk(
                                chunk_id=f"{file_node.node_id}_chunk_{i}",
                                content=chunk_text,
                                content_format=content_format,
                                source_path=str(item),
                                metadata={
                                    "folder_path": str(folder_path),
                                    "relative_path": str(item.relative_to(folder_path)),
                                    "file_name": item.name,
                                    "file_extension": item.suffix.lower(),
                                    "chunk_index": i,
                                    "total_chunks": len(chunks),
                                    "source_type": "local_folder"
                                }
                            )
                            processed.content_chunks.append(chunk)
    
    async def _read_local_file(self, file_path: Path) -> Optional[str]:
        """Read local file content."""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = await f.read(self.config.max_file_size)
                return content
        except Exception as e:
            logger.debug(f"Failed to read local file {file_path}: {str(e)}")
            return None


# Factory function to create appropriate extractor
def create_extractor(source_type: ContentType, config: IngestionConfig) -> ContentExtractor:
    """Create the appropriate extractor for the given source type."""
    if source_type == ContentType.GITHUB_REPOSITORY:
        return GitHubRepositoryExtractor(config)
    elif source_type == ContentType.WEB_PAGE:
        return WebPageExtractor(config)
    elif source_type in (ContentType.LOCAL_FOLDER, ContentType.LOCAL_FILE):
        return LocalFolderExtractor(config)
    else:
        raise ValueError(f"Unsupported source type: {source_type}")