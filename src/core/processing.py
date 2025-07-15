"""
Content processing functions (chunking, reranking, etc.).
"""
import asyncio
import re
import concurrent.futures
from typing import List, Dict, Any, Optional
from sentence_transformers import CrossEncoder
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import nltk
from nltk.tokenize import sent_tokenize, TextTilingTokenizer
import numpy as np

def ensure_nltk_data():
    """Ensure required NLTK data is downloaded."""
    try:
        import nltk
        nltk.data.find('tokenizers/punkt')
    except (LookupError, ImportError):
        try:
            nltk.download('punkt', quiet=True)
        except Exception:
            pass  # Will fallback to regex-based splitting

# This function must be at the top level to be pickleable by ProcessPoolExecutor
def _run_rerank_in_process(model: CrossEncoder, query: str, texts: List[str]) -> List[float]:
    """Helper function to run the prediction in a separate process."""
    pairs = [[query, text] for text in texts]
    return model.predict(pairs)

async def rerank_results(pool: concurrent.futures.ProcessPoolExecutor, model: CrossEncoder, query: str, results: List[Dict[str, Any]], content_key: str = "content") -> List[Dict[str, Any]]:
    """
    Rerank search results asynchronously using a process pool.
    """
    if not model or not results:
        return results
    
    loop = asyncio.get_running_loop()
    texts = [result.get(content_key, "") for result in results]
    
    try:
        scores = await loop.run_in_executor(
            pool, _run_rerank_in_process, model, query, texts
        )
        
        for i, result in enumerate(results):
            result["rerank_score"] = float(scores[i])
        
        return sorted(results, key=lambda x: x.get("rerank_score", 0), reverse=True)
    except Exception as e:
        print(f"Error during reranking: {e}")
        return results

class ChunkingStrategy:
    """Base class for chunking strategies."""
    
    def chunk(self, text: str) -> List[str]:
        raise NotImplementedError

class RegexChunking(ChunkingStrategy):
    def __init__(self, patterns: Optional[List[str]] = None):
        self.patterns = patterns or [r'\n\n']  # Default pattern for paragraphs

    def chunk(self, text: str) -> List[str]:
        paragraphs = [text]
        for pattern in self.patterns:
            paragraphs = [seg for p in paragraphs for seg in re.split(pattern, p) if seg.strip()]
        return paragraphs

class SentenceChunking(ChunkingStrategy):
    def chunk(self, text: str) -> List[str]:
        try:
            sentences = sent_tokenize(text)
            return [sentence.strip() for sentence in sentences if sentence.strip()]
        except Exception:
            # Fallback to basic splitting if NLTK data is not available
            sentences = re.split(r'[.!?]+', text)
            return [sentence.strip() for sentence in sentences if sentence.strip()]

class TopicSegmentationChunking(ChunkingStrategy):
    def __init__(self):
        try:
            self.tokenizer = TextTilingTokenizer()
        except Exception:
            self.tokenizer = None

    def chunk(self, text: str) -> List[str]:
        if self.tokenizer:
            try:
                return self.tokenizer.tokenize(text)
            except Exception:
                pass
        # Fallback to paragraph-based chunking
        return RegexChunking().chunk(text)

class FixedLengthWordChunking(ChunkingStrategy):
    def __init__(self, chunk_size: int = 100):
        self.chunk_size = chunk_size

    def chunk(self, text: str) -> List[str]:
        words = text.split()
        chunks = []
        for i in range(0, len(words), self.chunk_size):
            chunk = ' '.join(words[i:i + self.chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        return chunks

class SlidingWindowChunking(ChunkingStrategy):
    def __init__(self, window_size: int = 100, step: int = 50):
        self.window_size = window_size
        self.step = step

    def chunk(self, text: str) -> List[str]:
        words = text.split()
        chunks = []
        for i in range(0, len(words) - self.window_size + 1, self.step):
            chunk = ' '.join(words[i:i + self.window_size])
            if chunk.strip():
                chunks.append(chunk)
        return chunks

class SmartMarkdownChunking(ChunkingStrategy):
    """Enhanced version of the original smart_chunk_markdown with better boundary detection."""
    
    def __init__(self, chunk_size: int = 5000, min_chunk_size: int = 100):
        self.chunk_size = chunk_size
        self.min_chunk_size = min_chunk_size

    def chunk(self, text: str) -> List[str]:
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            end = start + self.chunk_size
            if end >= text_length:
                final_chunk = text[start:].strip()
                if len(final_chunk) >= self.min_chunk_size:
                    chunks.append(final_chunk)
                elif chunks:  # Append to last chunk if too small
                    chunks[-1] += "\n\n" + final_chunk
                else:
                    chunks.append(final_chunk)
                break
            
            chunk = text[start:end]
            
            # Priority order for finding good break points
            break_patterns = [
                (r'```[^`]*```', 0.8),  # End of code blocks
                (r'\n#{1,6}\s', 0.7),    # Headers
                (r'\n\n', 0.5),          # Paragraph breaks
                (r'\n-\s', 0.4),         # List items
                (r'\n\*\s', 0.4),        # Bullet points
                (r'[.!?]\s+', 0.3),      # Sentence endings
                (r',\s+', 0.2),          # Comma breaks
            ]
            
            best_break = end
            for pattern, min_ratio in break_patterns:
                matches = list(re.finditer(pattern, chunk))
                if matches:
                    # Find the last match that's after min_ratio of chunk_size
                    for match in reversed(matches):
                        if match.end() > self.chunk_size * min_ratio:
                            best_break = start + match.end()
                            break
                    if best_break != end:
                        break
            
            chunk = text[start:best_break].strip()
            if len(chunk) >= self.min_chunk_size:
                chunks.append(chunk)
            elif chunks:  # Append to previous chunk if too small
                chunks[-1] += "\n\n" + chunk
            else:
                chunks.append(chunk)  # First chunk, keep even if small
            
            start = best_break
        
        return [chunk for chunk in chunks if chunk.strip()]

class CosineSimilarityExtractor:
    """Extract relevant chunks using cosine similarity."""
    
    def __init__(self, query: str):
        self.query = query
        self.vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)

    def find_relevant_chunks(self, chunks: List[str], top_k: int = 5) -> List[tuple]:
        if not chunks:
            return []
        
        try:
            vectors = self.vectorizer.fit_transform([self.query] + chunks)
            similarities = cosine_similarity(vectors[0:1], vectors[1:]).flatten()
            
            # Get top-k most similar chunks
            top_indices = np.argsort(similarities)[::-1][:top_k]
            return [(chunks[i], float(similarities[i])) for i in top_indices if similarities[i] > 0.1]
        except Exception as e:
            print(f"Error in similarity extraction: {e}")
            return [(chunk, 1.0) for chunk in chunks[:top_k]]

def smart_chunk_markdown(text: str, chunk_size: int = 5000, strategy: str = "smart") -> List[str]:
    """Enhanced chunking function with multiple strategies."""
    
    strategies = {
        "smart": SmartMarkdownChunking(chunk_size),
        "regex": RegexChunking(),
        "sentence": SentenceChunking(),
        "topic": TopicSegmentationChunking(),
        "fixed_word": FixedLengthWordChunking(chunk_size // 10),  # Approximate word count
        "sliding": SlidingWindowChunking(chunk_size // 10, chunk_size // 20),
    }
    
    chunker = strategies.get(strategy, strategies["smart"])
    chunks = chunker.chunk(text)
    
    # Filter out very small chunks
    min_size = max(50, chunk_size // 100)
    return [chunk for chunk in chunks if len(chunk) >= min_size]

def extract_section_info(chunk: str) -> Dict[str, Any]:
    """Extract metadata from a chunk including headers, structure, and content type."""
    headers = re.findall(r'^(#+)\s+(.+)$', chunk, re.MULTILINE)
    header_str = '; '.join([f'{h[1]}' for h in headers]) if headers else ''
    
    # Detect content types
    code_blocks = len(re.findall(r'```[\s\S]*?```', chunk))
    links = len(re.findall(r'\[([^\]]+)\]\([^\)]+\)', chunk))
    lists = len(re.findall(r'^\s*[-*+]\s', chunk, re.MULTILINE))
    
    # Calculate reading complexity (rough estimate)
    sentences = len(re.findall(r'[.!?]+', chunk))
    words = len(chunk.split())
    avg_words_per_sentence = words / max(sentences, 1)
    
    return {
        "headers": header_str,
        "char_count": len(chunk),
        "word_count": words,
        "sentence_count": sentences,
        "avg_words_per_sentence": round(avg_words_per_sentence, 2),
        "code_blocks": code_blocks,
        "links": links,
        "lists": lists,
        "has_code": code_blocks > 0,
        "content_density": round(words / max(len(chunk), 1), 4)  # Words per character
    }

def get_chunking_strategy(strategy_name: str, **kwargs) -> ChunkingStrategy:
    """Factory function to get a chunking strategy by name."""
    strategies = {
        "smart": SmartMarkdownChunking,
        "regex": RegexChunking,
        "sentence": SentenceChunking,
        "topic": TopicSegmentationChunking,
        "fixed_word": FixedLengthWordChunking,
        "sliding": SlidingWindowChunking,
    }
    
    strategy_class = strategies.get(strategy_name, SmartMarkdownChunking)
    return strategy_class(**kwargs)

# Initialize NLTK data on import
ensure_nltk_data()