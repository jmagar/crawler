#!/usr/bin/env python3
"""
Test script for optimized embedding functions.
Tests both single embedding and batch processing.
"""
import asyncio
import time
import sys
import os

# Add src to path
sys.path.append('src')

from utils.embedding_utils import create_embedding, create_embeddings_batch, close_http_client

async def test_single_embedding():
    """Test single embedding creation."""
    print("Testing single embedding...")
    start_time = time.time()
    
    embedding = await create_embedding("This is a test sentence for embedding.")
    
    elapsed = time.time() - start_time
    print(f"Single embedding completed in {elapsed:.2f}s")
    print(f"Embedding dimension: {len(embedding)}")
    print(f"First 5 values: {embedding[:5]}")
    return embedding

async def test_batch_embeddings():
    """Test batch embedding creation with various sizes."""
    test_texts = [
        f"This is test document number {i} with some content to embed."
        for i in range(100)
    ]
    
    print(f"\nTesting batch embeddings with {len(test_texts)} texts...")
    start_time = time.time()
    
    embeddings = await create_embeddings_batch(test_texts)
    
    elapsed = time.time() - start_time
    print(f"Batch embeddings completed in {elapsed:.2f}s")
    print(f"Total embeddings: {len(embeddings)}")
    print(f"Throughput: {len(embeddings)/elapsed:.1f} embeddings/second")
    
    return embeddings

async def test_large_batch():
    """Test with a larger batch to stress test concurrent processing."""
    large_texts = [
        f"Document {i}: " + "This is a longer piece of text that contains more content. " * 10
        for i in range(500)
    ]
    
    print(f"\nTesting large batch with {len(large_texts)} texts...")
    start_time = time.time()
    
    embeddings = await create_embeddings_batch(large_texts)
    
    elapsed = time.time() - start_time
    print(f"Large batch completed in {elapsed:.2f}s")
    print(f"Total embeddings: {len(embeddings)}")
    print(f"Throughput: {len(embeddings)/elapsed:.1f} embeddings/second")
    
    return embeddings

async def main():
    """Run all tests."""
    print("Starting embedding optimization tests...")
    print(f"TEI Server URL: {os.getenv('EMBEDDING_MODEL_URL', 'http://localhost:8080/embed')}")
    
    try:
        # Test single embedding
        single_embedding = await test_single_embedding()
        
        # Test batch processing
        batch_embeddings = await test_batch_embeddings()
        
        # Test large batch for stress testing
        large_embeddings = await test_large_batch()
        
        print("\n✅ All tests completed successfully!")
        print("\nOptimization summary:")
        print("- Connection pooling enabled")
        print("- Concurrent batch processing")
        print("- Token-based payload estimation") 
        print("- Increased batch size (5 → 64)")
        print("- HTTP/2 and keepalive connections")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up HTTP client
        await close_http_client()
        print("\n🔧 HTTP client closed")

if __name__ == "__main__":
    asyncio.run(main())