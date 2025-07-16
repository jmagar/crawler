"""
Knowledge Graphs module for Crawl4AI MCP server.

This module provides knowledge graph functionality including:
- Repository analysis and extraction to Neo4j
- AI script validation against knowledge graphs
- Hallucination detection and reporting
- Graph-enhanced search and RAG capabilities

Components:
- DirectNeo4jExtractor: Parse GitHub repositories into Neo4j graphs
- KnowledgeGraphValidator: Validate AI scripts against graph knowledge
- AIScriptAnalyzer: Analyze Python scripts for structural patterns
- HallucinationReporter: Generate comprehensive validation reports
"""

from .parse_repo_into_neo4j import DirectNeo4jExtractor
from .knowledge_graph_validator import KnowledgeGraphValidator
from .ai_script_analyzer import AIScriptAnalyzer
from .hallucination_reporter import HallucinationReporter

__all__ = [
    "DirectNeo4jExtractor",
    "KnowledgeGraphValidator", 
    "AIScriptAnalyzer",
    "HallucinationReporter"
]

__version__ = "1.0.0"