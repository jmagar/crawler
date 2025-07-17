#!/usr/bin/env python3
"""
Demonstrate how hybrid search combines Neo4j + Qdrant for superior results.
"""
import asyncio
import logging
from unified_ingestion import UnifiedIngestionPipeline, IngestionConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def demo_hybrid_search_superiority():
    """Show how combining both databases creates better results than either alone."""
    
    print("🔬 HYBRID SEARCH DEMONSTRATION")
    print("=" * 60)
    print("Showing how Neo4j + Qdrant together > either database alone")
    print()
    
    # Create pipeline
    config = IngestionConfig(enable_performance_monitoring=True)
    pipeline = UnifiedIngestionPipeline(config)
    
    try:
        await pipeline.initialize()
        
        # Demo search queries that show the power of hybrid approach
        demo_queries = [
            {
                "query": "error handling patterns",
                "explanation": "Find both structural error handling AND semantically similar concepts"
            },
            {
                "query": "authentication security", 
                "explanation": "Locate auth files AND content about security concepts"
            },
            {
                "query": "async functions",
                "explanation": "Find async code files AND semantically related concurrency content"
            }
        ]
        
        for demo in demo_queries:
            query = demo["query"]
            explanation = demo["explanation"]
            
            print(f"🔍 QUERY: '{query}'")
            print(f"💡 Goal: {explanation}")
            print("-" * 50)
            
            # Get hybrid results
            results = await pipeline.search_hybrid(query, limit=5)
            
            if "error" not in results:
                graph_results = results.get("results", {}).get("graph_search", {})
                vector_results = results.get("results", {}).get("vector_search", {})
                
                # Show Neo4j results (structural/exact matches)
                print("🏗️  NEO4J GRAPH RESULTS (Structural/Exact):")
                if "error" not in graph_results:
                    matches = graph_results.get("matches", [])
                    if matches:
                        for i, match in enumerate(matches[:3], 1):
                            node_types = ", ".join(match.get("types", []))
                            node_props = match.get("node", {})
                            name = node_props.get("name", node_props.get("path", "Unknown"))
                            print(f"   {i}. [{node_types}] {name}")
                            
                            # Show key properties
                            for key in ["extension", "size", "url", "domain"]:
                                if key in node_props:
                                    print(f"      {key}: {node_props[key]}")
                    else:
                        print("   No structural matches found")
                else:
                    print(f"   Error: {graph_results.get('error', 'Unknown')}")
                
                print()
                
                # Show Qdrant results (semantic/fuzzy matches)
                print("🧠 QDRANT VECTOR RESULTS (Semantic/Contextual):")
                if "error" not in vector_results:
                    matches = vector_results.get("matches", [])
                    if matches:
                        for i, match in enumerate(matches[:3], 1):
                            score = match.get("score", 0)
                            content = match.get("content", "")[:200]
                            metadata = match.get("metadata", {})
                            source = metadata.get("source_path", metadata.get("url", "Unknown"))
                            
                            print(f"   {i}. Score: {score:.3f} | Source: {source}")
                            print(f"      Content: {content}...")
                            print()
                    else:
                        print("   No semantic matches found")
                else:
                    print(f"   Error: {vector_results.get('error', 'Unknown')}")
                
                # Show the hybrid advantage
                graph_count = graph_results.get("count", 0) if "error" not in graph_results else 0
                vector_count = vector_results.get("count", 0) if "error" not in vector_results else 0
                
                print("🎯 HYBRID ADVANTAGE:")
                if graph_count > 0 and vector_count > 0:
                    print("   ✨ BEST OF BOTH WORLDS!")
                    print("   📊 Structural matches give you EXACT file/code locations")
                    print("   🧠 Semantic matches find RELATED concepts and context")
                    print("   💎 Together = Complete understanding of your codebase")
                elif graph_count > 0:
                    print("   📊 Found structural matches - you know WHERE things are")
                    print("   🔍 Semantic search would add CONTEXT and RELATED concepts")
                elif vector_count > 0:
                    print("   🧠 Found semantic matches - you understand CONCEPTS")
                    print("   🔗 Graph search would add STRUCTURE and RELATIONSHIPS")
                else:
                    print("   🚀 No matches yet - ingest more content to see the magic!")
                
                print("=" * 60)
                print()
        
        # Show specific hybrid use cases
        print("💡 REAL-WORLD HYBRID USE CASES:")
        print("=" * 60)
        
        use_cases = [
            {
                "scenario": "🐛 Bug Investigation",
                "graph_finds": "Files that import 'logging' module",
                "vector_finds": "Content about error handling, debugging, troubleshooting",
                "combined_power": "Complete picture of logging infrastructure + debugging techniques"
            },
            {
                "scenario": "🔒 Security Audit", 
                "graph_finds": "Files with 'auth', 'security' in path/name",
                "vector_finds": "Content about authentication, authorization, encryption",
                "combined_power": "Security-related files + security best practices and patterns"
            },
            {
                "scenario": "📚 API Documentation",
                "graph_finds": "Files ending in .py with 'api' in name",
                "vector_finds": "Content explaining API usage, examples, tutorials",
                "combined_power": "API implementation code + usage documentation and examples"
            },
            {
                "scenario": "⚡ Performance Optimization",
                "graph_finds": "Large files, specific function calls",
                "vector_finds": "Content about optimization, performance, bottlenecks",
                "combined_power": "Potential bottleneck locations + optimization strategies"
            }
        ]
        
        for case in use_cases:
            print(f"{case['scenario']}:")
            print(f"   📊 Neo4j finds: {case['graph_finds']}")
            print(f"   🧠 Qdrant finds: {case['vector_finds']}")
            print(f"   💎 Combined: {case['combined_power']}")
            print()
        
        print("🚀 WHY HYBRID SEARCH IS SUPERIOR:")
        print("=" * 60)
        print("🎯 PRECISION + DISCOVERY")
        print("   Neo4j: 'Show me exactly where X is' (structural precision)")
        print("   Qdrant: 'Show me things related to X' (semantic discovery)")
        print("   Hybrid: 'Show me X AND everything related to X' (complete intelligence)")
        print()
        print("🔄 COMPLEMENTARY STRENGTHS")
        print("   Neo4j: Perfect for exact matches, relationships, hierarchy")
        print("   Qdrant: Perfect for fuzzy matches, concepts, context")
        print("   Hybrid: Covers both exact needs AND exploratory discovery")
        print()
        print("📈 BETTER RELEVANCE")
        print("   Single DB: Limited perspective on your query")
        print("   Hybrid: Multiple perspectives = richer, more complete results")
        print("   Result: Higher chance of finding exactly what you need")
        
        return True
        
    except Exception as e:
        print(f"❌ Demo failed: {str(e)}")
        return False
    finally:
        await pipeline.close()

async def demo_result_fusion_strategies():
    """Show different ways to combine/rank results from both databases."""
    
    print("\n🔀 RESULT FUSION STRATEGIES")
    print("=" * 60)
    print("Different ways to combine Neo4j + Qdrant results:")
    print()
    
    strategies = [
        {
            "name": "📊 Structural Priority",
            "description": "Show Neo4j results first (exact matches), then Qdrant (related content)",
            "use_case": "When you need precise file/code locations first"
        },
        {
            "name": "🧠 Semantic Priority", 
            "description": "Show Qdrant results first (relevance score), then Neo4j (structure)",
            "use_case": "When exploring concepts and need related content"
        },
        {
            "name": "🎯 Interleaved Ranking",
            "description": "Mix results based on confidence/relevance scores from both DBs",
            "use_case": "When you want the most relevant results regardless of source"
        },
        {
            "name": "🔗 Relationship Enhancement",
            "description": "Use Neo4j to find related files for each Qdrant semantic match",
            "use_case": "When you want context around semantically relevant content"
        },
        {
            "name": "🎨 Categorized Display",
            "description": "Group results: 'Exact Matches' vs 'Related Content' vs 'Similar Concepts'",
            "use_case": "When users need to understand the type of match"
        }
    ]
    
    for strategy in strategies:
        print(f"{strategy['name']}")
        print(f"   Method: {strategy['description']}")
        print(f"   Best for: {strategy['use_case']}")
        print()
    
    print("💎 THE MAGIC: CROSS-DATABASE ENRICHMENT")
    print("=" * 60)
    print("1️⃣ Find semantic matches in Qdrant")
    print("2️⃣ Use those matches to find related files in Neo4j")
    print("3️⃣ Use Neo4j relationships to find connected components")
    print("4️⃣ Use connected components to find more semantic content")
    print("5️⃣ Create a web of both structural AND semantic relevance!")

if __name__ == "__main__":
    async def main():
        success1 = await demo_hybrid_search_superiority()
        await demo_result_fusion_strategies()
        
        if success1:
            print("\n🎉 HYBRID SEARCH DEMO COMPLETED!")
            print("💡 You now have BOTH precision AND discovery in your search!")
        else:
            print("\n⚠️ Demo had issues, but the concept is solid!")
    
    asyncio.run(main())