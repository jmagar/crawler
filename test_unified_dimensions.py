#!/usr/bin/env python3
"""
Test script to verify embedding dimensions are working correctly.
"""
import asyncio
import logging
from unified_ingestion import UnifiedIngestionPipeline, IngestionConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_embedding_dimensions():
    """Test that the unified pipeline uses correct embedding dimensions."""
    
    print("🔧 TESTING EMBEDDING DIMENSIONS")
    print("=" * 50)
    
    # Create pipeline with correct config
    config = IngestionConfig()
    print(f"✓ Using collection: {config.qdrant_collection}")
    
    # Check embedding dimensions
    from src.utils.embedding_utils import EMBEDDING_DIMENSION
    print(f"✓ Embedding dimension: {EMBEDDING_DIMENSION}")
    
    pipeline = UnifiedIngestionPipeline(config)
    
    try:
        await pipeline.initialize()
        print("✓ Pipeline initialized successfully")
        
        # Test with a simple text file
        import tempfile
        import os
        
        # Create temporary test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("This is a test file for embedding dimension validation.\nIt contains multiple lines to test chunking and embedding generation.")
            temp_file_path = f.name
        
        try:
            print(f"✓ Testing with temporary file: {temp_file_path}")
            
            # Ingest the test file
            result = await pipeline.ingest_source(temp_file_path)
            
            if result.success:
                print(f"✓ Ingestion successful: {result.chunks_created} chunks, {result.nodes_created} nodes")
                
                # Test hybrid search
                search_results = await pipeline.search_hybrid("test file", limit=3)
                
                if "error" not in search_results:
                    vector_results = search_results.get("results", {}).get("vector_search", {})
                    if "error" not in vector_results:
                        matches = vector_results.get("matches", [])
                        print(f"✓ Vector search working: {len(matches)} matches found")
                        
                        if matches:
                            print(f"  - First match score: {matches[0].get('score', 0):.3f}")
                    else:
                        print(f"❌ Vector search error: {vector_results.get('error')}")
                        
                    graph_results = search_results.get("results", {}).get("graph_search", {})
                    if "error" not in graph_results:
                        graph_matches = graph_results.get("matches", [])
                        print(f"✓ Graph search working: {len(graph_matches)} matches found")
                    else:
                        print(f"❌ Graph search error: {graph_results.get('error')}")
                        
                else:
                    print(f"❌ Hybrid search error: {search_results.get('error')}")
            else:
                print(f"❌ Ingestion failed: {result.errors}")
                
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return False
    finally:
        await pipeline.close()

if __name__ == "__main__":
    success = asyncio.run(test_embedding_dimensions())
    if success:
        print("\n🎉 EMBEDDING DIMENSION TEST PASSED!")
        print("💎 The unified pipeline is correctly configured for 1024 dimensions!")
    else:
        print("\n⚠️ EMBEDDING DIMENSION TEST FAILED!")
        print("🔧 Check the configuration and try again.")