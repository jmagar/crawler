"""
Async wrapper for Qdrant operations to prevent blocking the event loop.
Provides timeout-protected database operations with proper error handling.
"""
import asyncio
import concurrent.futures
import logging
from typing import List, Dict, Any, Optional, Union
from qdrant_client import QdrantClient, models
from qdrant_client.models import PointStruct, Filter

from ..core.timeout_utils import with_database_timeout, TimeoutConfig

logger = logging.getLogger(__name__)

class AsyncQdrantWrapper:
    """
    Async wrapper for QdrantClient that prevents blocking operations.
    Executes all synchronous Qdrant operations in a thread pool with timeouts.
    """
    
    def __init__(self, client: QdrantClient, max_workers: int = 4):
        """
        Initialize async wrapper with thread pool.
        
        Args:
            client: Synchronous QdrantClient instance
            max_workers: Maximum number of worker threads
        """
        self.client = client
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        logger.info(f"Initialized AsyncQdrantWrapper with {max_workers} workers")
    
    async def close(self):
        """Close the thread pool executor."""
        if self.executor:
            self.executor.shutdown(wait=True)
            logger.info("AsyncQdrantWrapper executor shutdown")
    
    async def search_async(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        query_filter: Optional[Filter] = None,
        **kwargs
    ) -> List[models.ScoredPoint]:
        """
        Async search operation with timeout protection.
        
        Args:
            collection_name: Name of the collection to search
            query_vector: Query vector for similarity search
            limit: Maximum number of results
            query_filter: Optional filter for search
            **kwargs: Additional search parameters
            
        Returns:
            List of scored points
        """
        def _search():
            return self.client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                query_filter=query_filter,
                **kwargs
            )
        
        return await with_database_timeout(
            asyncio.get_event_loop().run_in_executor(self.executor, _search),
            operation_name=f"search {collection_name}"
        )
    
    async def upsert_async(
        self,
        collection_name: str,
        points: List[PointStruct],
        wait: bool = True,
        **kwargs
    ) -> models.UpdateResult:
        """
        Async upsert operation with timeout protection.
        
        Args:
            collection_name: Name of the collection
            points: List of points to upsert
            wait: Whether to wait for completion
            **kwargs: Additional upsert parameters
            
        Returns:
            Update result
        """
        def _upsert():
            return self.client.upsert(
                collection_name=collection_name,
                points=points,
                wait=wait,
                **kwargs
            )
        
        # Use batch timeout for upsert operations
        timeout = TimeoutConfig.QDRANT_BATCH_TIMEOUT if len(points) > 10 else TimeoutConfig.QDRANT_OPERATION_TIMEOUT
        
        return await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(self.executor, _upsert),
            timeout=timeout
        )
    
    async def scroll_async(
        self,
        collection_name: str,
        limit: int = 100,
        offset: Optional[Union[str, models.PointId]] = None,
        with_payload: bool = True,
        with_vectors: bool = False,
        **kwargs
    ) -> tuple:
        """
        Async scroll operation with timeout protection.
        
        Args:
            collection_name: Name of the collection
            limit: Maximum number of points to return
            offset: Optional offset for pagination
            with_payload: Include payload in results
            with_vectors: Include vectors in results
            **kwargs: Additional scroll parameters
            
        Returns:
            Tuple of (points, next_offset)
        """
        def _scroll():
            return self.client.scroll(
                collection_name=collection_name,
                limit=limit,
                offset=offset,
                with_payload=with_payload,
                with_vectors=with_vectors,
                **kwargs
            )
        
        # Use scroll timeout for potentially large operations
        timeout = TimeoutConfig.QDRANT_SCROLL_TIMEOUT
        
        return await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(self.executor, _scroll),
            timeout=timeout
        )
    
    async def delete_async(
        self,
        collection_name: str,
        points_selector: Optional[models.PointsSelector] = None,
        wait: bool = True,
        **kwargs
    ) -> models.UpdateResult:
        """
        Async delete operation with timeout protection.
        
        Args:
            collection_name: Name of the collection
            points_selector: Selector for points to delete
            wait: Whether to wait for completion
            **kwargs: Additional delete parameters
            
        Returns:
            Update result
        """
        def _delete():
            return self.client.delete(
                collection_name=collection_name,
                points_selector=points_selector,
                wait=wait,
                **kwargs
            )
        
        return await with_database_timeout(
            asyncio.get_event_loop().run_in_executor(self.executor, _delete),
            operation_name=f"delete from {collection_name}"
        )
    
    async def get_collection_async(self, collection_name: str) -> models.CollectionInfo:
        """
        Async get collection info operation.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Collection information
        """
        def _get_collection():
            return self.client.get_collection(collection_name)
        
        return await with_database_timeout(
            asyncio.get_event_loop().run_in_executor(self.executor, _get_collection),
            operation_name=f"get collection {collection_name}"
        )
    
    async def create_collection_async(
        self,
        collection_name: str,
        vectors_config: Union[models.VectorParams, Dict[str, models.VectorParams]],
        **kwargs
    ) -> bool:
        """
        Async create collection operation.
        
        Args:
            collection_name: Name of the new collection
            vectors_config: Vector configuration
            **kwargs: Additional collection parameters
            
        Returns:
            Success status
        """
        def _create_collection():
            return self.client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
                **kwargs
            )
        
        return await with_database_timeout(
            asyncio.get_event_loop().run_in_executor(self.executor, _create_collection),
            operation_name=f"create collection {collection_name}"
        )
    
    async def count_async(
        self,
        collection_name: str,
        count_filter: Optional[Filter] = None,
        exact: bool = True,
        **kwargs
    ) -> models.CountResult:
        """
        Async count operation.
        
        Args:
            collection_name: Name of the collection
            count_filter: Optional filter for counting
            exact: Whether to get exact count
            **kwargs: Additional count parameters
            
        Returns:
            Count result
        """
        def _count():
            return self.client.count(
                collection_name=collection_name,
                count_filter=count_filter,
                exact=exact,
                **kwargs
            )
        
        return await with_database_timeout(
            asyncio.get_event_loop().run_in_executor(self.executor, _count),
            operation_name=f"count {collection_name}"
        )

# Compatibility functions for existing code
async def search_documents_async(
    client: AsyncQdrantWrapper,
    query_vector: List[float],
    collection_name: str = "documents",
    match_count: int = 5,
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Search documents using async Qdrant wrapper.
    
    Args:
        client: AsyncQdrantWrapper instance
        query_vector: Query vector for similarity search
        collection_name: Name of the collection to search
        match_count: Number of results to return
        filter_metadata: Optional metadata filter
        
    Returns:
        List of search results
    """
    query_filter = None
    if filter_metadata:
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key=f"metadata.{key}",
                    match=models.MatchValue(value=value)
                )
                for key, value in filter_metadata.items()
            ]
        )
    
    try:
        hits = await client.search_async(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=match_count,
            query_filter=query_filter
        )
        
        results = []
        for hit in hits:
            result = {
                "content": hit.payload.get("content", ""),
                "metadata": hit.payload.get("metadata", {}),
                "score": hit.score,
                "url": hit.payload.get("url", ""),
                "source_id": hit.payload.get("source_id", "")
            }
            results.append(result)
        
        return results
        
    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        return []

async def add_documents_async(
    client: AsyncQdrantWrapper,
    urls: List[str],
    chunk_numbers: List[int],
    contents: List[str],
    metadatas: List[Dict[str, Any]],
    embeddings: List[List[float]],
    collection_name: str = "documents"
) -> bool:
    """
    Add documents using async Qdrant wrapper.
    
    Args:
        client: AsyncQdrantWrapper instance
        urls: List of URLs
        chunk_numbers: List of chunk numbers
        contents: List of content strings
        metadatas: List of metadata dictionaries
        embeddings: List of embedding vectors
        collection_name: Name of the collection
        
    Returns:
        Success status
    """
    try:
        points = []
        for i in range(len(contents)):
            point = PointStruct(
                id=f"{urls[i]}#{chunk_numbers[i]}",
                vector=embeddings[i],
                payload={
                    "url": urls[i],
                    "chunk_number": chunk_numbers[i],
                    "content": contents[i],
                    "metadata": metadatas[i],
                    "source_id": metadatas[i].get("source", "")
                }
            )
            points.append(point)
        
        await client.upsert_async(
            collection_name=collection_name,
            points=points,
            wait=True
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Add documents failed: {str(e)}")
        return False