# Crawl4AI RAG MCP Server - Development Guide

This is a Python-based MCP server for web crawling and RAG capabilities with vector storage in Qdrant and optional Neo4j knowledge graphs.

## Project Structure
- `src/core/` - Core crawling, processing, and server logic
- `src/tools/` - MCP tool implementations (crawling and knowledge graph tools)
- `src/utils/` - Utility modules for embeddings, Qdrant, and document processing
- `knowledge_graphs/` - Neo4j integration and analysis tools
- `unified_ingestion/` - Data models and pipeline for unified processing

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate    # Windows

# Install dependencies
uv pip install -e .
```

### Running the Server
```bash
# Start MCP server
uv run src/crawl4ai_mcp.py

# Development mode with file watching
./dev.sh
```

### Testing
```bash
# Run specific test files
python test_unified_dimensions.py
python test_unified_ingestion.py
python test_cancellation.py

# Test chunking strategies
python -m src.core.processing

# Test hybrid search
python demo_hybrid_search.py
python demo_working_hybrid.py
```

### Docker Services
```bash
# Start all services
docker-compose up -d

# Hardware-optimized version (i7-13700k)
docker-compose -f docker-compose.i7-13700k.yaml up -d

# Individual services
docker run -p 6333:6333 qdrant/qdrant  # Vector database
docker run -p 8080:80 --gpus all ghcr.io/huggingface/text-embeddings-inference:1.2 --model-id Qwen/Qwen2.5-0.5B --revision refs/pr/5  # Embeddings
```

### Code Quality
```bash
# No linting/formatting tools configured yet - run tests manually
python -m pytest  # If pytest is available
python -m unittest discover  # Standard library testing
```

## Key Dependencies
- `fastmcp>=2.10.5` - MCP server framework
- `crawl4ai>=0.7.0` - Web crawling
- `qdrant-client>=1.14.3` - Vector database
- `sentence-transformers>=5.0.0` - Embeddings
- `neo4j>=5.28.1` - Knowledge graphs (optional)
- `gitpython>=3.1.44` - Git repository analysis

## Configuration
Environment variables in `.env`:
- `QDRANT_URL=http://localhost:6333` - Vector database
- `EMBEDDING_MODEL_URL=http://localhost:8080/embed` - Local embeddings
- `EMBEDDING_DIMENSION=768` - Embedding dimensions
- `CHUNKING_STRATEGY=smart` - Text chunking method
- `USE_KNOWLEDGE_GRAPH=false` - Enable Neo4j integration

## MCP Tools Available
### Core Crawling Tools
- `scrape` - Crawl and store a single web page
- `crawl` - Intelligently crawl entire sites (sitemaps, recursive crawling)
- `crawl_dir` - Crawl local directories and ingest files into the pipeline
- `available_sources` - List all crawled domains/sources
- `rag_query` - Semantic search with optional source filtering
- `search_code_examples` - Find code snippets and implementation examples

### Knowledge Graph Tools (when USE_KNOWLEDGE_GRAPH=true)
- `crawl_repo` - Parse GitHub repository into Neo4j knowledge graph
- `you_trippin` - Validate AI-generated code against real repositories
- `graph_query` - Explore indexed repository structures

## MCP Resources Available
- `sources://overview` - Overview of all crawled sources with metadata
- `sources://urls` - List of all crawled URLs with filtering support
- `sources://stats` - Detailed statistics about crawled content

## Architecture Notes
- Local-first design with no external API dependencies
- Supports multiple chunking strategies in `src/core/processing.py`
- Vector storage via Qdrant with metadata-rich chunks
- Optional Neo4j knowledge graph for repository analysis
- MCP tools expose crawling and RAG capabilities to AI agents
- Enhanced cancellation handling and progress reporting throughout

## Directory Crawling with crawl_dir

The `crawl_dir` tool allows you to crawl local directories and ingest files into the pipeline:

### Usage
```bash
crawl_dir(
    directory_path="/path/to/directory",
    max_files=500,                    # Maximum files to process
    max_file_size=1048576,           # 1MB file size limit
    exclude_patterns=["*.log"],       # Patterns to exclude
    include_patterns=None,            # Override text file detection
    chunk_size=5000                   # Chunk size for processing
)
```

### Features
- **Smart File Detection**: Automatically detects text files by extension and MIME type
- **Security**: Prevents access to sensitive system directories
- **Configurable Limits**: Control file count, size, and processing parameters
- **Pattern Matching**: Include/exclude files using custom patterns
- **Full Pipeline Integration**: 
  - Generates embeddings using the same pipeline as web crawling
  - Stores in Qdrant vector database with rich metadata
  - Optionally stores in Neo4j knowledge graph
  - Supports code example extraction and indexing

### Supported File Types
- Source code: `.py`, `.js`, `.ts`, `.java`, `.c`, `.cpp`, `.go`, `.rs`, etc.
- Documentation: `.md`, `.rst`, `.txt`
- Configuration: `.json`, `.yaml`, `.toml`, `.ini`
- Web files: `.html`, `.css`, `.xml`
- Scripts: `.sh`, `.bash`, `.ps1`

### Default Exclusions
- Version control: `.git`, `.svn`, `.hg`
- Dependencies: `node_modules`, `__pycache__`, `.venv`
- Build artifacts: `dist`, `build`, `target`
- System files: `.DS_Store`, `Thumbs.db`

### Security Features
- Path validation and normalization
- Restricted access to system directories
- File size and count limits
- Permission checking