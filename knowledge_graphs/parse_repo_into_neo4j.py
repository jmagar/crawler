"""
DirectNeo4jExtractor for parsing repositories into Neo4j knowledge graph.
"""
import asyncio
import logging
from typing import Any, AsyncIterator
from urllib.parse import urlparse
import aiofiles
import git
import tempfile
import os
import shutil
from pathlib import Path
import time
from collections import defaultdict

from neo4j import AsyncGraphDatabase
try:
    from src.core.validation import format_neo4j_error
except ImportError:
    def format_neo4j_error(error: Exception) -> str:
        """Fallback error formatting function."""
        return f"Neo4j error: {str(error)}"
from .performance_monitor import get_performance_monitor, QueryPerformanceMonitor

logger = logging.getLogger(__name__)

# Default configuration constants
DEFAULT_MAX_FILE_SIZE = 50000  # Maximum file size to read content (bytes)
DEFAULT_BATCH_SIZE = 100  # Default batch size for processing files

class DirectNeo4jExtractor:
    """Extract repository information directly into Neo4j graph database with performance optimizations."""
    
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str, 
                 batch_size: int = DEFAULT_BATCH_SIZE, max_file_size: int = DEFAULT_MAX_FILE_SIZE):
        """Initialize the Neo4j extractor.
        
        Args:
            neo4j_uri: Neo4j database URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            batch_size: Number of files to process in each batch
            max_file_size: Maximum file size to read content (bytes)
        """
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.driver = None
        self.batch_size = batch_size
        self.max_file_size = max_file_size
        self.performance_metrics = defaultdict(float)
        self.perf_monitor = get_performance_monitor()
        self.query_monitor = QueryPerformanceMonitor(self.perf_monitor)
        
    async def initialize(self):
        """Initialize the Neo4j connection."""
        try:
            self.driver = AsyncGraphDatabase.driver(
                self.neo4j_uri, 
                auth=(self.neo4j_user, self.neo4j_password)
            )
            # Test the connection
            async with self.driver.session() as session:
                await session.run("RETURN 1")
            logger.info("Neo4j connection initialized successfully")
        except Exception as e:
            error_msg = format_neo4j_error(e)
            logger.error(f"Failed to initialize Neo4j: {error_msg}")
            raise RuntimeError(error_msg)
    
    async def close(self):
        """Close the Neo4j connection."""
        if self.driver:
            await self.driver.close()
            logger.info("Neo4j connection closed")
    
    async def analyze_repository(self, repo_url: str) -> dict[str, Any]:
        """Analyze a GitHub repository and extract it into Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")
        
        async with self.perf_monitor.measure_operation(
            "repository_analysis", 
            "repository", 
            {"repo_url": repo_url}
        ):
            logger.info(f"Starting repository analysis: {repo_url}")
            
            # Parse repository info
            repo_info = self._parse_repo_url(repo_url)
            
            # Clone repository temporarily
            temp_dir = None
            try:
                temp_dir = await self._clone_repository(repo_url)
                
                # Extract repository structure
                repo_data = await self._extract_repository_structure(temp_dir, repo_info)
                
                # Store in Neo4j
                await self._store_repository_graph(repo_data)
                
                # Record performance metrics
                self.perf_monitor.record_metric(
                    "files_processed",
                    repo_data.get("file_count", 0),
                    "repository",
                    {"repository": repo_info["name"]}
                )
                
                return {
                    "success": True,
                    "repository": repo_info["name"],
                    "files_processed": repo_data.get("file_count", 0),
                    "nodes_created": repo_data.get("nodes_created", 0),
                    "performance_metrics": self.get_performance_metrics()
                }
            
            except Exception as e:
                logger.error(f"Repository analysis failed: {str(e)}")
                raise
            finally:
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
    
    def _parse_repo_url(self, repo_url: str) -> dict[str, str]:
        """Parse GitHub repository URL to extract owner and name."""
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
        """Clone repository to temporary directory with URL validation."""
        # Validate repository URL for security
        self._validate_repository_url(repo_url)
        
        temp_dir = tempfile.mkdtemp(prefix="crawler_repo_")
        
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
    
    def _validate_repository_url(self, repo_url: str) -> None:
        """Validate repository URL to ensure it's from trusted sources and uses secure protocols."""
        parsed = urlparse(repo_url)
        
        # Ensure HTTPS protocol
        if parsed.scheme not in ('https',):
            raise ValueError(f"Only HTTPS repositories are allowed. Got: {parsed.scheme}")
        
        # Whitelist trusted hosts
        trusted_hosts = {
            'github.com',
            'gitlab.com', 
            'bitbucket.org',
            'gitlab.org'
        }
        
        if parsed.hostname not in trusted_hosts:
            raise ValueError(f"Repository host not in trusted list: {parsed.hostname}")
        
        # Basic path validation
        if not parsed.path or parsed.path == '/':
            raise ValueError("Invalid repository path")
        
        # Prevent path traversal attempts
        if '..' in parsed.path or parsed.path.startswith('/..'):
            raise ValueError("Invalid repository path: potential path traversal detected")
    
    async def _extract_repository_structure(self, repo_path: str, repo_info: dict[str, str]) -> dict[str, Any]:
        """Extract repository file structure and content with streaming and batching."""
        start_time = time.time()
        
        repo_data = {
            "repository": repo_info,
            "files": [],
            "directories": [],
            "file_count": 0,
            "nodes_created": 0
        }
        
        # Process repository structure in batches
        async for batch_data in self._stream_repository_files(repo_path):
            repo_data["files"].extend(batch_data["files"])
            repo_data["directories"].extend(batch_data["directories"])
            repo_data["file_count"] += batch_data["file_count"]
            
            # Allow other tasks to run
            await asyncio.sleep(0)
        
        self.performance_metrics["extraction_time"] = time.time() - start_time
        logger.info(f"Repository extraction completed in {self.performance_metrics['extraction_time']:.2f}s")
        
        return repo_data
    
    async def _stream_repository_files(self, repo_path: str) -> AsyncIterator[dict[str, Any]]:
        """Stream repository files in batches for memory efficiency."""
        # Supported file extensions for content extraction
        code_extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.hpp', 
                          '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt'}
        doc_extensions = {'.md', '.txt', '.rst', '.adoc'}
        config_extensions = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'}
        
        current_batch = {
            "files": [],
            "directories": set(),
            "file_count": 0
        }
        
        for root, dirs, files in os.walk(repo_path):
            # Skip common ignore directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      {'node_modules', '__pycache__', 'target', 'build', 'dist'}]
            
            rel_root = os.path.relpath(root, repo_path)
            if rel_root != '.':
                current_batch["directories"].add(rel_root)
            
            for file in files:
                if file.startswith('.'):
                    continue
                    
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                file_ext = Path(file).suffix.lower()
                file_size = os.path.getsize(file_path)
                
                file_info = {
                    "path": rel_path,
                    "name": file,
                    "extension": file_ext,
                    "size": file_size
                }
                
                # Extract content for supported file types asynchronously
                if (file_ext in code_extensions or file_ext in doc_extensions or 
                    file_ext in config_extensions) and file_size <= self.max_file_size:
                    try:
                        content = await self._read_file_async(file_path)
                        if content:
                            file_info["content"] = content
                            file_info["type"] = self._classify_file_type(file_ext)
                    except Exception as e:
                        logger.warning(f"Could not read file {rel_path}: {str(e)}")
                
                current_batch["files"].append(file_info)
                current_batch["file_count"] += 1
                
                # Yield batch when it reaches batch_size
                if len(current_batch["files"]) >= self.batch_size:
                    yield {
                        "files": current_batch["files"],
                        "directories": list(current_batch["directories"]),
                        "file_count": current_batch["file_count"]
                    }
                    current_batch = {"files": [], "directories": set(), "file_count": 0}
        
        # Yield remaining files
        if current_batch["files"]:
            yield {
                "files": current_batch["files"],
                "directories": list(current_batch["directories"]),
                "file_count": current_batch["file_count"]
            }
    
    async def _read_file_async(self, file_path: str) -> str | None:
        """Read file content asynchronously with size limits."""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = await f.read(self.max_file_size)
                return content
        except Exception as e:
            logger.debug(f"Failed to read file {file_path}: {str(e)}")
            return None
    
    def _classify_file_type(self, extension: str) -> str:
        """Classify file type based on extension."""
        code_exts = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.hpp', 
                    '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt'}
        doc_exts = {'.md', '.txt', '.rst', '.adoc'}
        config_exts = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'}
        
        if extension in code_exts:
            return "code"
        elif extension in doc_exts:
            return "documentation"
        elif extension in config_exts:
            return "configuration"
        else:
            return "other"
    
    async def _store_repository_graph(self, repo_data: dict[str, Any]) -> None:
        """Store repository data as a graph in Neo4j with batch processing and performance monitoring."""
        start_time = time.time()
        
        async with self.driver.session() as session:
            # Create repository node
            repo_query = """
            MERGE (r:Repository {name: $name, owner: $owner, url: $url})
            SET r.full_name = $full_name,
                r.file_count = $file_count,
                r.analyzed_at = datetime()
            RETURN r
            """
            
            await session.run(repo_query, {
                "name": repo_data["repository"]["name"],
                "owner": repo_data["repository"]["owner"],
                "url": repo_data["repository"]["url"],
                "full_name": repo_data["repository"]["full_name"],
                "file_count": repo_data["file_count"]
            })
            
            nodes_created = 1  # Repository node
            
            # Create directory nodes in batches
            if repo_data["directories"]:
                nodes_created += await self._create_directories_batch(
                    session, repo_data["directories"], repo_data["repository"]["name"]
                )
            
            # Create file nodes in batches
            if repo_data["files"]:
                nodes_created += await self._create_files_batch(
                    session, repo_data["files"], repo_data["repository"]["name"]
                )
            
            repo_data["nodes_created"] = nodes_created
            self.performance_metrics["storage_time"] = time.time() - start_time
            
            logger.info(f"Created {nodes_created} nodes in Neo4j for repository {repo_data['repository']['name']} "
                       f"in {self.performance_metrics['storage_time']:.2f}s")
    
    async def _create_directories_batch(self, session, directories: list[str], repo_name: str) -> int:
        """Create directory nodes in batches for better performance."""
        nodes_created = 0
        
        for i in range(0, len(directories), self.batch_size):
            batch = directories[i:i + self.batch_size]
            
            # Create batch query
            dir_query = """
            UNWIND $directories as dir
            MATCH (r:Repository {name: $repo_name})
            MERGE (d:Directory {path: dir.path, repository: $repo_name})
            MERGE (r)-[:CONTAINS]->(d)
            """
            
            batch_params = {
                "repo_name": repo_name,
                "directories": [{"path": dir_path} for dir_path in batch]
            }
            
            async with self.query_monitor.monitor_query(
                f"create_directories_batch_{i//self.batch_size}",
                dir_query,
                batch_params
            ):
                await session.run(dir_query, batch_params)
            
            nodes_created += len(batch)
            
            # Allow other tasks to run
            await asyncio.sleep(0)
        
        return nodes_created
    
    async def _create_files_batch(self, session, files: list[dict[str, Any]], repo_name: str) -> int:
        """Create file nodes in batches for better performance."""
        nodes_created = 0
        
        for i in range(0, len(files), self.batch_size):
            batch = files[i:i + self.batch_size]
            
            # Create batch query for files
            file_query = """
            UNWIND $files as file
            MATCH (r:Repository {name: $repo_name})
            MERGE (f:File {path: file.path, repository: $repo_name})
            SET f.name = file.name,
                f.extension = file.extension,
                f.size = file.size,
                f.type = file.type,
                f.content = file.content
            MERGE (r)-[:CONTAINS]->(f)
            """
            
            batch_params = {
                "repo_name": repo_name,
                "files": [
                    {
                        "path": file_info["path"],
                        "name": file_info["name"],
                        "extension": file_info["extension"],
                        "size": file_info["size"],
                        "type": file_info.get("type", "other"),
                        "content": file_info.get("content", "")
                    }
                    for file_info in batch
                ]
            }
            
            async with self.query_monitor.monitor_query(
                f"create_files_batch_{i//self.batch_size}",
                file_query,
                batch_params
            ):
                await session.run(file_query, batch_params)
            
            # Create directory relationships in batch
            await self._create_directory_relationships_batch(session, batch, repo_name)
            
            nodes_created += len(batch)
            
            # Allow other tasks to run
            await asyncio.sleep(0)
        
        return nodes_created
    
    async def _create_directory_relationships_batch(self, session, files: list[dict[str, Any]], repo_name: str):
        """Create directory-file relationships in batch."""
        relationships = []
        
        for file_info in files:
            parent_dir = str(Path(file_info["path"]).parent)
            if parent_dir != '.':
                relationships.append({
                    "dir_path": parent_dir,
                    "file_path": file_info["path"]
                })
        
        if relationships:
            rel_query = """
            UNWIND $relationships as rel
            MATCH (d:Directory {path: rel.dir_path, repository: $repo_name})
            MATCH (f:File {path: rel.file_path, repository: $repo_name})
            MERGE (d)-[:CONTAINS]->(f)
            """
            
            await session.run(rel_query, {
                "repo_name": repo_name,
                "relationships": relationships
            })
    
    def get_performance_metrics(self) -> dict[str, float]:
        """Get performance metrics for the last operation."""
        return dict(self.performance_metrics)