#!/bin/bash

# Development setup and server startup script
# This script sets up the development environment and starts the server with hot reload

set -e  # Exit on any error

echo "🚀 Crawl4AI MCP Development Setup"
echo "================================="

# Check if .env exists, if not copy from .env.example
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "📋 Copying .env.example to .env..."
        cp .env.example .env
        echo "✅ .env file created"
    else
        echo "⚠️  No .env.example found, creating basic .env..."
        cat > .env << EOF
# Crawl4AI MCP Server Configuration
HOST=0.0.0.0
PORT=8051

# Qdrant Configuration
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# Embedding Model Configuration
EMBEDDING_MODEL_URL=http://localhost:8080/embed
EMBEDDING_DIMENSION=768

# Optional LLM Configuration
LLM_MODEL_URL=
LLM_MODEL_NAME=phi3

# Feature Flags
USE_RERANKING=false
USE_CONTEXTUAL_EMBEDDINGS=false
USE_AGENTIC_RAG=false
USE_KNOWLEDGE_GRAPH=false

# Neo4j Configuration (if using knowledge graph)
NEO4J_URI=
NEO4J_USER=
NEO4J_PASSWORD=

# Logging
FASTMCP_LOG_LEVEL=INFO
EOF
        echo "✅ Basic .env file created"
    fi
    echo ""
    echo "🔧 Please configure your .env file with the appropriate values:"
    echo "   • Qdrant URL and API key"
    echo "   • Embedding model URL"
    echo "   • Optional LLM configuration"
    echo "   • Feature flags as needed"
    echo ""
fi

# Check if virtual environment exists and has dependencies
if [ ! -d ".venv" ] || [ ! -f ".venv/pyvenv.cfg" ]; then
    echo "📦 Setting up virtual environment and installing dependencies..."
    uv sync --group dev
    echo "✅ Development environment ready"
else
    echo "✅ Virtual environment already exists"
    echo "✅ Development dependencies already installed"
fi

echo ""
echo "🚀 Starting Crawl4AI MCP server..."
echo "💡 Development tips:"
echo "   • Server will run on http://localhost:8051/mcp/"
echo "   • Press Ctrl+C to stop the server"
echo "   • Configure your .env file for full functionality"
echo ""

# Start the server
uv run src/crawl4ai_mcp.py