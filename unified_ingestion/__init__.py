"""
Unified Ingestion Pipeline for Neo4j + Qdrant

A comprehensive content ingestion system that handles:
- GitHub repositories
- Web pages  
- Local folders and files

Outputs to both:
- Neo4j (structural/graph relationships)
- Qdrant (semantic vector embeddings)

Optimized for Intel i7-13700K hardware.
"""

from .data_models import (
    ContentType,
    ContentFormat, 
    ContentSource,
    ContentChunk,
    StructuralNode,
    ProcessedContent,
    IngestionResult,
    IngestionConfig,
    classify_content_format,
    generate_node_id,
    chunk_content
)

from .extractors import (
    ContentExtractor,
    GitHubRepositoryExtractor,
    WebPageExtractor,
    LocalFolderExtractor,
    create_extractor
)

from .database_ingesters import (
    DatabaseIngester,
    Neo4jIngester,
    QdrantIngester, 
    UnifiedIngester
)

from .pipeline import (
    UnifiedIngestionPipeline,
    ingest_github_repo,
    ingest_web_page,
    ingest_local_folder,
    hybrid_search
)

__version__ = "1.0.0"
__author__ = "Claude & User"

__all__ = [
    # Core pipeline
    "UnifiedIngestionPipeline",
    
    # Data models
    "ContentType",
    "ContentFormat",
    "ContentSource", 
    "ContentChunk",
    "StructuralNode",
    "ProcessedContent",
    "IngestionResult",
    "IngestionConfig",
    
    # Extractors
    "ContentExtractor",
    "GitHubRepositoryExtractor",
    "WebPageExtractor", 
    "LocalFolderExtractor",
    "create_extractor",
    
    # Database ingesters
    "DatabaseIngester",
    "Neo4jIngester",
    "QdrantIngester",
    "UnifiedIngester",
    
    # Convenience functions
    "ingest_github_repo",
    "ingest_web_page", 
    "ingest_local_folder",
    "hybrid_search",
    
    # Utilities
    "classify_content_format",
    "generate_node_id",
    "chunk_content"
]


def get_default_config() -> IngestionConfig:
    """Get default configuration optimized for i7-13700K."""
    return IngestionConfig()


def create_pipeline(config: IngestionConfig = None) -> UnifiedIngestionPipeline:
    """Create a new unified ingestion pipeline."""
    return UnifiedIngestionPipeline(config or get_default_config())