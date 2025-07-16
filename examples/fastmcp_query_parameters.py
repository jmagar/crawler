"""
Example demonstrating how to access query parameters in FastMCP resources.

This example shows different approaches to handle query parameters in FastMCP resources,
since the framework doesn't natively support them.
"""

import json
from typing import Dict, Any
from fastmcp import FastMCP, Context
from src.utils.fastmcp_utils import get_query_parameters, get_pagination_params

# Create a FastMCP server instance
mcp = FastMCP(name="QueryParametersExample")

# Example 1: Basic query parameter access
@mcp.resource("users://list")
async def get_users_list(context: Context) -> str:
    """
    Get a list of users with optional filtering and pagination.
    
    Supported query parameters:
    - limit: Number of users to return (default: 10)
    - offset: Starting position (default: 0)
    - role: Filter by user role (e.g., admin, user)
    - active: Filter by active status (true/false)
    
    Example URLs:
    - users://list?limit=20&offset=10
    - users://list?role=admin&active=true
    """
    query_params = get_query_parameters()
    
    # Extract parameters with defaults
    limit = query_params.get("limit", 10)
    offset = query_params.get("offset", 0)
    role = query_params.get("role")
    active = query_params.get("active")  # Will be converted to boolean automatically
    
    # Simulate database query
    users = simulate_user_query(limit=limit, offset=offset, role=role, active=active)
    
    return json.dumps({
        "users": users,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": len(users)
        },
        "filters": {
            "role": role,
            "active": active
        }
    }, indent=2)


# Example 2: Resource template with query parameters
@mcp.resource("articles://{category}/search")
async def search_articles(category: str, context: Context) -> str:
    """
    Search articles within a specific category.
    
    Path parameters:
    - category: The article category (e.g., tech, science, sports)
    
    Query parameters:
    - q: Search query string
    - limit: Number of results (default: 15)
    - sort: Sort order (date, relevance, title)
    - published_after: ISO date string
    
    Example URLs:
    - articles://tech/search?q=python&limit=5&sort=date
    - articles://science/search?q=climate&published_after=2024-01-01
    """
    query_params = get_query_parameters()
    
    search_query = query_params.get("q", "")
    limit = query_params.get("limit", 15)
    sort = query_params.get("sort", "relevance")
    published_after = query_params.get("published_after")
    
    # Simulate article search
    articles = simulate_article_search(
        category=category,
        query=search_query,
        limit=limit,
        sort=sort,
        published_after=published_after
    )
    
    return json.dumps({
        "category": category,
        "search_query": search_query,
        "results": articles,
        "parameters": {
            "limit": limit,
            "sort": sort,
            "published_after": published_after
        }
    }, indent=2)


# Example 3: Advanced pagination with helper function
@mcp.resource("products://catalog")
async def get_product_catalog(context: Context) -> str:
    """
    Get product catalog with advanced pagination.
    
    Query parameters:
    - limit: Items per page (default: 50)
    - offset: Starting position (default: 0)
    - page: Page number (alternative to offset)
    - category: Filter by category
    - min_price: Minimum price filter
    - max_price: Maximum price filter
    - in_stock: Show only in-stock items (true/false)
    
    Example URLs:
    - products://catalog?page=2&limit=20&category=electronics
    - products://catalog?min_price=100&max_price=500&in_stock=true
    """
    query_params = get_query_parameters()
    
    # Use helper function for pagination
    pagination = get_pagination_params(query_params)
    
    # Extract filter parameters
    category = query_params.get("category")
    min_price = query_params.get("min_price")
    max_price = query_params.get("max_price")
    in_stock = query_params.get("in_stock")
    
    # Simulate product query
    products = simulate_product_query(
        limit=pagination["limit"],
        offset=pagination["offset"],
        category=category,
        min_price=min_price,
        max_price=max_price,
        in_stock=in_stock
    )
    
    return json.dumps({
        "products": products,
        "pagination": pagination,
        "filters": {
            "category": category,
            "min_price": min_price,
            "max_price": max_price,
            "in_stock": in_stock
        }
    }, indent=2)


# Helper functions for simulation
def simulate_user_query(limit: int, offset: int, role: str = None, active: bool = None) -> list:
    """Simulate a user database query."""
    # This would be replaced with actual database query
    users = [
        {"id": i, "name": f"User {i}", "role": "admin" if i % 3 == 0 else "user", "active": i % 2 == 0}
        for i in range(offset, offset + limit)
    ]
    
    # Apply filters
    if role:
        users = [u for u in users if u["role"] == role]
    if active is not None:
        users = [u for u in users if u["active"] == active]
    
    return users


def simulate_article_search(category: str, query: str, limit: int, sort: str, published_after: str = None) -> list:
    """Simulate an article search."""
    # This would be replaced with actual search logic
    articles = [
        {
            "id": i,
            "title": f"{category.title()} Article {i}: {query}",
            "category": category,
            "published": "2024-01-01",
            "relevance": 0.9 - (i * 0.1)
        }
        for i in range(1, limit + 1)
    ]
    
    return articles


def simulate_product_query(limit: int, offset: int, category: str = None, 
                          min_price: int = None, max_price: int = None, 
                          in_stock: bool = None) -> list:
    """Simulate a product catalog query."""
    # This would be replaced with actual database query
    products = [
        {
            "id": i,
            "name": f"Product {i}",
            "category": category or "general",
            "price": 50 + (i * 10),
            "in_stock": i % 2 == 0
        }
        for i in range(offset, offset + limit)
    ]
    
    # Apply filters
    if min_price:
        products = [p for p in products if p["price"] >= min_price]
    if max_price:
        products = [p for p in products if p["price"] <= max_price]
    if in_stock is not None:
        products = [p for p in products if p["in_stock"] == in_stock]
    
    return products


if __name__ == "__main__":
    # Run the server
    mcp.run(transport="sse", host="0.0.0.0", port=8080)