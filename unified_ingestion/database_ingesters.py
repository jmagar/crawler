"""
Database ingesters for Neo4j and Qdrant coordination.
"""
import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient, models
from qdrant_client.models import Distance, VectorParams, PointStruct

# Import existing utilities
from src.utils.embedding_utils import create_embeddings_batch
from src.utils.qdrant_utils import get_qdrant_client, setup_qdrant_collections

# Import our data models
from .data_models import (
    DatabaseIngester, ProcessedContent, StructuralNode, ContentChunk,
    IngestionConfig, IngestionResult
)

logger = logging.getLogger(__name__)


class Neo4jIngester(DatabaseIngester):
    """Handles ingestion into Neo4j knowledge graph."""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
        self.driver = None
    
    async def initialize(self) -> None:
        """Initialize Neo4j connection."""
        try:
            self.driver = AsyncGraphDatabase.driver(
                self.config.neo4j_uri,
                auth=(self.config.neo4j_user, self.config.neo4j_password)
            )
            # Test connection
            async with self.driver.session() as session:
                await session.run("RETURN 1")
            logger.info("Neo4j ingester initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j ingester: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Close Neo4j connection."""
        if self.driver:
            await self.driver.close()
            logger.info("Neo4j ingester closed")
    
    async def ingest(self, processed_content: ProcessedContent) -> Dict[str, Any]:
        """Ingest structural data into Neo4j."""
        if not self.driver:
            raise RuntimeError("Neo4j ingester not initialized")
        
        start_time = time.time()
        nodes_created = 0
        relationships_created = 0
        
        async with self.driver.session() as session:
            # Create nodes in batches
            for i in range(0, len(processed_content.structural_nodes), self.config.batch_size):
                batch = processed_content.structural_nodes[i:i + self.config.batch_size]
                batch_result = await self._create_nodes_batch(session, batch)
                nodes_created += batch_result["nodes_created"]
                relationships_created += batch_result["relationships_created"]
                
                # Allow other tasks to run
                await asyncio.sleep(0)
        
        ingestion_time = time.time() - start_time
        
        result = {
            "nodes_created": nodes_created,
            "relationships_created": relationships_created,
            "ingestion_time": ingestion_time,
            "success": True
        }
        
        logger.info(f"Neo4j ingestion completed: {nodes_created} nodes, "
                   f"{relationships_created} relationships in {ingestion_time:.2f}s")
        
        return result
    
    async def _create_nodes_batch(self, session, nodes: List[StructuralNode]) -> Dict[str, Any]:
        """Create a batch of nodes and their relationships."""
        nodes_created = 0
        relationships_created = 0
        
        # Create nodes
        for node in nodes:
            node_query = f"""
            MERGE (n:{node.node_type} {{id: $node_id}})
            SET n += $properties
            RETURN n
            """
            
            await session.run(node_query, {
                "node_id": node.node_id,
                "properties": node.properties
            })
            nodes_created += 1
            
            # Create relationships
            for rel in node.relationships:
                rel_query = f"""
                MATCH (source:{node.node_type} {{id: $source_id}})
                MATCH (target {{id: $target_id}})
                MERGE (source)-[r:{rel['type']}]->(target)
                SET r += $rel_properties
                RETURN r
                """
                
                await session.run(rel_query, {
                    "source_id": node.node_id,
                    "target_id": rel["target"],
                    "rel_properties": rel.get("properties", {})
                })
                relationships_created += 1
        
        return {
            "nodes_created": nodes_created,
            "relationships_created": relationships_created
        }


class QdrantIngester(DatabaseIngester):
    """Handles ingestion into Qdrant vector database."""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
        self.client = None
        self.collection_name = config.qdrant_collection
    
    async def initialize(self) -> None:
        """Initialize Qdrant connection and ensure collection exists."""
        try:
            self.client = get_qdrant_client()
            
            # Ensure collection exists
            try:
                collection_info = self.client.get_collection(self.collection_name)
                logger.info(f"Using existing Qdrant collection: {self.collection_name}")
            except Exception:
                # Create collection
                # Get embedding dimension from config or environment
                from src.utils.embedding_utils import EMBEDDING_DIMENSION
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=EMBEDDING_DIMENSION, distance=Distance.COSINE)
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
            
            logger.info("Qdrant ingester initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant ingester: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Close Qdrant connection."""
        if self.client:
            self.client.close()
            logger.info("Qdrant ingester closed")
    
    async def ingest(self, processed_content: ProcessedContent) -> Dict[str, Any]:
        """Ingest content chunks into Qdrant with embeddings."""
        if not self.client:
            raise RuntimeError("Qdrant ingester not initialized")
        
        start_time = time.time()
        chunks_ingested = 0
        
        if not processed_content.content_chunks:
            return {
                "chunks_ingested": 0,
                "ingestion_time": 0.0,
                "success": True
            }
        
        # Generate embeddings for all chunks
        chunks_with_embeddings = await self._generate_embeddings(processed_content.content_chunks)
        
        # Ingest chunks in batches
        for i in range(0, len(chunks_with_embeddings), self.config.batch_size):
            batch = chunks_with_embeddings[i:i + self.config.batch_size]
            await self._ingest_chunks_batch(batch)
            chunks_ingested += len(batch)
            
            # Allow other tasks to run
            await asyncio.sleep(0)
        
        ingestion_time = time.time() - start_time
        
        result = {
            "chunks_ingested": chunks_ingested,
            "ingestion_time": ingestion_time,
            "success": True
        }
        
        logger.info(f"Qdrant ingestion completed: {chunks_ingested} chunks in {ingestion_time:.2f}s")
        
        return result
    
    async def _generate_embeddings(self, chunks: List[ContentChunk]) -> List[ContentChunk]:
        """Generate embeddings for content chunks."""
        # Extract text content
        texts = [chunk.content for chunk in chunks]
        
        # Generate embeddings in batches using existing optimized function
        embeddings = await create_embeddings_batch(
            texts,
            batch_size=self.config.embedding_batch_size
        )
        
        # Attach embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        return chunks
    
    async def _ingest_chunks_batch(self, chunks: List[ContentChunk]) -> None:
        """Ingest a batch of chunks into Qdrant."""
        points = []
        
        for chunk in chunks:
            if chunk.embedding is None:
                logger.warning(f"Chunk {chunk.chunk_id} has no embedding, skipping")
                continue
            
            # Prepare metadata
            payload = {
                "content": chunk.content,
                "content_format": chunk.content_format.value,
                "source_path": chunk.source_path,
                "chunk_id": chunk.chunk_id,
                **chunk.metadata
            }
            
            point = PointStruct(
                id=hash(chunk.chunk_id) % (2**63),  # Convert to positive integer
                vector=chunk.embedding,
                payload=payload
            )
            points.append(point)
        
        if points:
            # Use async operation if available, fallback to sync
            try:
                # Try async upsert (newer versions)
                if hasattr(self.client, 'upsert_async'):
                    await self.client.upsert_async(
                        collection_name=self.collection_name,
                        points=points
                    )
                else:
                    # Use sync upsert in executor
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self.client.upsert(
                            collection_name=self.collection_name,
                            points=points
                        )
                    )
            except Exception as e:
                logger.error(f"Failed to upsert batch to Qdrant: {str(e)}")
                raise


class UnifiedIngester(DatabaseIngester):
    """Coordinates ingestion into both Neo4j and Qdrant."""
    
    def __init__(self, config: IngestionConfig):
        self.config = config
        self.neo4j_ingester = Neo4jIngester(config)
        self.qdrant_ingester = QdrantIngester(config)
    
    async def initialize(self) -> None:
        """Initialize both database ingesters."""
        await asyncio.gather(
            self.neo4j_ingester.initialize(),
            self.qdrant_ingester.initialize()
        )
        logger.info("Unified ingester initialized")
    
    async def close(self) -> None:
        """Close both database connections."""
        await asyncio.gather(
            self.neo4j_ingester.close(),
            self.qdrant_ingester.close()
        )
        logger.info("Unified ingester closed")
    
    async def ingest(self, processed_content: ProcessedContent) -> Dict[str, Any]:
        """Ingest into both databases simultaneously."""
        start_time = time.time()
        
        # Ingest into both databases concurrently
        neo4j_task = asyncio.create_task(self.neo4j_ingester.ingest(processed_content))
        qdrant_task = asyncio.create_task(self.qdrant_ingester.ingest(processed_content))
        
        try:
            neo4j_result, qdrant_result = await asyncio.gather(neo4j_task, qdrant_task)
            
            total_time = time.time() - start_time
            
            result = {
                "success": True,
                "total_ingestion_time": total_time,
                "neo4j_result": neo4j_result,
                "qdrant_result": qdrant_result,
                "nodes_created": neo4j_result.get("nodes_created", 0),
                "relationships_created": neo4j_result.get("relationships_created", 0),
                "chunks_ingested": qdrant_result.get("chunks_ingested", 0)
            }
            
            logger.info(f"Unified ingestion completed in {total_time:.2f}s: "
                       f"{result['nodes_created']} nodes, {result['chunks_ingested']} chunks")
            
            return result
            
        except Exception as e:
            logger.error(f"Unified ingestion failed: {str(e)}")
            raise
    
    async def verify_ingestion(self, processed_content: ProcessedContent) -> Dict[str, Any]:
        """Verify that data was correctly ingested into both databases."""
        verification_result = {
            "neo4j_verification": {},
            "qdrant_verification": {},
            "success": True
        }
        
        try:
            # Verify Neo4j ingestion
            if self.neo4j_ingester.driver:
                async with self.neo4j_ingester.driver.session() as session:
                    # Count nodes by type
                    node_types = set(node.node_type for node in processed_content.structural_nodes)
                    for node_type in node_types:
                        result = await session.run(f"MATCH (n:{node_type}) RETURN count(n) as count")
                        record = await result.single()
                        verification_result["neo4j_verification"][f"{node_type}_count"] = record["count"]
            
            # Verify Qdrant ingestion
            if self.qdrant_ingester.client:
                collection_info = self.qdrant_ingester.client.get_collection(self.config.qdrant_collection)
                verification_result["qdrant_verification"]["total_points"] = collection_info.points_count
        
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            verification_result["success"] = False
            verification_result["error"] = str(e)
        
        return verification_result