"""
Unified data models for the ingestion pipeline.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from pathlib import Path
import time


class ContentType(Enum):
    """Content source types."""
    GITHUB_REPOSITORY = "github_repository"
    WEB_PAGE = "web_page"
    LOCAL_FOLDER = "local_folder"
    LOCAL_FILE = "local_file"


class ContentFormat(Enum):
    """Content format types."""
    CODE = "code"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    TEXT = "text"
    MARKDOWN = "markdown"
    OTHER = "other"


@dataclass
class ContentSource:
    """Represents a content source to be ingested."""
    source_type: ContentType
    source_id: str  # URL, path, or unique identifier
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate and normalize source data."""
        if self.source_type == ContentType.GITHUB_REPOSITORY:
            # Ensure GitHub URL format
            if not self.source_id.startswith(('https://github.com/', 'git@github.com:')):
                raise ValueError(f"Invalid GitHub repository URL: {self.source_id}")
        
        elif self.source_type == ContentType.WEB_PAGE:
            # Ensure web URL format
            if not self.source_id.startswith(('http://', 'https://')):
                raise ValueError(f"Invalid web URL: {self.source_id}")
        
        elif self.source_type in (ContentType.LOCAL_FOLDER, ContentType.LOCAL_FILE):
            # Ensure path exists
            if not Path(self.source_id).exists():
                raise ValueError(f"Path does not exist: {self.source_id}")


@dataclass
class ContentChunk:
    """Represents a chunk of content for vector embedding."""
    chunk_id: str
    content: str
    content_format: ContentFormat
    source_path: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def __post_init__(self):
        """Generate chunk ID if not provided."""
        if not self.chunk_id:
            # Generate hash-based ID from content and path
            import hashlib
            content_hash = hashlib.md5(f"{self.source_path}:{self.content[:100]}".encode()).hexdigest()
            self.chunk_id = f"{self.content_format.value}_{content_hash}"


@dataclass
class StructuralNode:
    """Represents a node in the knowledge graph."""
    node_type: str  # Repository, Directory, File, Page, etc.
    node_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_relationship(self, relationship_type: str, target_node_id: str, properties: Optional[Dict[str, Any]] = None):
        """Add a relationship to another node."""
        self.relationships.append({
            "type": relationship_type,
            "target": target_node_id,
            "properties": properties or {}
        })


@dataclass
class IngestionResult:
    """Result of content ingestion process."""
    source: ContentSource
    success: bool
    chunks_created: int = 0
    nodes_created: int = 0
    relationships_created: int = 0
    processing_time: float = 0.0
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Database-specific results
    neo4j_result: Optional[Dict[str, Any]] = None
    qdrant_result: Optional[Dict[str, Any]] = None


@dataclass
class ProcessedContent:
    """Container for processed content ready for dual ingestion."""
    source: ContentSource
    
    # For Neo4j (structural data)
    structural_nodes: List[StructuralNode] = field(default_factory=list)
    
    # For Qdrant (vector embeddings)
    content_chunks: List[ContentChunk] = field(default_factory=list)
    
    # Processing metadata
    processing_stats: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize processing stats."""
        if not self.processing_stats:
            self.processing_stats = {
                "extraction_start_time": time.time(),
                "nodes_extracted": len(self.structural_nodes),
                "chunks_extracted": len(self.content_chunks),
                "total_content_size": sum(len(chunk.content) for chunk in self.content_chunks)
            }


class ContentExtractor(ABC):
    """Abstract base class for content extractors."""
    
    @abstractmethod
    async def extract(self, source: ContentSource) -> ProcessedContent:
        """Extract content from a source into both structural and chunk formats."""
        pass
    
    @abstractmethod
    def supports_source_type(self, source_type: ContentType) -> bool:
        """Check if this extractor supports the given source type."""
        pass


class DatabaseIngester(ABC):
    """Abstract base class for database ingesters."""
    
    @abstractmethod
    async def ingest(self, processed_content: ProcessedContent) -> Dict[str, Any]:
        """Ingest processed content into the database."""
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize database connection."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close database connection."""
        pass


@dataclass
class IngestionConfig:
    """Configuration for the ingestion pipeline."""
    
    # Hardware optimization (i7-13700K specific)
    max_workers: int = 16  # Use P-cores with hyperthreading
    batch_size: int = 300  # Optimized for 24-thread CPU
    max_file_size: int = 2097152  # 2MB with 32GB RAM
    
    # Embedding configuration
    embedding_batch_size: int = 64
    max_concurrent_embeddings: int = 12
    
    # Neo4j configuration
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"
    
    # Qdrant configuration
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "crawl4rag_default"
    
    # Content filtering
    supported_extensions: List[str] = field(default_factory=lambda: [
        '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.hpp',
        '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt',  # Code
        '.md', '.txt', '.rst', '.adoc',  # Documentation
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'  # Configuration
    ])
    
    ignore_patterns: List[str] = field(default_factory=lambda: [
        'node_modules', '__pycache__', '.git', '.svn', 'target', 
        'build', 'dist', '.venv', 'venv', '.pytest_cache'
    ])
    
    # Performance monitoring
    enable_performance_monitoring: bool = True
    enable_detailed_logging: bool = False


# Utility functions for content classification
def classify_content_format(file_path: str, content: str = "") -> ContentFormat:
    """Classify content format based on file extension and content."""
    file_path = file_path.lower()
    
    code_extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.hpp', 
                      '.cs', '.php', '.rb', '.go', '.rs', '.swift', '.kt'}
    doc_extensions = {'.md', '.txt', '.rst', '.adoc'}
    config_extensions = {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'}
    
    extension = Path(file_path).suffix.lower()
    
    if extension in code_extensions:
        return ContentFormat.CODE
    elif extension in doc_extensions:
        if extension == '.md':
            return ContentFormat.MARKDOWN
        return ContentFormat.DOCUMENTATION
    elif extension in config_extensions:
        return ContentFormat.CONFIGURATION
    else:
        # Try to classify by content if available
        if content:
            if any(keyword in content.lower() for keyword in ['def ', 'function ', 'class ', 'import ', '#include']):
                return ContentFormat.CODE
            elif content.startswith('#') or '##' in content:
                return ContentFormat.MARKDOWN
        
        return ContentFormat.OTHER


def generate_node_id(node_type: str, identifier: str) -> str:
    """Generate a unique node ID for the knowledge graph."""
    import hashlib
    combined = f"{node_type}:{identifier}"
    return f"{node_type}_{hashlib.md5(combined.encode()).hexdigest()[:12]}"


def chunk_content(content: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """Split content into overlapping chunks for embedding."""
    if len(content) <= chunk_size:
        return [content]
    
    chunks = []
    start = 0
    
    while start < len(content):
        end = start + chunk_size
        chunk = content[start:end]
        
        # Try to break at word boundaries
        if end < len(content):
            last_space = chunk.rfind(' ')
            if last_space > start + chunk_size // 2:
                chunk = chunk[:last_space]
                end = start + last_space
        
        chunks.append(chunk.strip())
        start = end - overlap
        
        if start >= len(content):
            break
    
    return chunks