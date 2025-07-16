"""
DirectNeo4jExtractor for parsing repositories into Neo4j knowledge graph.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
import aiohttp
import git
import tempfile
import os
import shutil
from pathlib import Path

from neo4j import AsyncGraphDatabase
from src.core.validation import format_neo4j_error

logger = logging.getLogger(__name__)

class DirectNeo4jExtractor:
    """Extract repository information directly into Neo4j graph database."""
    
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        """Initialize the Neo4j extractor."""
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.driver = None
        
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
    
    async def analyze_repository(self, repo_url: str) -> Dict[str, Any]:
        """Analyze a GitHub repository and extract it into Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")
        
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
            
            return {
                "success": True,
                "repository": repo_info["name"],
                "files_processed": repo_data.get("file_count", 0),
                "nodes_created": repo_data.get("nodes_created", 0)
            }
            
        except Exception as e:
            logger.error(f"Repository analysis failed: {str(e)}")
            raise
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    def _parse_repo_url(self, repo_url: str) -> Dict[str, str]:
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
        """Clone repository to temporary directory."""
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
    
    async def _extract_repository_structure(self, repo_path: str, repo_info: Dict[str, str]) -> Dict[str, Any]:
        """Extract repository file structure and content."""
        repo_data = {
            "repository": repo_info,
            "files": [],
            "directories": [],
            "file_count": 0,
            "nodes_created": 0
        }
        
        # Supported file extensions for content extraction
        code_extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.hpp', 
                          '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt'}
        doc_extensions = {'.md', '.txt', '.rst', '.adoc'}
        config_extensions = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'}
        
        for root, dirs, files in os.walk(repo_path):
            # Skip common ignore directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in 
                      {'node_modules', '__pycache__', 'target', 'build', 'dist'}]
            
            rel_root = os.path.relpath(root, repo_path)
            if rel_root != '.':
                repo_data["directories"].append(rel_root)
            
            for file in files:
                if file.startswith('.'):
                    continue
                    
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, repo_path)
                file_ext = Path(file).suffix.lower()
                
                file_info = {
                    "path": rel_path,
                    "name": file,
                    "extension": file_ext,
                    "size": os.path.getsize(file_path)
                }
                
                # Extract content for supported file types
                if file_ext in code_extensions or file_ext in doc_extensions or file_ext in config_extensions:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            if len(content) <= 50000:  # Limit content size
                                file_info["content"] = content
                                file_info["type"] = self._classify_file_type(file_ext)
                    except Exception as e:
                        logger.warning(f"Could not read file {rel_path}: {str(e)}")
                
                repo_data["files"].append(file_info)
                repo_data["file_count"] += 1
        
        return repo_data
    
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
    
    async def _store_repository_graph(self, repo_data: Dict[str, Any]) -> None:
        """Store repository data as a graph in Neo4j."""
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
            
            # Create directory nodes and relationships
            for dir_path in repo_data["directories"]:
                dir_query = """
                MATCH (r:Repository {name: $repo_name})
                MERGE (d:Directory {path: $path, repository: $repo_name})
                MERGE (r)-[:CONTAINS]->(d)
                """
                
                await session.run(dir_query, {
                    "repo_name": repo_data["repository"]["name"],
                    "path": dir_path
                })
                nodes_created += 1
            
            # Create file nodes and relationships
            for file_info in repo_data["files"]:
                # Determine parent directory
                parent_dir = str(Path(file_info["path"]).parent)
                if parent_dir == '.':
                    parent_dir = None
                
                file_query = """
                MATCH (r:Repository {name: $repo_name})
                MERGE (f:File {path: $path, repository: $repo_name})
                SET f.name = $name,
                    f.extension = $extension,
                    f.size = $size,
                    f.type = $type
                MERGE (r)-[:CONTAINS]->(f)
                """
                
                params = {
                    "repo_name": repo_data["repository"]["name"],
                    "path": file_info["path"],
                    "name": file_info["name"],
                    "extension": file_info["extension"],
                    "size": file_info["size"],
                    "type": file_info.get("type", "other")
                }
                
                # Add content if available
                if "content" in file_info:
                    file_query += " SET f.content = $content"
                    params["content"] = file_info["content"]
                
                await session.run(file_query, params)
                
                # Create relationship to parent directory
                if parent_dir:
                    dir_rel_query = """
                    MATCH (d:Directory {path: $dir_path, repository: $repo_name})
                    MATCH (f:File {path: $file_path, repository: $repo_name})
                    MERGE (d)-[:CONTAINS]->(f)
                    """
                    
                    await session.run(dir_rel_query, {
                        "repo_name": repo_data["repository"]["name"],
                        "dir_path": parent_dir,
                        "file_path": file_info["path"]
                    })
                
                nodes_created += 1
            
            repo_data["nodes_created"] = nodes_created
            logger.info(f"Created {nodes_created} nodes in Neo4j for repository {repo_data['repository']['name']}")