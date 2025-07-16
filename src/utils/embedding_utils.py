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