"""
Knowledge Graphs module for Crawl4AI MCP server.

This module provides knowledge graph functionality including:
- Repository analysis and extraction to Neo4j
- AI script validation against knowledge graphs
- Hallucination detection and reporting
- Graph-enhanced search and RAG capabilities
- Performance monitoring and optimization
- Query pagination and optimization

Components:
- DirectNeo4jExtractor: Parse GitHub repositories into Neo4j graphs
- KnowledgeGraphValidator: Validate AI scripts against graph knowledge
- AIScriptAnalyzer: Analyze Python scripts for structural patterns
- HallucinationReporter: Generate comprehensive validation reports
- PaginatedQueryExecutor: Handle large query results with pagination
- GraphQueryOptimizer: Optimize Neo4j queries for better performance
- PerformanceMonitor: Monitor and collect performance metrics
- QueryPerformanceMonitor: Specialized monitoring for Neo4j queries

Performance Features:
- Streaming file processing for large repositories
- Batch processing for Neo4j operations
- Async file I/O for better concurrency
- Query result pagination
- Real-time performance monitoring
- Memory usage optimization
"""

from .parse_repo_into_neo4j import DirectNeo4jExtractor
from .knowledge_graph_validator import KnowledgeGraphValidator
from .ai_script_analyzer import AIScriptAnalyzer
from .hallucination_reporter import HallucinationReporter
from .query_pagination import PaginatedQueryExecutor, GraphQueryOptimizer
from .performance_monitor import PerformanceMonitor, QueryPerformanceMonitor, get_performance_monitor

__all__ = [
    "AIScriptAnalyzer",
    "DirectNeo4jExtractor",
    "GraphQueryOptimizer",
    "HallucinationReporter",
    "KnowledgeGraphValidator", 
    "PaginatedQueryExecutor",
    "PerformanceMonitor",
    "QueryPerformanceMonitor",
    "get_performance_monitor",
]

__version__ = "1.0.0"