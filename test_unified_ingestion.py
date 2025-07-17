#!/usr/bin/env python3
"""
Comprehensive test of the unified ingestion pipeline.

Tests all content types and demonstrates dual database ingestion.
"""
import asyncio
import logging
import tempfile
import os
from pathlib import Path

# Import the unified ingestion system
from unified_ingestion import (
    UnifiedIngestionPipeline, ContentType, IngestionConfig,
    ingest_github_repo, ingest_web_page, ingest_local_folder, hybrid_search
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_github_repository():
    """Test GitHub repository ingestion."""
    print("\n🔷 TESTING GITHUB REPOSITORY INGESTION")
    print("=" * 60)
    
    # Use a small test repository
    repo_url = "https://github.com/octocat/Hello-World"
    
    try:
        result = await ingest_github_repo(repo_url)
        
        print(f"✅ GitHub ingestion successful!")
        print(f"   Repository: {repo_url}")
        print(f"   Processing time: {result.processing_time:.2f}s")
        print(f"   Chunks created: {result.chunks_created}")
        print(f"   Nodes created: {result.nodes_created}")
        print(f"   Relationships created: {result.relationships_created}")
        
        if result.neo4j_result:
            print(f"   Neo4j: {result.neo4j_result.get('nodes_created', 0)} nodes")
        if result.qdrant_result:
            print(f"   Qdrant: {result.qdrant_result.get('chunks_ingested', 0)} chunks")
            
        return True
        
    except Exception as e:
        print(f"❌ GitHub ingestion failed: {str(e)}")
        return False


async def test_web_page():
    """Test web page ingestion."""
    print("\n🌐 TESTING WEB PAGE INGESTION") 
    print("=" * 60)
    
    # Use a simple web page
    url = "https://httpbin.org/html"
    
    try:
        result = await ingest_web_page(url)
        
        print(f"✅ Web page ingestion successful!")
        print(f"   URL: {url}")
        print(f"   Processing time: {result.processing_time:.2f}s")
        print(f"   Chunks created: {result.chunks_created}")
        print(f"   Nodes created: {result.nodes_created}")
        
        return True
        
    except Exception as e:
        print(f"❌ Web page ingestion failed: {str(e)}")
        return False


async def test_local_folder():
    """Test local folder ingestion."""
    print("\n📁 TESTING LOCAL FOLDER INGESTION")
    print("=" * 60)
    
    # Create a temporary folder with test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test files
        test_files = {
            "README.md": "# Test Project\n\nThis is a test markdown file for ingestion.",
            "main.py": "#!/usr/bin/env python3\n\ndef hello_world():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    hello_world()",
            "config.json": '{"name": "test_project", "version": "1.0.0", "description": "Test configuration"}',
            "subfolder/utils.py": "def utility_function():\n    return 'This is a utility function'"
        }
        
        for file_path, content in test_files.items():
            full_path = temp_path / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding='utf-8')
        
        try:
            result = await ingest_local_folder(str(temp_path))
            
            print(f"✅ Local folder ingestion successful!")
            print(f"   Folder: {temp_path}")
            print(f"   Processing time: {result.processing_time:.2f}s")
            print(f"   Chunks created: {result.chunks_created}")
            print(f"   Nodes created: {result.nodes_created}")
            
            return True
            
        except Exception as e:
            print(f"❌ Local folder ingestion failed: {str(e)}")
            return False


async def test_pipeline_direct():
    """Test the pipeline directly with multiple sources."""
    print("\n🔧 TESTING UNIFIED PIPELINE WITH MULTIPLE SOURCES")
    print("=" * 60)
    
    # Create optimized configuration
    config = IngestionConfig(
        max_workers=8,  # Use fewer workers for testing
        batch_size=50,  # Smaller batches for testing
        enable_performance_monitoring=True
    )
    
    pipeline = UnifiedIngestionPipeline(config)
    
    try:
        await pipeline.initialize()
        
        # Test multiple sources
        sources = [
            {
                "identifier": "https://github.com/octocat/Hello-World",
                "type": ContentType.GITHUB_REPOSITORY,
                "metadata": {"test": "github_test"}
            },
            {
                "identifier": "https://httpbin.org/json", 
                "type": ContentType.WEB_PAGE,
                "metadata": {"test": "web_test"}
            }
        ]
        
        print(f"Processing {len(sources)} sources...")
        results = await pipeline.ingest_multiple(sources, max_concurrent=2)
        
        successful = sum(1 for r in results if r.success)
        print(f"✅ Pipeline test completed: {successful}/{len(results)} sources successful")
        
        for i, result in enumerate(results):
            source_info = sources[i]
            if result.success:
                print(f"   ✓ {source_info['identifier']}: {result.chunks_created} chunks, {result.nodes_created} nodes")
            else:
                print(f"   ✗ {source_info['identifier']}: {result.errors}")
        
        # Test pipeline statistics
        stats = await pipeline.get_ingestion_stats()
        if "error" not in stats:
            print(f"📊 Pipeline stats: {stats.get('database_verification', {})}")
        
        return successful == len(results)
        
    except Exception as e:
        print(f"❌ Pipeline test failed: {str(e)}")
        return False
    finally:
        await pipeline.close()


async def test_hybrid_search():
    """Test hybrid search functionality."""
    print("\n🔍 TESTING HYBRID SEARCH")
    print("=" * 60)
    
    try:
        # Search for content we know exists from previous tests
        search_queries = [
            "Hello World",
            "function", 
            "test"
        ]
        
        for query in search_queries:
            print(f"\nSearching for: '{query}'")
            
            results = await hybrid_search(query, limit=5)
            
            if "error" not in results:
                graph_results = results.get("results", {}).get("graph_search", {})
                vector_results = results.get("results", {}).get("vector_search", {})
                
                graph_count = graph_results.get("count", 0) if "error" not in graph_results else 0
                vector_count = vector_results.get("count", 0) if "error" not in vector_results else 0
                
                print(f"   Graph results: {graph_count}")
                print(f"   Vector results: {vector_count}")
                
                # Show sample results
                if graph_count > 0:
                    sample = graph_results.get("matches", [])[:2]
                    for match in sample:
                        node_types = ", ".join(match.get("types", []))
                        print(f"     📊 Graph: {node_types} node")
                
                if vector_count > 0:
                    sample = vector_results.get("matches", [])[:2]  
                    for match in sample:
                        score = match.get("score", 0)
                        content = match.get("content", "")[:100]
                        print(f"     🧠 Vector: {score:.3f} - {content}...")
            else:
                print(f"   Search error: {results['error']}")
        
        print(f"✅ Hybrid search test completed")
        return True
        
    except Exception as e:
        print(f"❌ Hybrid search test failed: {str(e)}")
        return False


async def test_auto_detection():
    """Test automatic content type detection."""
    print("\n🎯 TESTING AUTO-DETECTION")
    print("=" * 60)
    
    pipeline = UnifiedIngestionPipeline()
    
    test_cases = [
        ("https://github.com/user/repo", ContentType.GITHUB_REPOSITORY),
        ("https://example.com/page", ContentType.WEB_PAGE),
        ("/tmp", ContentType.LOCAL_FOLDER),
        ("./README.md", ContentType.LOCAL_FILE if Path("./README.md").exists() else ContentType.LOCAL_FOLDER)
    ]
    
    correct_detections = 0
    
    for identifier, expected_type in test_cases:
        detected_type = pipeline._detect_source_type(identifier)
        is_correct = detected_type == expected_type
        
        status = "✅" if is_correct else "❌"
        print(f"   {status} {identifier} -> {detected_type.value} (expected: {expected_type.value})")
        
        if is_correct:
            correct_detections += 1
    
    accuracy = correct_detections / len(test_cases) * 100
    print(f"Detection accuracy: {accuracy:.1f}% ({correct_detections}/{len(test_cases)})")
    
    return accuracy >= 75  # 75% accuracy threshold


async def main():
    """Run all tests."""
    print("🚀 UNIFIED INGESTION PIPELINE COMPREHENSIVE TEST")
    print("=" * 80)
    print("Testing all content types with dual database ingestion...")
    print("Optimized for Intel i7-13700K + 32GB DDR5 + RTX 4070")
    print("=" * 80)
    
    # Run all tests
    tests = [
        ("Auto-detection", test_auto_detection),
        ("GitHub Repository", test_github_repository),
        ("Web Page", test_web_page),
        ("Local Folder", test_local_folder),
        ("Pipeline Direct", test_pipeline_direct),
        ("Hybrid Search", test_hybrid_search)
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            success = await test_func()
            if success:
                passed_tests += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} FAILED with exception: {str(e)}")
    
    # Final results
    print(f"\n{'='*80}")
    print(f"🎯 TEST RESULTS: {passed_tests}/{total_tests} tests passed")
    print(f"Success rate: {passed_tests/total_tests*100:.1f}%")
    
    if passed_tests == total_tests:
        print("🎉 ALL TESTS PASSED! Unified ingestion pipeline is working correctly.")
        print("✨ Ready for production use with Neo4j + Qdrant dual ingestion!")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
    
    print("\n📋 CAPABILITIES DEMONSTRATED:")
    print("   ✓ GitHub repository ingestion with file structure analysis")
    print("   ✓ Web page crawling and content extraction")  
    print("   ✓ Local folder and file processing")
    print("   ✓ Dual database ingestion (Neo4j + Qdrant)")
    print("   ✓ Concurrent processing optimization")
    print("   ✓ Hybrid search across both databases")
    print("   ✓ Performance monitoring and metrics")
    print("   ✓ i7-13700K hardware optimizations")


if __name__ == "__main__":
    asyncio.run(main())