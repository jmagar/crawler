"""
Query pagination utilities for Neo4j knowledge graph queries.
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple
from dataclasses import dataclass
import time

from neo4j import AsyncSession

logger = logging.getLogger(__name__)

@dataclass
class PaginationConfig:
    """Configuration for query pagination."""
    page_size: int = 100
    max_pages: Optional[int] = None
    timeout_seconds: float = 30.0

@dataclass
class QueryResult:
    """Result of a paginated query."""
    data: List[Dict[str, Any]]
    total_count: int
    page: int
    page_size: int
    has_next: bool
    execution_time: float

class PaginatedQueryExecutor:
    """Execute Neo4j queries with pagination and performance optimization."""
    
    def __init__(self, session: AsyncSession, config: PaginationConfig = None):
        """Initialize the paginated query executor.
        
        Args:
            session: Neo4j async session
            config: Pagination configuration
        """
        self.session = session
        self.config = config or PaginationConfig()
        self.performance_metrics = {}
    
    async def execute_paginated_query(
        self, 
        query: str, 
        params: Dict[str, Any] = None,
        page: int = 1
    ) -> QueryResult:
        """Execute a single paginated query.
        
        Args:
            query: Cypher query (should include SKIP and LIMIT placeholders)
            params: Query parameters
            page: Page number (1-based)
            
        Returns:
            QueryResult with data and pagination info
        """
        start_time = time.time()
        
        if params is None:
            params = {}
        
        # Calculate SKIP and LIMIT
        skip = (page - 1) * self.config.page_size
        params.update({
            'skip': skip,
            'limit': self.config.page_size
        })
        
        # Execute the query
        try:
            result = await self.session.run(query, params)
            records = await result.data()
            
            # Get total count (requires a separate count query)
            total_count = await self._get_total_count(query, params)
            
            execution_time = time.time() - start_time
            
            # Check if there's a next page
            has_next = skip + len(records) < total_count
            
            return QueryResult(
                data=records,
                total_count=total_count,
                page=page,
                page_size=self.config.page_size,
                has_next=has_next,
                execution_time=execution_time
            )
            
        except Exception as e:
            logger.error(f"Paginated query failed: {str(e)}")
            raise
    
    async def stream_all_results(
        self, 
        query: str, 
        params: Dict[str, Any] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream all results from a query, handling pagination automatically.
        
        Args:
            query: Cypher query (should include SKIP and LIMIT placeholders)
            params: Query parameters
            
        Yields:
            Individual records from the query
        """
        page = 1
        
        while True:
            # Check timeout and max pages
            if self.config.max_pages and page > self.config.max_pages:
                logger.warning(f"Reached max pages limit: {self.config.max_pages}")
                break
            
            result = await self.execute_paginated_query(query, params, page)
            
            # Yield each record
            for record in result.data:
                yield record
            
            # Check if we have more pages
            if not result.has_next:
                break
                
            page += 1
            
            # Allow other tasks to run
            await asyncio.sleep(0)
    
    async def get_page_batch(
        self, 
        query: str, 
        params: Dict[str, Any] = None,
        start_page: int = 1,
        num_pages: int = 5
    ) -> List[QueryResult]:
        """Get multiple pages in a batch for better performance.
        
        Args:
            query: Cypher query
            params: Query parameters
            start_page: Starting page number
            num_pages: Number of pages to fetch
            
        Returns:
            List of QueryResult objects
        """
        tasks = []
        
        for page in range(start_page, start_page + num_pages):
            task = self.execute_paginated_query(query, params, page)
            tasks.append(task)
        
        # Execute all queries concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and log them
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Page {start_page + i} failed: {str(result)}")
            else:
                valid_results.append(result)
        
        return valid_results
    
    async def _get_total_count(self, query: str, params: Dict[str, Any]) -> int:
        """Get total count for a query by converting it to a count query.
        
        Args:
            query: Original query
            params: Query parameters (without skip/limit)
            
        Returns:
            Total number of records
        """
        # Remove skip and limit from params for count query
        count_params = {k: v for k, v in params.items() if k not in ['skip', 'limit']}
        
        # Convert query to count query
        count_query = self._convert_to_count_query(query)
        
        try:
            result = await self.session.run(count_query, count_params)
            count_record = await result.single()
            return count_record['count'] if count_record else 0
        except Exception as e:
            logger.warning(f"Could not get total count: {str(e)}")
            return 0
    
    def _convert_to_count_query(self, query: str) -> str:
        """Convert a regular query to a count query.
        
        Args:
            query: Original Cypher query
            
        Returns:
            Count version of the query
        """
        # Simple conversion - replace RETURN clause with COUNT
        lines = query.strip().split('\n')
        
        # Find the RETURN line and replace it
        for i, line in enumerate(lines):
            line_upper = line.strip().upper()
            if line_upper.startswith('RETURN'):
                # Replace with count
                lines[i] = 'RETURN COUNT(*) as count'
                break
        
        # Remove SKIP and LIMIT clauses
        filtered_lines = []
        for line in lines:
            line_upper = line.strip().upper()
            if not (line_upper.startswith('SKIP') or line_upper.startswith('LIMIT')):
                filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)

class GraphQueryOptimizer:
    """Optimize Neo4j graph queries for better performance."""
    
    def __init__(self, session: AsyncSession):
        """Initialize the query optimizer.
        
        Args:
            session: Neo4j async session
        """
        self.session = session
        self.query_cache = {}
    
    async def create_performance_indexes(self) -> Dict[str, bool]:
        """Create indexes for better query performance.
        
        Returns:
            Dict mapping index names to success status
        """
        indexes = {
            'repository_name': 'CREATE INDEX repo_name_idx IF NOT EXISTS FOR (r:Repository) ON (r.name)',
            'file_path': 'CREATE INDEX file_path_idx IF NOT EXISTS FOR (f:File) ON (f.path)',
            'file_type': 'CREATE INDEX file_type_idx IF NOT EXISTS FOR (f:File) ON (f.type)',
            'directory_path': 'CREATE INDEX dir_path_idx IF NOT EXISTS FOR (d:Directory) ON (d.path)',
            'repository_owner': 'CREATE INDEX repo_owner_idx IF NOT EXISTS FOR (r:Repository) ON (r.owner)',
        }
        
        results = {}
        
        for index_name, query in indexes.items():
            try:
                await self.session.run(query)
                results[index_name] = True
                logger.info(f"Created index: {index_name}")
            except Exception as e:
                results[index_name] = False
                logger.error(f"Failed to create index {index_name}: {str(e)}")
        
        return results
    
    async def analyze_query_performance(self, query: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Analyze query performance using EXPLAIN.
        
        Args:
            query: Cypher query to analyze
            params: Query parameters
            
        Returns:
            Performance analysis results
        """
        explain_query = f"EXPLAIN {query}"
        
        try:
            result = await self.session.run(explain_query, params or {})
            plan = await result.data()
            
            return {
                "query": query,
                "execution_plan": plan,
                "analysis_time": time.time()
            }
        except Exception as e:
            logger.error(f"Query analysis failed: {str(e)}")
            return {"error": str(e)}
    
    async def optimize_query(self, query: str) -> str:
        """Apply basic optimizations to a Cypher query.
        
        Args:
            query: Original query
            
        Returns:
            Optimized query
        """
        # Basic optimizations
        optimized = query
        
        # Add hints for common patterns
        if 'MATCH (r:Repository)' in query and 'r.name' in query:
            optimized = optimized.replace(
                'MATCH (r:Repository)',
                'MATCH (r:Repository) USING INDEX r:Repository(name)'
            )
        
        # Add LIMIT to unbounded queries
        if 'RETURN' in optimized and 'LIMIT' not in optimized.upper():
            optimized += ' LIMIT 1000'
        
        return optimized

# Convenience functions for common paginated queries

async def get_repository_files_paginated(
    session: AsyncSession, 
    repo_name: str, 
    page: int = 1,
    file_type: Optional[str] = None
) -> QueryResult:
    """Get repository files with pagination.
    
    Args:
        session: Neo4j session
        repo_name: Repository name
        page: Page number
        file_type: Optional file type filter
        
    Returns:
        Paginated query result
    """
    executor = PaginatedQueryExecutor(session)
    
    base_query = """
    MATCH (r:Repository {name: $repo_name})-[:CONTAINS]->(f:File)
    """
    
    if file_type:
        base_query += " WHERE f.type = $file_type"
    
    base_query += """
    RETURN f.path as path, f.name as name, f.type as type, f.size as size
    ORDER BY f.path
    SKIP $skip LIMIT $limit
    """
    
    params = {"repo_name": repo_name}
    if file_type:
        params["file_type"] = file_type
    
    return await executor.execute_paginated_query(base_query, params, page)

async def search_code_content_paginated(
    session: AsyncSession, 
    search_term: str, 
    page: int = 1
) -> QueryResult:
    """Search code content with pagination.
    
    Args:
        session: Neo4j session
        search_term: Term to search for
        page: Page number
        
    Returns:
        Paginated query result
    """
    executor = PaginatedQueryExecutor(session)
    
    query = """
    MATCH (f:File)
    WHERE f.content CONTAINS $search_term
    RETURN f.path as path, f.name as name, f.repository as repository
    ORDER BY f.repository, f.path
    SKIP $skip LIMIT $limit
    """
    
    params = {"search_term": search_term}
    
    return await executor.execute_paginated_query(query, params, page)