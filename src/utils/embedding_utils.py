"""
Embedding and LLM utility functions.
"""
import os
import asyncio
from typing import List, Tuple
import httpx

# Configuration
EMBEDDING_MODEL_URL = os.getenv("EMBEDDING_MODEL_URL", "http://localhost:8080/embed")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", 768))
LLM_MODEL_URL = os.getenv("LLM_MODEL_URL") # For Ollama, e.g., http://localhost:11434/api/generate
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "phi3") # e.g., phi3

# Performance configuration matching TEI server settings
MAX_BATCH_SIZE = int(os.getenv("EMBEDDING_MAX_BATCH_SIZE", "64"))  # Match TEI max-batch-requests
MAX_CONCURRENT_BATCHES = int(os.getenv("EMBEDDING_MAX_CONCURRENT", "64"))  # Half of TEI max-concurrent-requests
MAX_TOKENS_PER_BATCH = int(os.getenv("EMBEDDING_MAX_TOKENS", "28000"))  # Below TEI max-batch-tokens for safety
CONNECTION_POOL_SIZE = int(os.getenv("EMBEDDING_CONNECTION_POOL", "32"))

# Global client and semaphore for connection pooling
_http_client = None
_semaphore = None
_semaphore_lock = asyncio.Lock()

async def _get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client with connection pooling."""
    global _http_client
    if _http_client is None:
        limits = httpx.Limits(
            max_keepalive_connections=CONNECTION_POOL_SIZE,
            max_connections=CONNECTION_POOL_SIZE + 10,
            keepalive_expiry=30.0
        )
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            limits=limits,
            http2=True
        )
    return _http_client

async def _get_semaphore() -> asyncio.Semaphore:
    """Get or create the semaphore for concurrent request limiting."""
    global _semaphore
    if _semaphore is None:
        async with _semaphore_lock:
            # Double-check after acquiring lock
            if _semaphore is None:
                _semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)
    return _semaphore

def _estimate_tokens(text: str) -> int:
    """
    Rough token estimation: ~4 chars per token for most models.
    
    This estimation works best for English text and may be less accurate for:
    - Code (which tends to have more tokens per character due to symbols)
    - Non-English languages (especially languages with different character densities)
    - Special characters and Unicode symbols
    - Mathematical notation or technical content
    
    Use this for batch sizing heuristics, not precise token counting.
    """
    return len(text) // 4

async def _send_batch_request(client: httpx.AsyncClient, batch_texts: List[str]) -> List[List[float]]:
    """Send a single batch request with proper error handling."""
    max_retries = 3
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            response = await client.post(
                EMBEDDING_MODEL_URL, 
                json={"inputs": batch_texts, "truncate": True}
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 413:  # Payload Too Large
                if len(batch_texts) == 1:
                    # Single text too large, truncate
                    truncated_text = batch_texts[0][:10000]
                    response = await client.post(
                        EMBEDDING_MODEL_URL, 
                        json={"inputs": [truncated_text], "truncate": True}
                    )
                    response.raise_for_status()
                    return response.json()
                else:
                    # Split batch and retry
                    mid = len(batch_texts) // 2
                    batch1 = await _send_batch_request(client, batch_texts[:mid])
                    batch2 = await _send_batch_request(client, batch_texts[mid:])
                    return batch1 + batch2
            else:
                raise e
                
        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                print(f"Error in batch request (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"Failed batch request after {max_retries} attempts: {e}")
                # Return zero embeddings as fallback
                return [[0.0] * EMBEDDING_DIMENSION for _ in batch_texts]
    
    return [[0.0] * EMBEDDING_DIMENSION for _ in batch_texts]

async def create_embeddings_batch(texts: List[str], max_batch_size: int = None) -> List[List[float]]:
    """
    Create embeddings for multiple texts using a self-hosted TEI server.
    Optimized for high throughput with connection pooling and concurrent processing.
    
    Args:
        texts: List of texts to create embeddings for
        max_batch_size: Maximum number of texts to send in one request (defaults to configured MAX_BATCH_SIZE)
        
    Returns:
        List of embeddings (each embedding is a list of floats)
    """
    if not texts:
        return []
    
    if max_batch_size is None:
        max_batch_size = MAX_BATCH_SIZE
    
    client = await _get_http_client()
    semaphore = await _get_semaphore()
    
    # Smart batching based on token estimation
    batches = []
    current_batch = []
    current_tokens = 0
    
    for text in texts:
        estimated_tokens = _estimate_tokens(text)
        
        # Check if adding this text would exceed limits
        if (current_batch and 
            (len(current_batch) >= max_batch_size or 
             current_tokens + estimated_tokens > MAX_TOKENS_PER_BATCH)):
            batches.append(current_batch)
            current_batch = [text]
            current_tokens = estimated_tokens
        else:
            current_batch.append(text)
            current_tokens += estimated_tokens
    
    if current_batch:
        batches.append(current_batch)
    
    # Process batches concurrently with semaphore limiting
    async def process_batch(batch_texts: List[str]) -> List[List[float]]:
        async with semaphore:
            return await _send_batch_request(client, batch_texts)
    
    # Execute all batches concurrently
    batch_results = await asyncio.gather(
        *[process_batch(batch) for batch in batches],
        return_exceptions=True
    )
    
    # Flatten results and handle any exceptions
    all_embeddings = []
    for i, result in enumerate(batch_results):
        if isinstance(result, Exception):
            print(f"Batch {i} failed with exception: {result}")
            # Fallback to zero embeddings for failed batch
            all_embeddings.extend([[0.0] * EMBEDDING_DIMENSION for _ in batches[i]])
        else:
            all_embeddings.extend(result)
    
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

async def close_http_client():
    """Close the shared HTTP client to clean up connections."""
    global _http_client, _semaphore
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
    _semaphore = None

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