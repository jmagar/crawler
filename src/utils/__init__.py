"""
Utilities package for Crawl4AI MCP server.
"""

# Import Qdrant utilities
from .qdrant_utils import get_qdrant_client, setup_qdrant_collections

# Import embedding utilities
from .embedding_utils import (
    create_embeddings_batch,
    create_embedding,
    call_llm,
    generate_contextual_embedding,
    process_chunk_with_context,
    close_http_client,
)

# Import document utilities
from .document_utils import (
    add_documents_to_qdrant,
    search_documents,
    extract_code_blocks,
    generate_code_example_summary,
    add_code_examples_to_qdrant,
    update_source_info,
    extract_source_summary,
    search_code_examples
)

# Import FastMCP utilities
from .fastmcp_utils import (
    get_query_parameters,
    get_pagination_params
)

__all__ = [
    "get_qdrant_client", 
    "setup_qdrant_collections",
    "create_embeddings_batch",
    "create_embedding",
    "call_llm",
    "generate_contextual_embedding",
    "process_chunk_with_context",
    "close_http_client",
    "add_documents_to_qdrant",
    "search_documents",
    "extract_code_blocks",
    "generate_code_example_summary",
    "add_code_examples_to_qdrant",
    "update_source_info",
    "extract_source_summary",
    "search_code_examples",
    "get_query_parameters",
    "get_pagination_params"
]