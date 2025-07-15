
"""
Utility functions for the Crawl4AI MCP server.
"""
import os
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

def get_qdrant_client() -> QdrantClient:
    """
    Get a Qdrant client with the URL and key from environment variables.
    
    Returns:
        Qdrant client instance
    """
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def setup_qdrant_collections(client: QdrantClient):
    """
    Ensure all necessary collections exist in Qdrant.
    """
    try:
        # Documents collection
        client.recreate_collection(
            collection_name=DOCUMENTS_COLLECTION,
            vectors_config=models.VectorParams(size=EMBEDDING_DIMENSION, distance=models.Distance.COSINE),
        )
        # Code examples collection
        client.recreate_collection(
            collection_name=CODE_EXAMPLES_COLLECTION,
            vectors_config=models.VectorParams(size=EMBEDDING_DIMENSION, distance=models.Distance.COSINE),
        )
        # Sources collection (no vectors, just metadata)
        client.recreate_collection(
            collection_name=SOURCES_COLLECTION,
            vectors_config=models.VectorParams(size=EMBEDDING_DIMENSION, distance=models.Distance.COSINE), # Dummy vector
        )
        print("✓ Qdrant collections checked/created successfully.")
    except Exception as e:
        print(f"Error setting up Qdrant collections: {e}")
        # This is a critical error, so we might want to raise it
        raise

async def create_embeddings_batch(texts: List[str], max_batch_size: int = 5) -> List[List[float]]:
    """
    Create embeddings for multiple texts using a self-hosted TEI server.
    Splits large batches to prevent 413 Payload Too Large errors.
    
    Args:
        texts: List of texts to create embeddings for
        max_batch_size: Maximum number of texts to send in one request
        
    Returns:
        List of embeddings (each embedding is a list of floats)
    """
    if not texts:
        return []
    
    all_embeddings = []
    
    # Process in smaller batches to prevent payload size issues
    for i in range(0, len(texts), max_batch_size):
        batch_texts = texts[i:i + max_batch_size]
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    # Calculate approximate payload size
                    total_chars = sum(len(text) for text in batch_texts)
                    if total_chars > 50000:  # If batch too large, split further
                        # Recursively split the batch
                        mid = len(batch_texts) // 2
                        batch1 = await create_embeddings_batch(batch_texts[:mid], max_batch_size)
                        batch2 = await create_embeddings_batch(batch_texts[mid:], max_batch_size)
                        all_embeddings.extend(batch1 + batch2)
                        break
                    
                    response = await client.post(EMBEDDING_MODEL_URL, json={"inputs": batch_texts, "truncate": True})
                    response.raise_for_status()
                    batch_embeddings = response.json()
                    all_embeddings.extend(batch_embeddings)
                    break
                    
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 413:  # Payload Too Large
                        print(f"Payload too large for batch of {len(batch_texts)} texts, splitting...")
                        # Split batch in half and retry
                        if len(batch_texts) == 1:
                            # Single text is too large, truncate it
                            truncated_text = batch_texts[0][:10000]  # Limit to 10k chars
                            response = await client.post(EMBEDDING_MODEL_URL, json={"inputs": [truncated_text], "truncate": True})
                            response.raise_for_status()
                            batch_embeddings = response.json()
                            all_embeddings.extend(batch_embeddings)
                            break
                        else:
                            mid = len(batch_texts) // 2
                            batch1 = await create_embeddings_batch(batch_texts[:mid], max_batch_size)
                            batch2 = await create_embeddings_batch(batch_texts[mid:], max_batch_size)
                            all_embeddings.extend(batch1 + batch2)
                            break
                    else:
                        raise e
                        
                except httpx.RequestError as e:
                    if attempt < max_retries - 1:
                        print(f"Error creating batch embeddings (attempt {attempt + 1}/{max_retries}): {e}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        print(f"Failed to create batch embeddings after {max_retries} attempts: {e}")
                        # Fallback to creating zero embeddings for this batch
                        all_embeddings.extend([[0.0] * EMBEDDING_DIMENSION for _ in batch_texts])
                        break
    
    return all_embeddings

async def create_embedding(text: str) -> List[float]:
    """
    Create an embedding for a single text.
    
    Args:
        text: Text to create an embedding for
        
    Returns:
        List of floats representing the embedding
    """
    try:
        embeddings = await create_embeddings_batch([text])
        return embeddings[0] if embeddings else [0.0] * EMBEDDING_DIMENSION
    except Exception as e:
        print(f"Error creating embedding: {e}")
        return [0.0] * EMBEDDING_DIMENSION

async def call_llm(prompt: str, model_name: str) -> str:
    """
    Call a local LLM (like Ollama) for text generation.
    """
    if not LLM_MODEL_URL:
        print("LLM_MODEL_URL not set. Skipping LLM call.")
        return "LLM not configured."

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 200
                }
            }
            response = await client.post(LLM_MODEL_URL, json=payload)
            response.raise_for_status()
            # The response from Ollama is a JSON object with a "response" key
            return response.json().get("response", "").strip()
        except httpx.RequestError as e:
            print(f"Error calling LLM at {LLM_MODEL_URL}: {e}")
            return f"Error calling LLM: {e}"
        except Exception as e:
            print(f"An unexpected error occurred during LLM call: {e}")
            return f"Unexpected LLM error: {e}"

async def generate_contextual_embedding(full_document: str, chunk: str) -> Tuple[str, bool]:
    """
    Generate contextual information for a chunk using a local LLM.
    """
    use_contextual = os.getenv("USE_CONTEXTUAL_EMBEDDINGS", "false") == "true"
    if not use_contextual or not LLM_MODEL_URL:
        return chunk, False

    prompt = f"""<document> 
{full_document[:25000]} 
</document>
Here is the chunk we want to situate within the whole document 
<chunk> 
{chunk}
</chunk> 
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""

    context = await call_llm(prompt, LLM_MODEL_NAME)
    if "Error" in context:
        print(f"Failed to generate contextual embedding: {context}")
        return chunk, False
    
    contextual_text = f"{context}\n---\n{chunk}"
    return contextual_text, True

async def process_chunk_with_context(args):
    url, content, full_document = args
    return await generate_contextual_embedding(full_document, content)

async def add_documents_to_qdrant(
    client: QdrantClient, 
    urls: List[str], 
    chunk_numbers: List[int],
    contents: List[str], 
    metadatas: List[Dict[str, Any]],
    url_to_full_document: Dict[str, str],
    batch_size: int = 10  # Reduced from 50 to prevent 413 errors
):
    """
    Add documents to the Qdrant collection in batches.
    Deletes existing records with the same URLs before inserting.
    """
    unique_urls = list(set(urls))
    if unique_urls:
        try:
            client.delete(
                collection_name=DOCUMENTS_COLLECTION,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="url",
                                match=models.MatchAny(any=unique_urls)
                            )
                        ]
                    )
                )
            )
        except Exception as e:
            print(f"Error deleting documents for URLs {unique_urls}: {e}")

    use_contextual = os.getenv("USE_CONTEXTUAL_EMBEDDINGS", "false") == "true"
    
    for i in range(0, len(contents), batch_size):
        batch_end = min(i + batch_size, len(contents))
        batch_contents = contents[i:batch_end]
        batch_metadatas = metadatas[i:batch_end]
        batch_urls = urls[i:batch_end]

        texts_to_embed = []
        if use_contextual:
            tasks = [
                process_chunk_with_context((batch_urls[j], content, url_to_full_document.get(batch_urls[j], "")))
                for j, content in enumerate(batch_contents)
            ]
            results = await asyncio.gather(*tasks)
            for j, (text, success) in enumerate(results):
                texts_to_embed.append(text)
                batch_metadatas[j]["contextual_embedding"] = success
        else:
            texts_to_embed = batch_contents

        batch_embeddings = await create_embeddings_batch(texts_to_embed, max_batch_size=5)
        
        points = []
        for j in range(len(batch_contents)):
            payload = {
                "url": batch_urls[j],
                "chunk_number": chunk_numbers[i+j],
                "content": batch_contents[j], # Store original content
                "metadata": batch_metadatas[j],
                "source_id": urlparse(batch_urls[j]).netloc or urlparse(batch_urls[j]).path
            }
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=batch_embeddings[j],
                    payload=payload
                )
            )
        
        if points:
            client.upsert(collection_name=DOCUMENTS_COLLECTION, points=points, wait=True)

async def search_documents(
    client: QdrantClient, 
    query: str, 
    match_count: int = 10, 
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Search for documents in Qdrant using vector similarity.
    """
    query_embedding = await create_embedding(query)
    
    search_filter = None
    if filter_metadata and "source" in filter_metadata:
        search_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_id",
                    match=models.MatchValue(value=filter_metadata["source"])
                )
            ]
        )

    try:
        hits = client.search(
            collection_name=DOCUMENTS_COLLECTION,
            query_vector=query_embedding,
            query_filter=search_filter,
            limit=match_count,
            with_payload=True
        )
        return [
            {**hit.payload, "similarity": hit.score} for hit in hits
        ]
    except Exception as e:
        print(f"Error searching documents in Qdrant: {e}")
        return []

def extract_code_blocks(markdown_content: str, min_length: int = 300) -> List[Dict[str, Any]]:
    """
    Extract code blocks from markdown content along with context.
    """
    # This function remains largely the same, just adjusted min_length default
    # as per the original README.
    code_blocks = []
    # ... (rest of the logic is identical to the original)
    content = markdown_content.strip()
    start_offset = 0
    if content.startswith('```'):
        start_offset = 3
    
    backtick_positions = []
    pos = start_offset
    while True:
        pos = markdown_content.find('```', pos)
        if pos == -1:
            break
        backtick_positions.append(pos)
        pos += 3
    
    i = 0
    while i < len(backtick_positions) - 1:
        start_pos = backtick_positions[i]
        end_pos = backtick_positions[i + 1]
        
        code_section = markdown_content[start_pos+3:end_pos]
        lines = code_section.split('\n', 1)
        if len(lines) > 1:
            first_line = lines[0].strip()
            if first_line and not ' ' in first_line and len(first_line) < 20:
                language = first_line
                code_content = lines[1].strip() if len(lines) > 1 else ""
            else:
                language = ""
                code_content = code_section.strip()
        else:
            language = ""
            code_content = code_section.strip()
        
        if len(code_content) < min_length:
            i += 2
            continue
        
        context_start = max(0, start_pos - 1000)
        context_before = markdown_content[context_start:start_pos].strip()
        context_end = min(len(markdown_content), end_pos + 3 + 1000)
        context_after = markdown_content[end_pos + 3:context_end].strip()
        
        code_blocks.append({
            'code': code_content,
            'language': language,
            'context_before': context_before,
            'context_after': context_after,
            'full_context': f"{context_before}\n\n{code_content}\n\n{context_after}"
        })
        i += 2
    
    return code_blocks

async def generate_code_example_summary(code: str, context_before: str, context_after: str) -> str:
    """
    Generate a summary for a code example using a local LLM.
    """
    use_agentic_rag = os.getenv("USE_AGENTIC_RAG", "false") == "true"
    if not use_agentic_rag or not LLM_MODEL_URL:
        return "Code example summary generation is disabled."

    prompt = f"""<context_before>
{context_before[-500:]}
</context_before>

<code_example>
{code[:1500]}
</code_example>

<context_after>
{context_after[:500]}
</context_after>

Based on the code example and its surrounding context, provide a concise summary (2-3 sentences) that describes what this code example demonstrates and its purpose. Focus on the practical application and key concepts illustrated."""
    
    summary = await call_llm(prompt, LLM_MODEL_NAME)
    return summary if "Error" not in summary else "Could not generate summary."

async def add_code_examples_to_qdrant(
    client: QdrantClient,
    urls: List[str],
    chunk_numbers: List[int],
    code_examples: List[str],
    summaries: List[str],
    metadatas: List[Dict[str, Any]],
    batch_size: int = 10  # Reduced from 50 to prevent 413 errors
):
    """
    Add code examples to the Qdrant code_examples collection.
    """
    if not urls:
        return
        
    unique_urls = list(set(urls))
    if unique_urls:
        client.delete(
            collection_name=CODE_EXAMPLES_COLLECTION,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="url",
                            match=models.MatchAny(any=unique_urls)
                        )
                    ]
                )
            )
        )

    for i in range(0, len(urls), batch_size):
        batch_end = min(i + batch_size, len(urls))
        batch_texts = [f"{code_examples[j]}\n\nSummary: {summaries[j]}" for j in range(i, batch_end)]
        
        embeddings = await create_embeddings_batch(batch_texts, max_batch_size=5)
        
        points = []
        for j, embedding in enumerate(embeddings):
            idx = i + j
            payload = {
                'url': urls[idx],
                'chunk_number': chunk_numbers[idx],
                'content': code_examples[idx],
                'summary': summaries[idx],
                'metadata': metadatas[idx],
                'source_id': urlparse(urls[idx]).netloc or urlparse(urls[idx]).path
            }
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload=payload
                )
            )
        
        if points:
            client.upsert(collection_name=CODE_EXAMPLES_COLLECTION, points=points, wait=True)

async def update_source_info(client: QdrantClient, source_id: str, summary: str, word_count: int):
    """
    Update or insert source information in the Qdrant sources collection.
    """
    # In Qdrant, we "upsert". We need a consistent ID for each source.
    # We can generate a UUID based on the source_id string.
    source_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, source_id)
    
    # We need a dummy vector for this collection.
    dummy_vector = [0.0] * EMBEDDING_DIMENSION

    try:
        client.upsert(
            collection_name=SOURCES_COLLECTION,
            points=[
                models.PointStruct(
                    id=str(source_uuid),
                    vector=dummy_vector,
                    payload={
                        "source_id": source_id,
                        "summary": summary,
                        "total_words": word_count,
                        "updated_at": time.time()
                    }
                )
            ],
            wait=True
        )
        print(f"Upserted source: {source_id}")
    except Exception as e:
        print(f"Error upserting source {source_id}: {e}")

async def extract_source_summary(source_id: str, content: str) -> str:
    """
    Extract a summary for a source from its content using a local LLM.
    """
    if not LLM_MODEL_URL:
        return f"Content from {source_id}"

    truncated_content = content[:25000]
    prompt = f"""<source_content>
{truncated_content}
</source_content>

The above content is from the documentation for '{source_id}'. Please provide a concise summary (3-5 sentences) that describes what this library/tool/framework is about. The summary should help understand what the library/tool/framework accomplishes and the purpose."""
    
    summary = await call_llm(prompt, LLM_MODEL_NAME)
    return summary if "Error" not in summary else f"Content from {source_id}"

async def search_code_examples(
    client: QdrantClient, 
    query: str, 
    match_count: int = 10, 
    filter_metadata: Optional[Dict[str, Any]] = None,
    source_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search for code examples in Qdrant.
    """
    enhanced_query = f"Code example for {query}\n\nSummary: Example code showing {query}"
    query_embedding = await create_embedding(enhanced_query)
    
    search_filter = None
    if source_id:
        search_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="source_id",
                    match=models.MatchValue(value=source_id)
                )
            ]
        )

    try:
        hits = client.search(
            collection_name=CODE_EXAMPLES_COLLECTION,
            query_vector=query_embedding,
            query_filter=search_filter,
            limit=match_count,
            with_payload=True
        )
        return [
            {**hit.payload, "similarity": hit.score} for hit in hits
        ]
    except Exception as e:
        print(f"Error searching code examples in Qdrant: {e}")
        return []
