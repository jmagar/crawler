"""
Example usage of the performance-optimized knowledge graph system.
"""
import asyncio
import logging
from typing import List, Dict, Any

from .parse_repo_into_neo4j import DirectNeo4jExtractor
from .ai_script_analyzer import AIScriptAnalyzer
from .query_pagination import PaginatedQueryExecutor, get_repository_files_paginated
from .performance_monitor import (
    PerformanceMonitor, 
    QueryPerformanceMonitor, 
    setup_performance_monitoring,
    cleanup_performance_monitoring
)
from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)

class OptimizedKnowledgeGraphExample:
    """Example demonstrating performance-optimized knowledge graph operations."""
    
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        """Initialize the example with Neo4j connection details."""
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.driver = None
        self.extractor = None
        self.analyzer = None
        self.performance_monitor = None
    
    async def setup(self):
        """Set up the knowledge graph system with performance monitoring."""
        # Initialize performance monitoring
        self.performance_monitor = setup_performance_monitoring()
        
        # Initialize Neo4j extractor with performance optimizations
        self.extractor = DirectNeo4jExtractor(
            self.neo4j_uri, 
            self.neo4j_user, 
            self.neo4j_password,
            batch_size=150,  # Larger batch for better performance
            max_file_size=100000  # Increased file size limit
        )\
        await self.extractor.initialize()
        
        # Initialize async script analyzer
        self.analyzer = AIScriptAnalyzer(
            max_file_size=1024 * 1024,  # 1MB limit
            max_workers=8  # More workers for CPU-bound tasks
        )
        
        # Initialize Neo4j driver for direct queries
        self.driver = AsyncGraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password)
        )
        
        logger.info("Optimized knowledge graph system initialized")
    
    async def analyze_repository_with_monitoring(self, repo_url: str) -> Dict[str, Any]:
        """Analyze a repository with comprehensive performance monitoring."""
        async with self.performance_monitor.measure_operation(
            "full_repository_analysis",
            "example",
            {"repo_url": repo_url}
        ):
            # Extract repository to Neo4j
            extraction_result = await self.extractor.analyze_repository(repo_url)
            
            # Get repository name for further analysis
            repo_name = extraction_result.get("repository")
            
            if not repo_name:
                return {"error": "Failed to extract repository"}
            
            # Query repository files with pagination
            paginated_files = await self._query_repository_files_paginated(repo_name)
            
            # Analyze Python scripts asynchronously
            python_files = [
                f["path"] for f in paginated_files 
                if f.get("path", "").endswith(".py")
            ][:10]  # Limit to first 10 for demo
            
            script_analyses = []
            if python_files:
                # Convert paths to full paths (this would need actual file access)
                script_analyses = await self.analyzer.analyze_multiple_scripts(
                    python_files, 
                    max_concurrent=5
                )
            
            # Generate performance report
            performance_report = await self._generate_performance_report()
            
            return {
                "extraction_result": extraction_result,
                "files_analyzed": len(paginated_files),
                "python_scripts_analyzed": len(script_analyses),
                "performance_report": performance_report
            }
    
    async def demonstrate_pagination(self, repo_name: str) -> Dict[str, Any]:
        """Demonstrate paginated queries for large datasets."""
        async with self.driver.session() as session:
            executor = PaginatedQueryExecutor(session)
            
            # Get first page of files
            page1 = await get_repository_files_paginated(session, repo_name, page=1)
            
            # Stream all files (demonstrates memory-efficient processing)
            all_files = []
            async for file_record in executor.stream_all_results(
                """
                MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(f:File)
                RETURN f.path as path, f.name as name, f.type as type
                ORDER BY f.path
                SKIP $skip LIMIT $limit
                """,
                {"repo_name": repo_name}
            ):
                all_files.append(file_record)
                
                # Process in chunks to avoid memory issues
                if len(all_files) >= 1000:
                    await self._process_file_batch(all_files)
                    all_files = []
            
            # Process remaining files
            if all_files:
                await self._process_file_batch(all_files)
            
            return {
                "first_page_count": len(page1.data),
                "total_files_processed": len(all_files),
                "pagination_metrics": {
                    "page_size": page1.page_size,
                    "execution_time": page1.execution_time
                }
            }
    
    async def benchmark_operations(self, repo_urls: List[str]) -> Dict[str, Any]:
        """Benchmark various operations for performance analysis."""
        benchmark_results = {
            "repository_analyses": [],
            "query_performance": {},
            "system_metrics": {}
        }
        
        # Benchmark repository analyses
        for repo_url in repo_urls[:3]:  # Limit for demo
            async with self.performance_monitor.measure_operation(
                f"benchmark_analysis",
                "benchmark",
                {"repo_url": repo_url}
            ):
                result = await self.extractor.analyze_repository(repo_url)
                benchmark_results["repository_analyses"].append({
                    "repo_url": repo_url,
                    "result": result,
                    "performance_metrics": self.extractor.get_performance_metrics()
                })
        
        # Benchmark query operations
        async with self.driver.session() as session:
            query_monitor = QueryPerformanceMonitor(self.performance_monitor)
            
            # Test different query patterns
            queries = [
                ("count_files", "MATCH (f:File) RETURN COUNT(f) as count"),
                ("count_repositories", "MATCH (r:Repository) RETURN COUNT(r) as count"),
                ("files_by_type", "MATCH (f:File) RETURN f.type, COUNT(f) as count GROUP BY f.type")
            ]
            
            for query_name, query in queries:
                async with query_monitor.monitor_query(query_name, query):
                    result = await session.run(query)
                    await result.data()
            
            benchmark_results["query_performance"] = query_monitor.get_query_performance_report()
        
        # Get system metrics
        benchmark_results["system_metrics"] = self.performance_monitor.get_system_metrics_summary()
        
        return benchmark_results
    
    async def _query_repository_files_paginated(self, repo_name: str) -> List[Dict[str, Any]]:
        """Query repository files using pagination."""
        async with self.driver.session() as session:
            result = await get_repository_files_paginated(session, repo_name, page=1)
            return result.data
    
    async def _process_file_batch(self, files: List[Dict[str, Any]]):
        \"\"\"Process a batch of files (placeholder for actual processing).\"\"\"
        # This would contain actual file processing logic
        await asyncio.sleep(0.1)  # Simulate processing time
        logger.debug(f\"Processed batch of {len(files)} files\")\n    \n    async def _generate_performance_report(self) -> Dict[str, Any]:\n        \"\"\"Generate a comprehensive performance report.\"\"\"\n        return {\n            \"metrics_summary\": self.performance_monitor.get_all_metrics_summary(),\n            \"system_metrics\": self.performance_monitor.get_system_metrics_summary(),\n            \"extractor_metrics\": self.extractor.get_performance_metrics() if self.extractor else {},\n            \"analyzer_metrics\": self.analyzer.get_performance_metrics() if self.analyzer else {}\n        }\n    \n    async def cleanup(self):\n        \"\"\"Clean up resources.\"\"\"\n        if self.extractor:\n            await self.extractor.close()\n        \n        if self.analyzer:\n            await self.analyzer.cleanup()\n        \n        if self.driver:\n            await self.driver.close()\n        \n        await cleanup_performance_monitoring()\n        \n        logger.info(\"Knowledge graph system cleaned up\")\n\nasync def run_performance_example():\n    \"\"\"Run a complete performance optimization example.\"\"\"\n    # Example configuration\n    neo4j_config = {\n        \"neo4j_uri\": \"bolt://localhost:7687\",\n        \"neo4j_user\": \"neo4j\",\n        \"neo4j_password\": \"password\"\n    }\n    \n    example_repos = [\n        \"https://github.com/python/cpython\",\n        \"https://github.com/django/django\",\n        \"https://github.com/pallets/flask\"\n    ]\n    \n    kg_example = OptimizedKnowledgeGraphExample(**neo4j_config)\n    \n    try:\n        # Set up the system\n        await kg_example.setup()\n        \n        # Analyze a repository with monitoring\n        logger.info(\"Starting repository analysis with performance monitoring\")\n        analysis_result = await kg_example.analyze_repository_with_monitoring(example_repos[0])\n        print(f\"Analysis completed: {analysis_result['files_analyzed']} files processed\")\n        \n        # Demonstrate pagination\n        repo_name = analysis_result[\"extraction_result\"].get(\"repository\")\n        if repo_name:\n            logger.info(\"Demonstrating pagination capabilities\")\n            pagination_result = await kg_example.demonstrate_pagination(repo_name)\n            print(f\"Pagination demo: {pagination_result['total_files_processed']} files processed\")\n        \n        # Run benchmarks\n        logger.info(\"Running performance benchmarks\")\n        benchmark_results = await kg_example.benchmark_operations(example_repos)\n        print(f\"Benchmarks completed: {len(benchmark_results['repository_analyses'])} repositories analyzed\")\n        \n        # Export performance metrics\n        await kg_example.performance_monitor.export_metrics(\n            \"performance_metrics.json\",\n            format=\"json\"\n        )\n        print(\"Performance metrics exported to performance_metrics.json\")\n        \n    except Exception as e:\n        logger.error(f\"Example failed: {str(e)}\")\n        raise\n    finally:\n        await kg_example.cleanup()\n\nif __name__ == \"__main__\":\n    # Configure logging\n    logging.basicConfig(\n        level=logging.INFO,\n        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'\n    )\n    \n    # Run the example\n    asyncio.run(run_performance_example())