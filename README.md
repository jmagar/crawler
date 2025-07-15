<h1 align="center">🕷️ Crawl4AI RAG MCP Server</h1>

<p align="center">
  <em>Fully Local Web Crawling and RAG Pipeline for AI Agents</em>
</p>

<p align="center">
  <strong>🔒 No Third-Party Dependencies • 🏠 Completely Local • 🛡️ Your Data Stays Yours</strong>
</p>

A powerful implementation of the [Model Context Protocol (MCP)](https://modelcontextprotocol.io) that provides AI agents with **completely local** web crawling and RAG capabilities. Zero reliance on external services - your RAG pipeline is entirely under your control.

## 🎯 Why This Matters

**You Own Your Entire RAG Pipeline.** No gatekeepers, no external APIs, no data leaving your machine:

- ✅ **Local Embeddings**: Powered by Qwen2.5:0.5B via Hugging Face Text Embeddings Inference
- ✅ **Local LLM**: Contextual embeddings via Phi3 through Ollama 
- ✅ **Local Vector Database**: Qdrant running on your hardware
- ✅ **Local Web Crawling**: Crawl4AI with full content control
- ✅ **Local Processing**: Advanced chunking and content filtering

**The only external dependency is the LLM you use to interact with the MCP server** - and even that can be local via Ollama!

## 🚀 Features

### Smart Crawling & Processing
- **Intelligent URL Detection**: Automatically handles webpages, sitemaps, and text files
- **5 Chunking Strategies**: Smart, regex, sentence-based, topic segmentation, sliding window
- **Enhanced Markdown Generation**: Content filtering with BM25 and pruning algorithms
- **Payload Optimization**: Smart batching prevents server overload (fixes 413 errors)

### Advanced RAG Capabilities  
- **Contextual Embeddings**: LLM-enhanced chunk context for better retrieval
- **Code Example Extraction**: Specialized code search for AI coding assistants
- **Cross-Encoder Reranking**: Improved result relevance
- **Metadata-Rich Chunks**: Headers, code blocks, links, and content analysis
- **Source Filtering**: Precise RAG queries by domain/source

### Knowledge Graph (Optional)
- **AI Hallucination Detection**: Validate generated code against real repositories
- **Repository Analysis**: Parse GitHub repos into Neo4j knowledge graphs
- **Code Validation**: Check imports, method calls, and class usage

## 🛠️ Tools Available

### Core Crawling Tools
1. **`crawl_single_page`**: Crawl and store a single web page
2. **`smart_crawl_url`**: Intelligently crawl entire sites (sitemaps, recursive crawling)
3. **`test_chunking_strategies`**: Compare different chunking approaches
4. **`get_available_sources`**: List all crawled domains/sources
5. **`perform_rag_query`**: Semantic search with optional source filtering

### Specialized Tools (Configurable)
6. **`search_code_examples`**: Find code snippets and implementation examples
7. **`parse_github_repository`**: Index repositories into knowledge graph
8. **`check_ai_script_hallucinations`**: Validate AI-generated code
9. **`query_knowledge_graph`**: Explore indexed repository structures

## 📋 Prerequisites

### Required Services (All Local)
- **[Qdrant](https://qdrant.tech/)**: Vector database
  ```bash
  docker run -p 6333:6333 qdrant/qdrant
  ```

- **[Hugging Face TEI](https://github.com/huggingface/text-embeddings-inference)**: Embeddings
  ```bash
  docker run -p 8080:80 --gpus all ghcr.io/huggingface/text-embeddings-inference:1.2 --model-id Qwen/Qwen2.5-0.5B --revision refs/pr/5
  ```

### Optional Services
- **[Ollama](https://ollama.ai/)**: Local LLM for contextual embeddings
  ```bash
  ollama pull phi3
  ```

- **[Neo4j](https://neo4j.com/)**: Knowledge graph functionality
  ```bash
  docker run -p 7474:7474 -p 7687:7687 neo4j
  ```

### Development Tools
- [Python 3.12+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/) or Docker

## 🚀 Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/jmagar/crawler.git
cd crawler
```

### 2. Install Dependencies
```bash
# Using uv (recommended)
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -e .

# Using pip
pip install -e .
```

### 3. Configure Environment
Create `.env` file:
```bash
# MCP Server Configuration
HOST=0.0.0.0
PORT=8051
TRANSPORT=sse

# Qdrant Configuration (Local Vector Database)
QDRANT_URL=http://localhost:6333

# Embedding Model Configuration (Local TEI Server)
EMBEDDING_MODEL_URL=http://localhost:8080/embed
EMBEDDING_DIMENSION=768

# Local LLM (Ollama) Configuration
LLM_MODEL_URL=http://localhost:11434/api/generate
LLM_MODEL_NAME=phi3

# Content Processing Configuration  
USE_CONTENT_FILTERING=true
CHUNKING_STRATEGY=smart
EMBEDDING_BATCH_SIZE=5

# RAG Strategies (Enable as needed)
USE_CONTEXTUAL_EMBEDDINGS=false
USE_AGENTIC_RAG=false
USE_RERANKING=false
USE_KNOWLEDGE_GRAPH=false

# Neo4j Configuration (Optional)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

### 4. Start the Server
```bash
uv run src/crawl4ai_mcp.py
```

## 🔧 Configuration Guide

### Chunking Strategies
- **`smart`**: Enhanced boundary detection (headers, code blocks, paragraphs)
- **`regex`**: Pattern-based splitting
- **`sentence`**: NLP sentence boundaries
- **`topic`**: TextTiling topic segmentation
- **`fixed_word`**: Fixed word count chunks
- **`sliding`**: Overlapping window chunks

### RAG Strategy Recommendations

**🏃 Fast & Simple**
```bash
USE_CONTENT_FILTERING=true
CHUNKING_STRATEGY=smart
USE_RERANKING=false
```

**🎯 High Precision**
```bash
USE_CONTEXTUAL_EMBEDDINGS=true
USE_RERANKING=true
CHUNKING_STRATEGY=smart
```

**💻 AI Coding Assistant**
```bash
USE_CONTEXTUAL_EMBEDDINGS=true
USE_AGENTIC_RAG=true
USE_RERANKING=true
CHUNKING_STRATEGY=smart
```

**🔍 Full Stack + Validation**
```bash
USE_CONTEXTUAL_EMBEDDINGS=true
USE_AGENTIC_RAG=true
USE_RERANKING=true
USE_KNOWLEDGE_GRAPH=true
```

## 🌐 MCP Client Integration

### Claude Code
```bash
claude mcp add --transport sse crawl4ai-rag http://localhost:8051/sse
```

### General MCP Clients (SSE)
```json
{
  "mcpServers": {
    "crawl4ai-rag": {
      "transport": "sse",
      "url": "http://localhost:8051/sse"
    }
  }
}
```

### Stdio Configuration
```json
{
  "mcpServers": {
    "crawl4ai-rag": {
      "command": "uv",
      "args": ["run", "src/crawl4ai_mcp.py"],
      "env": {
        "TRANSPORT": "stdio"
      }
    }
  }
}
```

## 🏗️ Architecture

### Core Components
- **`src/core/crawling.py`**: Web crawling logic with enhanced markdown generation
- **`src/core/processing.py`**: Advanced chunking strategies and content analysis
- **`src/core/server.py`**: FastMCP server with Qdrant integration
- **`src/tools/crawling_tools.py`**: MCP tool implementations
- **`src/utils.py`**: Vector operations and embedding management

### Data Flow
1. **Crawl**: Enhanced content extraction with filtering
2. **Chunk**: Multiple strategies for optimal text segmentation  
3. **Embed**: Local embedding generation via TEI
4. **Store**: Qdrant vector database with metadata
5. **Search**: Semantic similarity with optional reranking
6. **Retrieve**: Structured results with source attribution

## 🧪 Testing Your Setup

```bash
# Test single page crawling
curl -X POST http://localhost:8051/tools/crawl_single_page \
  -H "Content-Type: application/json" \
  -d '{"url": "https://docs.python.org/3/tutorial/"}'

# Test RAG query
curl -X POST http://localhost:8051/tools/perform_rag_query \
  -H "Content-Type: application/json" \
  -d '{"query": "python functions", "match_count": 5}'
```

## 🎯 Performance & Scalability

- **Payload Management**: Automatic batching prevents 413 errors
- **Concurrent Processing**: Parallel crawling and embedding generation
- **Memory Efficient**: Chunked processing for large documents
- **Configurable Limits**: Batch sizes and timeouts adjustable
- **Local Processing**: No API rate limits or external dependencies

## 🛡️ Privacy & Security

- **Zero Data Exfiltration**: All processing happens locally
- **No API Keys Required**: No external service dependencies
- **Content Control**: Full control over what gets crawled and stored
- **Local Storage**: Vector database and knowledge graphs stay on your hardware
- **Open Source**: Fully auditable codebase

## 🤝 Contributing

We welcome contributions! This project emphasizes:
- **Local-first architecture**
- **Zero external dependencies** 
- **Enhanced RAG capabilities**
- **Performance optimization**

## 📄 License

MIT License - Build what you want with it.

---

<p align="center">
  <strong>🔒 Your Data • 🏠 Your Hardware • 🛡️ Your Control</strong><br>
  <em>The way RAG should be.</em>
</p>