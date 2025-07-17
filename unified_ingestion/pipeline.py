"""
Main unified ingestion pipeline orchestrator.
"""
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from urllib.parse import urlparse

# Import our components
from .data_models import (
    ContentSource, ContentType, IngestionConfig, IngestionResult, ProcessedContent
)
from .extractors import create_extractor
from .database_ingesters import UnifiedIngester
from knowledge_graphs.performance_monitor import get_performance_monitor

logger = logging.getLogger(__name__)


class UnifiedIngestionPipeline:
    """
    Main pipeline that coordinates content extraction and dual database ingestion.
    
    Supports:
    - GitHub repositories
    - Web pages  
    - Local folders and files
    
    Outputs to:
    - Neo4j (structural/graph data)
    - Qdrant (vector embeddings)
    """
    
    def __init__(self, config: Optional[IngestionConfig] = None):
        self.config = config or IngestionConfig()
        self.ingester = UnifiedIngester(self.config)
        self.performance_monitor = get_performance_monitor()
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the pipeline and database connections."""
        if self._initialized:
            return
        
        logger.info("Initializing unified ingestion pipeline...")
        await self.ingester.initialize()
        self._initialized = True
        logger.info("Pipeline initialization completed")
    
    async def close(self) -> None:
        """Close pipeline and database connections."""
        if self._initialized:
            await self.ingester.close()
            self._initialized = False
            logger.info("Pipeline closed")
    
    async def ingest_source(self, source_identifier: str, source_type: Optional[ContentType] = None, 
                           metadata: Optional[Dict[str, Any]] = None) -> IngestionResult:
        """
        Ingest content from any source type.
        
        Args:
            source_identifier: URL, file path, or repository identifier
            source_type: Explicit source type (auto-detected if None)
            metadata: Additional metadata for the source
            
        Returns:
            IngestionResult with detailed processing information
        """
        if not self._initialized:
            await self.initialize()
        
        # Auto-detect source type if not provided
        if source_type is None:
            source_type = self._detect_source_type(source_identifier)
        
        # Create content source
        source = ContentSource(
            source_type=source_type,
            source_id=source_identifier,
            metadata=metadata or {}
        )
        
        return await self._process_source(source)
    
    async def ingest_multiple(self, sources: List[Dict[str, Any]], 
                             max_concurrent: Optional[int] = None) -> List[IngestionResult]:
        """
        Ingest multiple sources concurrently.
        
        Args:
            sources: List of source dictionaries with 'identifier' and optional 'type', 'metadata'
            max_concurrent: Maximum concurrent ingestions (defaults to config setting)
            
        Returns:
            List of IngestionResult objects
        """
        if not self._initialized:
            await self.initialize()
        
        max_concurrent = max_concurrent or self.config.max_workers
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(source_info: Dict[str, Any]) -> IngestionResult:
            async with semaphore:
                return await self.ingest_source(
                    source_identifier=source_info["identifier"],
                    source_type=source_info.get("type"),
                    metadata=source_info.get("metadata")
                )
        
        # Process all sources concurrently
        tasks = [process_with_semaphore(source_info) for source_info in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to failed IngestionResults
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                source_info = sources[i]
                failed_result = IngestionResult(
                    source=ContentSource(
                        source_type=source_info.get("type", ContentType.WEB_PAGE),
                        source_id=source_info["identifier"]
                    ),
                    success=False,
                    errors=[str(result)]
                )
                final_results.append(failed_result)
            else:
                final_results.append(result)
        
        return final_results
    
    async def _process_source(self, source: ContentSource) -> IngestionResult:
        """Process a single content source through the complete pipeline."""
        start_time = time.time()
        
        try:
            logger.info(f"Processing {source.source_type.value}: {source.source_id}")
            
            # Extract content using appropriate extractor
            extractor = create_extractor(source.source_type, self.config)
            
            async with self.performance_monitor.measure_operation(
                "content_extraction",
                source.source_type.value,
                {"source_id": source.source_id}
            ):
                processed_content = await extractor.extract(source)
            
            # Ingest into both databases
            async with self.performance_monitor.measure_operation(
                "dual_database_ingestion", 
                source.source_type.value,
                {"source_id": source.source_id}
            ):
                ingestion_result = await self.ingester.ingest(processed_content)
            
            # Record metrics
            self.performance_monitor.record_metric(
                "content_chunks_processed",
                len(processed_content.content_chunks),
                source.source_type.value,
                {"source": source.source_id}
            )
            
            self.performance_monitor.record_metric(
                "structural_nodes_created",
                len(processed_content.structural_nodes),
                source.source_type.value,
                {"source": source.source_id}
            )
            
            # Create final result
            total_time = time.time() - start_time
            result = IngestionResult(
                source=source,
                success=True,
                chunks_created=len(processed_content.content_chunks),
                nodes_created=ingestion_result.get("nodes_created", 0),
                relationships_created=ingestion_result.get("relationships_created", 0),
                processing_time=total_time,
                metadata={
                    "extraction_stats": processed_content.processing_stats,
                    "performance_metrics": self.performance_monitor.get_metrics()
                },
                neo4j_result=ingestion_result.get("neo4j_result"),
                qdrant_result=ingestion_result.get("qdrant_result")
            )
            
            logger.info(f"Successfully processed {source.source_type.value} in {total_time:.2f}s: "
                       f"{result.chunks_created} chunks, {result.nodes_created} nodes")
            
            return result
            
        except Exception as e:
            error_time = time.time() - start_time
            logger.error(f"Failed to process {source.source_type.value} {source.source_id}: {str(e)}")
            
            return IngestionResult(
                source=source,
                success=False,
                processing_time=error_time,
                errors=[str(e)]
            )
    
    def _detect_source_type(self, identifier: str) -> ContentType:
        """Auto-detect the source type from the identifier."""
        # GitHub repository detection
        if (identifier.startswith('https://github.com/') or 
            identifier.startswith('git@github.com:') or
            identifier.startswith('github.com/')):
            return ContentType.GITHUB_REPOSITORY
        
        # Web page detection
        if identifier.startswith(('http://', 'https://')):
            return ContentType.WEB_PAGE
        
        # Local path detection
        path = Path(identifier)
        if path.exists():
            if path.is_file():
                return ContentType.LOCAL_FILE
            elif path.is_dir():
                return ContentType.LOCAL_FOLDER
        
        # Default fallback - assume it's a web page if it looks like a URL
        parsed = urlparse(identifier)
        if parsed.netloc:
            return ContentType.WEB_PAGE
        
        # Final fallback - treat as local path
        return ContentType.LOCAL_FOLDER
    
    async def get_ingestion_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics about ingested content."""
        if not self._initialized:
            return {"error": "Pipeline not initialized"}
        
        try:
            # Get verification from both databases
            verification = await self.ingester.verify_ingestion(ProcessedContent(
                source=ContentSource(ContentType.WEB_PAGE, "dummy")
            ))
            
            # Get performance metrics
            performance_metrics = self.performance_monitor.get_metrics()
            
            return {
                "database_verification": verification,
                "performance_metrics": performance_metrics,
                "pipeline_config": {
                    "max_workers": self.config.max_workers,
                    "batch_size": self.config.batch_size,
                    "max_file_size": self.config.max_file_size,
                    "embedding_batch_size": self.config.embedding_batch_size
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get ingestion stats: {str(e)}")
            return {"error": str(e)}
    
    async def search_hybrid(self, query: str, limit: int = 10, 
                           include_graph: bool = True, include_vector: bool = True) -> Dict[str, Any]:
        """
        Perform hybrid search across both Neo4j and Qdrant.
        
        Args:
            query: Search query
            limit: Maximum results to return
            include_graph: Include Neo4j graph search results
            include_vector: Include Qdrant vector search results
            
        Returns:
            Combined search results from both databases
        """
        if not self._initialized:
            await self.initialize()
        
        results = {"query": query, "results": {}}
        
        try:
            search_tasks = []
            
            # Neo4j graph search
            if include_graph and self.ingester.neo4j_ingester.driver:
                search_tasks.append(self._search_neo4j(query, limit))
            
            # Qdrant vector search  
            if include_vector and self.ingester.qdrant_ingester.client:
                search_tasks.append(self._search_qdrant(query, limit))
            
            if search_tasks:
                search_results = await asyncio.gather(*search_tasks, return_exceptions=True)
                
                if include_graph and len(search_results) > 0:
                    results["results"]["graph_search"] = search_results[0] if not isinstance(search_results[0], Exception) else {"error": str(search_results[0])}
                
                if include_vector:
                    vector_index = 1 if include_graph else 0
                    if len(search_results) > vector_index:
                        results["results"]["vector_search"] = search_results[vector_index] if not isinstance(search_results[vector_index], Exception) else {"error": str(search_results[vector_index])}
            
            return results
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {str(e)}")
            return {"query": query, "error": str(e)}
    
    async def _search_neo4j(self, query: str, limit: int) -> Dict[str, Any]:
        """Search Neo4j for structural/graph matches."""
        async with self.ingester.neo4j_ingester.driver.session() as session:
            # Simple content search across all node types
            cypher_query = """
            MATCH (n)
            WHERE ANY(prop IN keys(n) WHERE toString(n[prop]) CONTAINS $query)
            RETURN n, labels(n) as node_types
            LIMIT $limit
            """
            
            result = await session.run(cypher_query, {"query": query, "limit": limit})
            records = [{"node": dict(record["n"]), "types": record["node_types"]} async for record in result]
            
            return {"matches": records, "count": len(records)}
    
    async def _search_qdrant(self, query: str, limit: int) -> Dict[str, Any]:
        """Search Qdrant for semantic/vector matches."""
        from src.utils.embedding_utils import create_embeddings_batch
        
        # Generate embedding for query
        query_embeddings = await create_embeddings_batch([query])
        query_vector = query_embeddings[0]
        
        # Search Qdrant
        search_results = self.ingester.qdrant_ingester.client.search(
            collection_name=self.config.qdrant_collection,
            query_vector=query_vector,
            limit=limit,
            with_payload=True
        )
        
        matches = []
        for hit in search_results:
            matches.append({
                "score": hit.score,
                "content": hit.payload.get("content", ""),
                "metadata": {k: v for k, v in hit.payload.items() if k != "content"}
            })
        
        return {"matches": matches, "count": len(matches)}


# Convenience functions for easy usage
async def ingest_github_repo(repo_url: str, config: Optional[IngestionConfig] = None) -> IngestionResult:
    """Convenience function to ingest a GitHub repository."""
    pipeline = UnifiedIngestionPipeline(config)
    try:
        return await pipeline.ingest_source(repo_url, ContentType.GITHUB_REPOSITORY)
    finally:
        await pipeline.close()


async def ingest_web_page(url: str, config: Optional[IngestionConfig] = None) -> IngestionResult:
    """Convenience function to ingest a web page."""
    pipeline = UnifiedIngestionPipeline(config)
    try:
        return await pipeline.ingest_source(url, ContentType.WEB_PAGE)
    finally:
        await pipeline.close()


async def ingest_local_folder(folder_path: str, config: Optional[IngestionConfig] = None) -> IngestionResult:
    """Convenience function to ingest a local folder."""
    pipeline = UnifiedIngestionPipeline(config)
    try:
        return await pipeline.ingest_source(folder_path, ContentType.LOCAL_FOLDER)
    finally:
        await pipeline.close()


async def hybrid_search(query: str, limit: int = 10, config: Optional[IngestionConfig] = None) -> Dict[str, Any]:
    """Convenience function for hybrid search."""
    pipeline = UnifiedIngestionPipeline(config)
    try:
        await pipeline.initialize()
        return await pipeline.search_hybrid(query, limit)
    finally:
        await pipeline.close()