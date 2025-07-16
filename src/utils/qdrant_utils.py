"""
Qdrant-related utility functions.
"""
import os
import asyncio
import concurrent.futures
from typing import List, Dict, Any, Optional, Tuple
import json
from qdrant_client import QdrantClient, models
from urllib.parse import urlparse
import httpx
import re
import time
import uuid

# --- Qdrant Configuration ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
EMBEDDING_MODEL_URL = os.getenv("EMBEDDING_MODEL_URL", "http://localhost:8080/embed")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", 768))
LLM_MODEL_URL = os.getenv("LLM_MODEL_URL") # For Ollama, e.g., http://localhost:11434/api/generate
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "phi3") # e.g., phi3

# --- Collection Names ---
DOCUMENTS_COLLECTION = "documents"
CODE_EXAMPLES_COLLECTION = "code_examples"
SOURCES_COLLECTION = "sources"

# --- Default Limits ---
DEFAULT_SOURCES_LIMIT = int(os.getenv("DEFAULT_SOURCES_LIMIT", 200))

def get_qdrant_client() -> QdrantClient:
    """
    Get a Qdrant client with the URL and key from environment variables.
    
    Returns:
        Qdrant client instance
    """
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def setup_qdrant_collections(client: QdrantClient):
    """
    Ensure all necessary collections exist in Qdrant using modern API.
    """
    collections_config = [
        (DOCUMENTS_COLLECTION, "Documents collection for RAG content"),
        (CODE_EXAMPLES_COLLECTION, "Code examples collection for agentic RAG"),
        (SOURCES_COLLECTION, "Sources metadata collection"),
    ]
    
    try:
        for collection_name, description in collections_config:
            # Check if collection exists
            try:
                collection_info = client.get_collection(collection_name)
                print(f"✓ Collection '{collection_name}' already exists with {collection_info.points_count} points")
                continue
            except Exception:
                # Collection doesn't exist, create it
                pass
            
            try:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=EMBEDDING_DIMENSION, 
                        distance=models.Distance.COSINE
                    ),
                )
                print(f"✓ Created collection '{collection_name}' - {description}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"✓ Collection '{collection_name}' already exists")
                else:
                    raise e
                    
        print("✓ Qdrant collections setup completed successfully.")
    except Exception as e:
        print(f"Error setting up Qdrant collections: {e}")
        raise