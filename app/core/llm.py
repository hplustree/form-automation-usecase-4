import os
from typing import List, Dict, Optional, Tuple, Any
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
import json
import re
import numpy as np
from collections import defaultdict
from rank_bm25 import BM25Okapi
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.logging_config import logger
from app.utils.file_handler import DocumentLoader
from app.core.weaviate_client import WeaviateClient
from app.core.embedding import EmbeddingService
import redis as rqredis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", 86400))
sync_redis = rqredis.from_url(REDIS_URL)

load_dotenv()

class Source(BaseModel):
    file: str
    document_name: str
    pages: List[int]
    page_scores: Optional[Dict[int, float]] = None
    confidence: float
    hybrid_score: float
    filepath: str
    chunks: Optional[List[dict]] = None

class LLMResponse(BaseModel):
    verbatim_answer: str
    explanation: Optional[str] = None
    source: Optional[Source] = None

class FallbackResponse(BaseModel):
    """Pydantic model for validating fallback response structure."""
    verbatim_answer: str
    explanation: str

def get_chat_openai_params(model: str, reasoning_effort: str, max_tokens: int, base_url: str, api_key: str) -> Dict:
    """Helper to compute ChatOpenAI params based on model and reasoning_effort."""
    gpt5_variants = ["gpt-5", "gpt-5-mini", "gpt-5-nano"]
    temperature = None if model in gpt5_variants else float(os.getenv("TEMPERATURE", "0.5"))
    model_kwargs = {"reasoning": {"effort": reasoning_effort}} if model in gpt5_variants else {}
    return {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "max_tokens": max_tokens,
        "model_kwargs": model_kwargs,
        "temperature": temperature
    }

def tokenize(text: str) -> List[str]:
    return re.findall(r"\w+", text.lower())

def softmax_normalize_scores(scores_dict: Dict[str, float]) -> Dict[str, float]:
    """
    Apply softmax normalization to scores to get values between 0 and 1.
    
    Args:
        scores_dict: Dictionary with keys and their BM25 scores
        
    Returns:
        Dictionary with same keys and softmax-normalized scores
    """
    if not scores_dict:
        return {}
    
    keys = list(scores_dict.keys())
    scores = np.array([scores_dict[k] for k in keys])
    
    # Apply softmax
    exp_scores = np.exp(scores - np.max(scores))  # Subtract max for numerical stability
    softmax_scores = exp_scores / exp_scores.sum()
    
    return {keys[i]: float(softmax_scores[i]) for i in range(len(keys))}


def cutoff_first_big_gap_normalized(page_scores: Dict[str, float], threshold: float = 0.05, 
                                     min_results: int = 2, max_results: int = 3, 
                                     min_score_threshold: float = 0.5) -> List[str]:
    """
    Select top pages based on normalized scores with minimum score threshold.
    
    Args:
        page_scores: Dictionary mapping page keys to normalized scores (0-1 range)
        threshold: Gap threshold for cutoff
        min_results: Minimum number of pages to return
        max_results: Maximum number of pages to return
        min_score_threshold: Minimum score threshold (default 0.5)
        
    Returns:
        List of selected page keys
    """
    if not page_scores:
        return []
    
    # Sort by score descending
    sorted_pages = sorted(page_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Filter by minimum score threshold first
    filtered_pages = [(k, v) for k, v in sorted_pages if v >= min_score_threshold]
    
    if not filtered_pages:
        logger.warning(f"No pages meet minimum score threshold of {min_score_threshold}")
        return []
    
    # Apply max_results limit
    filtered_pages = filtered_pages[:max_results]
    
    # If only one page or at min_results, return as is
    if len(filtered_pages) <= min_results:
        return [k for k, v in filtered_pages]
    
    # Find gaps and apply cutoff logic
    selected = [filtered_pages[0][0]]  # Always include top page
    
    for i in range(1, len(filtered_pages)):
        gap = filtered_pages[i-1][1] - filtered_pages[i][1]
        
        # Stop if gap is significant
        if gap > threshold and len(selected) >= min_results:
            break
            
        selected.append(filtered_pages[i][0])
        
        # Stop at max_results
        if len(selected) >= max_results:
            break
    
    return selected

def cutoff_first_big_gap(scores_dict: Dict[str, float], threshold: float = 0.05, min_results: int = 1, max_results: int = 3) -> int:
    """
    Determine the cutoff point for page selection based on a 5% drop in relevance scores.
    Now works with page keys and uses percentage-based threshold.

    Args:
        scores_dict: Dictionary mapping page keys to their relevance scores
        threshold: Minimum score drop percentage to consider a gap significant (default: 0.05 = 5%)
        min_results: Minimum number of pages to return (default: 1)
        max_results: Maximum number of pages to return (default: 3)

    Returns:
        Integer indicating the number of pages to select
    """
    if not scores_dict:
        return 0

    # Sort pages by score in descending order
    sorted_pages_scores = sorted(scores_dict.items(), key=lambda x: x[1], reverse=True)
    n = len(sorted_pages_scores)
    
    if n <= min_results:
        return n

    cutoff = n
    for i in range(min_results - 1, n - 1):
        current_score = sorted_pages_scores[i][1]
        next_score = sorted_pages_scores[i + 1][1]
        
        # Calculate percentage drop
        if current_score > 0:
            drop_percentage = (current_score - next_score) / current_score
            if drop_percentage >= threshold:
                cutoff = i + 1
                break

    return min(cutoff, max_results)

class LLMService:
    """Service for handling LLM interactions for RAG."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = os.getenv("LLM_MODEL_GPT_5", "gpt-4.1-mini"),
        fallback_model: str = os.getenv("LLM_MODEL_GPT_5_MINI", "gpt-4.1-mini"),
        page_model: str = os.getenv("LLM_MODEL_GPT_4_1_MINI", "gpt-4.1-mini"),
        reasoning_effort: str = os.getenv("REASONING_EFFORT", "low"),
        weaviate_client: Optional[Any] = None,
        embedding_service: Optional[Any] = None,
    ):
        """
        Initialize the LLM service.

        Args:
            api_key: OpenAI API key. If None, will use OPENAI_API_KEY from environment.
            model: OpenAI model to use for generation.
            fallback_model: Fallback model.
            page_model: Model for page relevance assessment.
            reasoning_effort: Reasoning effort (mode) for GPT-5 variants or temperature mapping for others.
            weaviate_client: Weaviate client instance (optional, for page selection).
            embedding_service: Embedding service instance (optional, for page selection).
        """
        self.api_key = api_key or os.getenv("LITELLM_MASTER_KEY")
        if not self.api_key:
            raise ValueError("LiteLLM Master Key is required")

        self.model = model
        self.fallback_model = fallback_model
        self.page_model = page_model
        self.reasoning_effort = reasoning_effort
        self.max_tokens = int(os.getenv("MAX_RESPONSE_TOKENS", "500"))
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:4000")

        # Initialize services if not provided
        if weaviate_client is None or embedding_service is None:
            document_loader = DocumentLoader()

            weaviate_client = WeaviateClient(
                url=os.getenv("WEAVIATE_URL", "http://localhost:8080"),
                document_loader=document_loader,
            )

            embedding_service = EmbeddingService(
                api_key=self.api_key,
                embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
                min_chunk_size=int(os.getenv("MIN_CHUNK_SIZE", "100")),
                llm_model=model,
                chunk_size= int(os.getenv("CHUNK_SIZE", 1000)),
                chunk_overlap= int(os.getenv("CHUNK_OVERLAP", 200))
            )

        self.weaviate_client = weaviate_client
        self.embedding_service = embedding_service

        # Initialize clients with model-specific params
        params = get_chat_openai_params(
            self.model, self.reasoning_effort, self.max_tokens, base_url, self.api_key
        )
        self.client = ChatOpenAI(**params, streaming=False)

        fallback_params = get_chat_openai_params(
            self.fallback_model, self.reasoning_effort, self.max_tokens, base_url, self.api_key
        )
        self.fallback_client = ChatOpenAI(**fallback_params, streaming=False)

        page_params = get_chat_openai_params(
            self.page_model, self.reasoning_effort, self.max_tokens, base_url, self.api_key
        )
        self.page_client = ChatOpenAI(**page_params, streaming=False)

        # Handle TOP_PAGES env
        try:
            self.top_pages_limit = int(os.getenv("TOP_PAGES", 3))
            if self.top_pages_limit <= 0:
                logger.warning("TOP_PAGES must be a positive integer, defaulting to 3")
                self.top_pages_limit = 3
        except ValueError:
            logger.warning("Invalid TOP_PAGES value in .env, defaulting to 3")
            self.top_pages_limit = 3

    def _extract_text_from_response(self, resp) -> str:
        """Extract plain text from a ChatOpenAI response."""
        try:
            if isinstance(resp, str):
                return resp.strip()
            
            if hasattr(resp, "content"):
                content = resp.content
            else:
                content = resp

            if content is None:
                logger.warning("Response content is None, returning empty string")
                return ""
            
            if isinstance(content, str):
                return content.strip()
            
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif part:
                        text_parts.append(str(part))
                result = "".join(text_parts).strip()
                return result 
            
            if isinstance(content, dict):
            # Handle dicts more gracefully
                if "text" in content and isinstance(content["text"], str):
                    return content["text"].strip()
                logger.warning(f"Unexpected dict response without 'text': {content}")
                return ""
            
            return str(content).strip()
        except Exception as e:
            logger.error(f"Error extracting text from response: {str(e)}")
            return ""

    def parse_ai_message_to_json(self, msg: Any) -> dict:
        """Extract JSON object from LLM response."""
        try:
            text = self._extract_text_from_response(msg)
            if not text or not text.strip():
                logger.warning("Empty response content, returning default JSON")
                return {"error": "Empty response content"}

            if isinstance(msg, dict):
                return msg

            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                logger.warning("No JSON object found in response")
                return {"error": "No JSON object found"}

            json_str = match.group(0)
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {str(e)} | text={text[:200]}...")
            return {"error": f"JSON parsing failed: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error parsing JSON: {str(e)} | msg={msg}")
            return {"error": f"Unexpected error: {str(e)}"}

    def _extract_doc_ids(self, context_pages: Dict[str, str]) -> List[str]:
        """
        Extract unique doc_ids from context_pages keys.
        
        Args:
            context_pages: Dictionary mapping page keys (format: <doc_id>::page:<page_num>) to page content.
        
        Returns:
            List of unique doc_ids extracted from the keys.
        """
        if not context_pages:
            logger.warning("Page selection - context_pages is empty, returning empty doc_ids")
            return []

        unique_doc_ids = set()
        for key in context_pages.keys():
            if '::page:' in key:
                try:
                    doc_id = key.split('::page:')[0]
                    if doc_id:
                        unique_doc_ids.add(doc_id)
                except IndexError:
                    logger.warning(f"Page selection - Invalid key format: {key}")
                    continue
        
        doc_ids = sorted(list(unique_doc_ids))  # Sort for consistency
        logger.debug(f"Page selection - Extracted doc_ids: {doc_ids}")
        return doc_ids

    def _filter_pages_with_weaviate(
        self, 
        prompt: str, 
        answer: str, 
        page_numbers: List[int], 
        job_id: str,
    ) -> Tuple[List[int], Dict[int, float]]:
        """
        Filter pages using Weaviate hybrid search and return reduced page numbers with their hybrid scores.
        Uses job_id to fetch doc_ids and perform scoped search.
        """
        if not self.weaviate_client or not self.embedding_service:
            logger.warning("Page selection - Weaviate or embedding service unavailable, returning empty results")
            return [], {}

        if not page_numbers:
            logger.warning("Page selection - No page numbers provided, returning empty results")
            return [], {}

        try:
            # Combine prompt and answer for comprehensive query embedding
            query_text = f"{prompt} {answer}"
            query_vector = self.embedding_service.generate_prompt_embedding(query_text)
            logger.info(f"Page selection - Querying Weaviate for job_id '{job_id}' with query: {query_text[:50]}...")

            # Get doc_ids from the context (no document_types needed)
            # But since this is fallback, and context_pages are built from initial search, which was filtered,
            # but to be precise, we can fetch all relevant doc_ids for the job if needed, but since extracting from context_pages later.
            # For filter, we need doc_ids for the search.
            # Since it's filtering existing page_numbers, but search needs scope.
            # To align, fetch all doc_ids for job.

            doc_ids_json = sync_redis.get(f"job:{job_id}:doc_ids")
            doc_ids = json.loads(doc_ids_json) if doc_ids_json else None
            if not doc_ids:
                logger.warning(f"Page selection - No doc_ids found for job_id={job_id}")
                return [], {}

            weaviate_results = self.weaviate_client.search_similar(
                job_id=job_id,
                query_vector=query_vector,
                query_text=query_text,
                limit=20,
                doc_ids=doc_ids,
                alpha=0.3,
            )

            # Extract unique page numbers with their hybrid scores
            hybrid_scores = {}
            reduced_page_numbers = []
            for result in weaviate_results:
                chunk_page_numbers = result.get("page_numbers", [])
                if isinstance(chunk_page_numbers, int):
                    chunk_page_numbers = [chunk_page_numbers]
                elif not isinstance(chunk_page_numbers, list):
                    chunk_page_numbers = []
                hybrid_score = float(result.get("hybrid_score", 0.0))
                for page_num in chunk_page_numbers:
                    try:
                        page_num = int(page_num)
                        if page_num in page_numbers:
                            hybrid_scores[page_num] = max(hybrid_scores.get(page_num, 0.0), hybrid_score)
                            if page_num not in reduced_page_numbers:
                                reduced_page_numbers.append(page_num)
                    except (ValueError, TypeError):
                        logger.warning(f"Page selection - Invalid page number: {page_num}")
                        continue

            if not reduced_page_numbers:
                logger.info("Page selection - Weaviate returned no relevant pages, returning empty results")
                return [], {}

            logger.info(f"Page selection - Reduced to {len(reduced_page_numbers)} pages via Weaviate: {reduced_page_numbers}")
            logger.debug(f"Page selection - Weaviate hybrid scores: {hybrid_scores}")
            return sorted(reduced_page_numbers), hybrid_scores
        except Exception as e:
            logger.error(f"Page selection - Weaviate filtering failed: {str(e)}")
            return [], {}

    
    def select_top_pages(
        self,
        prompt: str,
        answer: str,
        context_pages: Dict[str, str],
        page_numbers: List[int],
        collection_id: str,
        context_chunks: List[Dict],
        explanation: Optional[str] = None
    ) -> Tuple[List[str], Dict[str, float]]:
        """
        Select the top most relevant pages using unified BM25 scoring with softmax normalization per document.
        """
        job_id = collection_id
        logger.info(f"Page selection - Selecting top pages from {len(context_chunks)} chunks using unified BM25 for job_id={job_id}")
        
        if not context_chunks:
            logger.warning("Page selection - No chunks provided")
            return [], {}

        # Merge answer and explanation for BM25 scoring
        combined_text = answer
        if explanation and explanation.strip():
            combined_text = f"{answer} {explanation}"
        
        # Apply BM25 on the merged text
        tokenized_corpus = [tokenize(c["text"]) for c in context_chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenize(combined_text))

        page_scores = {}
        page_extracts = {}
        pages_by_doc = defaultdict(dict)  # doc_id -> {page_key: score}

        reverse_mapping_json = sync_redis.get(f"job:{job_id}:doc_reverse_mapping")
        reverse_mapping = json.loads(reverse_mapping_json) if reverse_mapping_json else {}

        for c, s in zip(context_chunks, scores):
            c["score"] = float(s)
            chunk_page_numbers = c.get("page_numbers", [])
            if isinstance(chunk_page_numbers, int):
                chunk_page_numbers = [chunk_page_numbers]
            elif not isinstance(chunk_page_numbers, list):
                chunk_page_numbers = []

            doc_id = c.get("doc_id", "unknown")
            chunk_text = c.get("text", "")

            for page_num in chunk_page_numbers:
                try:
                    key = f"{doc_id}::page:{int(page_num)}"
                    bm25_score = c["score"]
                    
                    if key not in page_scores or bm25_score > page_scores[key]:
                        page_scores[key] = bm25_score
                        pages_by_doc[doc_id][key] = bm25_score
                        page_extracts[key] = {
                            "extract": chunk_text,
                            "doc_name": c.get("document_name", "") or c.get("filename", ""),
                            "page_num": int(page_num),
                            "doc_id": doc_id
                        }
                except (ValueError, TypeError):
                    logger.warning(f"Page selection - Invalid page number in chunk: {page_num}")
                    continue

        if not page_scores:
            logger.warning("Page selection - No valid pages found after BM25 scoring")
            return [], {}

        # Apply softmax normalization per document
        top_pages = []
        selected_scores = {}
        logger.info(f"Page selection - ++++++++++++++++++++++pages_by_doc: {pages_by_doc}")
        for doc_id, doc_page_scores in pages_by_doc.items():
            # Normalize scores for this document
            normalized_doc_scores = softmax_normalize_scores(doc_page_scores)
            logger.info(f"Page selection - ++++++++++++++++++++++normalized_doc_scores: {normalized_doc_scores}")
            # Filter pages with score >= 0.5 for this document
            qualified_pages = {k: v for k, v in normalized_doc_scores.items() if v >= 0.5}
            logger.info(f"Page selection - ++++++++++++++++++++++qualified_pages: {qualified_pages}")
            if qualified_pages:
                # Log raw page scores before cutoff (sorted by score descending)
                sorted_qualified = sorted(qualified_pages.items(), key=lambda x: x, reverse=True)
                logger.info(f"\nPage selection - doc_id={doc_id}:")
                logger.info(f"Raw page scores ({len(sorted_qualified)} pages with score >= 0.5):")
                for i, (page_key, score) in enumerate(sorted_qualified):
                    logger.info(f"  Page {page_key}: {score:.4f}")

                # Apply cutoff logic to qualified pages
                doc_top_pages = cutoff_first_big_gap_normalized(
                    qualified_pages, 
                    threshold=0.20,  # Increased from 0.05 to allow more pages with smaller gaps
                    min_results=2, 
                    max_results=3,   # Maximum 3 pages
                    min_score_threshold=0.5
                )
                
                # Log selected pages after cutoff
                logger.info(f"\nSelected pages after cutoff (threshold=0.20, min=2, max=3):")
                for i, page_key in enumerate(doc_top_pages):
                    score = normalized_doc_scores.get(page_key, 0.0)
                    logger.info(f"  Selected page {i+1}: {page_key} (score: {score:.4f})")
                logger.info(f"Final selection: {len(doc_top_pages)} pages")
                logger.info("")  # Add spacing for readability
                
                top_pages.extend(doc_top_pages)
                selected_scores.update({k: normalized_doc_scores[k] for k in doc_top_pages})
                logger.info(f"Page selection - doc_id={doc_id}: selected {len(doc_top_pages)} pages with scores >= 0.5")
            else:
                logger.info(f"Page selection - doc_id={doc_id}: no pages met 0.5 threshold")

        try:
            generate_request_json = sync_redis.get(f"job:{job_id}:payload") 
            if generate_request_json:
                generate_request = json.loads(generate_request_json)
                file_name_map = {
                    f.get("id"): os.path.basename(f.get("file", "")) for f in generate_request.get("files", [])
                }
            else:
                file_name_map = {}
        except Exception as e:
            logger.warning(f"Page selection - Could not load generate_request for job {job_id}: {e}")
            file_name_map = {}
        # Store unified references
        unified_references = []
        for key in top_pages:
            extract_data = page_extracts[key]
            doc_id = extract_data.get("doc_id", "")
            logger.info(f"INTOP document id : {doc_id}")

            filepath = file_name_map.get(doc_id, "unknown")
            doc_name = os.path.splitext(os.path.basename(filepath))[0]

            logger.info(f"INTOP document name : {doc_name}")

            unified_references.append({
                "file_name": doc_name,
                "page_number": extract_data["page_num"],
                "extract": extract_data["extract"],
                "page_score": selected_scores[key]
            })

        self._last_unified_references = unified_references

        logger.info(f"Page selection - Selected {len(top_pages)} pages across documents with normalized BM25 scores: {selected_scores}")
        return sorted(top_pages), selected_scores


    # Update for select_top_pages_for_fallback method in LLMService class
    def select_top_pages_for_fallback(
        self,
        prompt: str,
        answer: str,
        context_pages: Dict[str, str],
        page_numbers: List[int],
        collection_id: str,
        explanation: Optional[str] = None
    ) -> Tuple[List[str], Dict[str, float]]:
        """
        Select the top most relevant pages using unified BM25 scoring with softmax normalization per document.
        """
        job_id = collection_id
        logger.info(f"BM25 Fallback Page Selection - Evaluating pages for job_id={job_id}")
        
        if not context_pages or not page_numbers:
            logger.warning("BM25 Fallback Page Selection - No context pages or page numbers provided")
            return [], {}

        # Step 1: Get doc_ids from context_pages keys
        doc_ids = self._extract_doc_ids(context_pages)

        # Step 2: Weaviate hybrid pre-filter
        filtered_pages, hybrid_scores = self._filter_pages_with_weaviate(
            prompt=prompt,
            answer=answer,
            page_numbers=page_numbers,
            job_id=job_id,
        )

        if not filtered_pages:
            logger.warning("BM25 Fallback Page Selection - Weaviate returned no relevant pages")
            return [], {}

        # Step 3: Build context_chunks from filtered pages
        context_chunks = []
        reverse_mapping_json = sync_redis.get(f"job:{job_id}:doc_reverse_mapping")
        reverse_mapping = json.loads(reverse_mapping_json) if reverse_mapping_json else {}

        # NEW: Fetch actual filenames for each doc_id from Weaviate
        doc_id_to_filename = {}
        for doc_id in doc_ids:
            # Get filename from Weaviate chunks
            chunks = self.weaviate_client.get_all_chunks_by_doc_id(job_id, doc_id)
            if chunks and len(chunks) > 0:
                # Try multiple fields to get the actual filename
                actual_filename = (
                    chunks[0].get("filename", "") or 
                    chunks[0].get("document_name", "") or 
                    chunks[0].get("filepath", "").split('/')[-1] if chunks[0].get("filepath") else ""
                )
                doc_id_to_filename[doc_id] = actual_filename if actual_filename else "unknown"
            else:
                doc_id_to_filename[doc_id] = "unknown"

        for page_num in filtered_pages:
            page_key = next((key for key in context_pages if f"::page:{page_num}" in key), None)
            if not page_key:
                continue
            text = context_pages.get(page_key, "").strip()
            if not text:
                continue
            doc_id = page_key.split("::page:")[0] if page_key else "unknown"
            doc_type = reverse_mapping.get(doc_id, "unknown")
            actual_filename = doc_id_to_filename.get(doc_id, "unknown")
            
            context_chunks.append({
                "page_numbers": [int(page_num)],
                "doc_type": doc_type,
                "doc_id": doc_id,
                "text": text,
                "document_name": actual_filename, 
                "filename": actual_filename
            })

        if not context_chunks:
            logger.warning("Page selection - No chunks provided")
            return [], {}

        # Merge answer and explanation for BM25 scoring
        combined_text = answer
        if explanation and explanation.strip():
            combined_text = f"{answer} {explanation}"
        
        # Apply BM25 on the merged text
        tokenized_corpus = [tokenize(c["text"]) for c in context_chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(tokenize(combined_text))

        page_scores = {}
        page_extracts = {}
        pages_by_doc = defaultdict(dict)  # doc_id -> {page_key: score}

        reverse_mapping_json = sync_redis.get(f"job:{job_id}:doc_reverse_mapping")
        reverse_mapping = json.loads(reverse_mapping_json) if reverse_mapping_json else {}

        for c, s in zip(context_chunks, scores):
            c["score"] = float(s)
            chunk_page_numbers = c.get("page_numbers", [])
            if isinstance(chunk_page_numbers, int):
                chunk_page_numbers = [chunk_page_numbers]
            elif not isinstance(chunk_page_numbers, list):
                chunk_page_numbers = []

            doc_id = c.get("doc_id", "unknown")
            chunk_text = c.get("text", "")

            for page_num in chunk_page_numbers:
                try:
                    key = f"{doc_id}::page:{int(page_num)}"
                    bm25_score = c["score"]
                    
                    if key not in page_scores or bm25_score > page_scores[key]:
                        page_scores[key] = bm25_score
                        pages_by_doc[doc_id][key] = bm25_score
                        page_extracts[key] = {
                            "extract": chunk_text,
                            "doc_name": c.get("document_name", "") or c.get("filename", ""),
                            "page_num": int(page_num),
                            "doc_id": doc_id
                        }
                except (ValueError, TypeError):
                    logger.warning(f"Page selection - Invalid page number in chunk: {page_num}")
                    continue

        if not page_scores:
            logger.warning("Page selection - No valid pages found after BM25 scoring")
            return [], {}

        # Apply softmax normalization per document
        top_pages = []
        selected_scores = {}
        
        for doc_id, doc_page_scores in pages_by_doc.items():
            # Normalize scores for this document
            normalized_doc_scores = softmax_normalize_scores(doc_page_scores)
            
            # Filter pages with score >= 0.5 for this document
            qualified_pages = {k: v for k, v in normalized_doc_scores.items() if v >= 0.5}
            
            if qualified_pages:
                # Apply cutoff logic to qualified pages
                doc_top_pages = cutoff_first_big_gap_normalized(
                    qualified_pages, 
                    threshold=0.15,  # Increased from 0.05 to allow more pages with smaller gaps
                    min_results=2, 
                    max_results=5,   # Increased from 3 to allow more relevant pages
                    min_score_threshold=0.5
                )
                
                top_pages.extend(doc_top_pages)
                selected_scores.update({k: normalized_doc_scores[k] for k in doc_top_pages})
                logger.info(f"Page selection - doc_id={doc_id}: selected {len(doc_top_pages)} pages with scores >= 0.5")
            else:
                logger.info(f"Page selection - doc_id={doc_id}: no pages met 0.5 threshold")

        # Store unified references
        try:
            generate_request_json = sync_redis.get(f"job:{job_id}:payload") 
            if generate_request_json:
                generate_request = json.loads(generate_request_json)
                file_name_map = {
                    f.get("id"): os.path.basename(f.get("file", "")) for f in generate_request.get("files", [])
                }
            else:
                file_name_map = {}
        except Exception as e:
            logger.warning(f"Fallback Page selection - Could not load generate_request for job {job_id}: {e}")
            file_name_map = {}

        unified_references = []
        for key in top_pages:
            extract_data = page_extracts[key]
            doc_id = extract_data.get("doc_id", "")
            logger.info(f"INFALLBACK document id : {doc_id}")
            filepath = file_name_map.get(doc_id, "unknown")
            doc_name = os.path.splitext(os.path.basename(filepath))[0]
            logger.info(f"INFALLBACK document name : {doc_name}")
            unified_references.append({
                "file_name": doc_name,
                "page_number": extract_data["page_num"],
                "extract": extract_data["extract"],
                "page_score": selected_scores[key]
            })

        self._last_unified_references = unified_references

        logger.info(f"Page selection - Selected {len(top_pages)} pages across documents with normalized BM25 scores: {selected_scores}")
        return sorted(top_pages), selected_scores
    
    def generate_rag_response(self, prompt: str, context_chunks: List[dict], context_pages: dict, collection_id: str, explanation_needed: bool = False, prompt_type: Optional[str] = None) -> LLMResponse:
        """
        Generate a response using retrieved context chunks and their associated page texts in the unified response format.

        Args:
            prompt: User's query
            context_chunks: List of retrieved document chunks with text and metadata
            context_pages: Dictionary mapping page numbers to their full text (from original_texts)
            explanation_needed: Whether to include an explanation
            prompt_type: "summarize" or "verbatim" to control response style
            collection_id: Weaviate collection ID for page selection

        Returns:
            LLMResponse with verbatim_answer, explanation (if requested), source, and page_scores
        """
        if prompt_type == "summarize":
            verbatim_answer = self._generate_summarized_answer(prompt, context_chunks, context_pages)
        else:
            verbatim_answer = self._generate_verbatim_answer(prompt, context_chunks, context_pages)
        
        if not isinstance(verbatim_answer, str):
            logger.warning(f"verbatim_answer is not a string: {type(verbatim_answer)}, attempting conversion")
            verbatim_answer = str(verbatim_answer) if verbatim_answer else ""
        
        explanation = None
        if explanation_needed:
            explanation = self.generate_explanation(prompt, verbatim_answer, context_chunks, context_pages)
        
        return LLMResponse(
            verbatim_answer=verbatim_answer,
            explanation=explanation,
            source=None
        )

    def _generate_verbatim_answer(self, prompt: str, context_chunks: List[dict], context_pages: dict) -> str:
        """Generate the verbatim answer for the query using provided context."""
        system_prompt = """You are an expert at extracting exact text from documents. Follow these instructions:

1. Extract the exact answer from the provided documents that directly answers the query.
2. Quote the text verbatim, preserving original wording, punctuation, and formatting.
3. If the question requires sentence completion or fill-in-the-blank, complete it using the exact matching text from the documents.
4. If options are provided in the question, select the correct option using the exact phrasing from the documents.
5. If multiple relevant sections exist, select the most precise and concise match.
6. If no exact match is found, return an empty string.
7. Do not paraphrase, summarize, interpret, or add any external information.
8. Always provide the response strictly in English — if the input is in another language, translate the response into English.
9. Return the answer in plain text format only.

Guidelines:
- Verbatim Answer Only: Provide a concise, standalone factual statement or direct completion as required by the query.
- Sentence Completion: If the query contains a sentence to complete, do so using exact matching text.
- Use chunked text to extract precise and targeted details, while relying on the full page content to understand the broader context. Always prioritize content that is most relevant to the query.

Always follow HTML Formatting Guidelines:
- Output must be in **basic HTML format only** in string.
- Allowed tags: <p>, <i>, <u>.
- Use <p> for paragraphs and lists.
- Use <i> for italic text where present in the original.
- Use line breaks (\n) inside the same paragraph if required.
- Do not use <html>, <head>, <body>, <div>, <span>, or CSS/JavaScript.
- Do not add any extra structure, metadata, or attributes inside tags.
- Do not use any special character unicodes.
- Ensure the HTML is clean and minimal — only wrap the extracted answer text.

"""
        user_prompt = f"""Context Information:
1. ### Full Document Context:
{context_pages}
2. ### Retrieved Chunks:
{context_chunks}

Question: {prompt}

Instructions:
Based on the above context, extract the exact text that answers the question. Follow these rules:
- Use the precise wording from the documents.
- Do not paraphrase or summarize.
- If the question asks to complete a sentence or fill in the blank, do so using the exact matching text.
- If options are provided, complete the question with the correct option using verbatim text.
- Return only the final answer as plain text.
"""
        try:
            response = self.client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            answer = self._extract_text_from_response(response)
            logger.debug(f"Raw verbatim answer response: {answer[:200]}...")
            logger.info(f"Verbatim answer generated: {answer}")
            return answer
        except Exception as e:
            logger.error(f"Verbatim answer generation failed: {str(e)}")
            return ""

    def _generate_summarized_answer(self, prompt: str, context_chunks: List[dict], context_pages: dict) -> str:
        """Generate a summarized answer for the query using provided context."""
        
        system_prompt = """You are an expert in summarizing financial and legal documents for executive teams. Your task is to generate concise, business-ready executive summaries from sources such as CIMs, SPAs and Warranty Deed. Follow these strict instructions:
           1. Provide an accurate and concise summary that answers the query strictly based on the provided context.
           2. Do not paraphrase—extract the exact relevant content directly from the document.
           3. Ensure the answer includes everything explicitly asked in the query (e.g., complete-the-sentence requests, specific word limits, clause references, etc.).
           4. If the query requires a specific format (e.g., complete a sentence, limit to 30 words), adhere to it strictly.
           5. Use only the information available in the 'context_pages'. Do not rely on external knowledge or make assumptions.
           6. If the answer is not found in the document, respond with: "Information not found in the provided documents."
           7. Always provide the response strictly in English — if the input is in another language, translate the response into English.
		   8. Ensure the first letter of the output is capitalized, even if the source text begins with a lowercase word.
           9. Keep the tone clear and professional. Return the answer in plain text format only.

           Always follow HTML Formatting Guidelines:
           - Output must be in **basic HTML format only** in string.
           - Allowed tags: <p>, <i>, <u>.
           - Use <p> for paragraphs and lists.
           - Use <i> for italic text where present in the original.
           - Use line breaks (\n) inside the same paragraph if requires.
           - Do not use <html>, <head>, <body>, <div>, <span>, or CSS/JavaScript.
           - Do not add any extra structure, metadata, or attributes inside tags.
           - Do not use any special character unicodes.
           - Ensure the HTML is clean and minimal — only wrap the extracted answer text.

           Omit Missing Data Commentary
            •	Only summarize facts that are explicitly available in the source material.
            •	Do not mention or speculate on missing information.
            •	If a requested detail (e.g., headquarters, revenue split) is not stated, simply omit it and continue summarizing what is available.
            •   If the query is descriptive or narrative (e.g., business model, product description, customers, management team, M&A activity): a) summarize only what is explicitly available; b) If part of the requested detail is missing, omit it silently and continue with what is present; and c) Do not say “not found”, “not available”, or “not provided” for missing details.
            •	Write in a direct, declarative style suitable for executives.
            •	Ensure the first word of the response starts with a capital letter.
            •	Keep the response concise and within the requested word limit.
           """
        user_prompt = f"""Context Information:

1. ### Full Document Context:
{context_pages}

2. ### Focus Chunks:
{context_chunks}

### Query:
{prompt}

Instructions:
- Use only the information available in the 'Full Document Context', where 'Focus Chunks' provide the focus area of context.
- If the question specifies a word/character limit or asks to complete a sentence, follow it strictly.
- If the question provides a partial sentence, placeholder (e.g., "[...]"), or requires insertion of a clause/section reference:
 - Find the exact clause/section number or reference from the provided context.
 - Insert it directly into the sentence, replacing the placeholder exactly as shown.
 - Do not modify any other part of the provided text.
- Include all elements explicitly requested in the query (e.g., clause numbers, financial metrics, specific terms).
- If the query requests a table format, provide the answer strictly in table format with clear spacing and proper column separation.
 - Do not add any headings, explanatory text, or extra wording unless explicitly requested.
- Do not add hallucinated or assumed values for financials, clause numbers, schedules, or any other specific details.
 - If the requested information is not present, leave it blank or keep the placeholder as is.
- If no relevant information is found, return an empty string ("").
- Keep the answer clear, concise, and professional.
- Return the final answer in plain text only.

Voice & framing
	•	Write in a neutral, declarative voice for executives.
	•	Do not refer to the source (no “this slide shows…”, “described as…”, “according to…”, “in the materials…”).
    • Do not describe formatting, visuals, or how the information is presented (e.g., “this slide shows”, “photos of executives”, “cards list prior employers”).
    • Focus only on the substantive facts: average experience, tenure, industries, functional mix.
    • Phrase as direct factual statements suitable for an executive summary.
    • Never mention photos, slides, graphics, tables, cards, logos, layouts, pages, or any presentation elements.

	•	Avoid hedging and meta-language (no “it appears…”, “it seems…”, “the document indicates…”).

Banned phrases (hard prohibition)
	•	Do not use any of:
“described as”, “this slide shows”, “the slide shows”, “the slide indicates”, “headline says”, “this slide”, “photo shows”, “according to”, “per the”, “as per”, “the document states”, “the materials state”, “the source”.
	•	If these phrases appear in the source, rewrite into a direct factual statement.

Style & length
	•	Prefer short sentences. Remove marketing fluff; keep only verifiable facts.
	•	Use compact bullets only when multiple items are required (e.g., key metrics, customer stats).
	•	No citations, clause numbers, or page refs in the output.

Warranties & Indemnities Clauses
You are an expert in extracting legal provisions from Share Purchase Agreements (SPAs) and Management Warranty Deeds (MWDs). Identify the precise clause and sub-clause numbers, and relevant Schedules/Parts/Sections, when prompted, for the following categories:

Fundamental Warranties:
These usually cover title to shares, capacity/authority to enter into the agreement, ownership of the seller’s shares, ability to sell the shares free from encumbrances, due authorization. Fundamental Warranties also includes, but not limited to, Title Warranties. If the term “Fundamental Warranties” is not expressly used, treat these warranties as the Fundamental warranties. 

General Warranties:
These typically cover operational/business warranties such as financial statements, contracts, assets, IP, employees, compliance, litigation, etc. If not labelled, identify the main section in the SPA or MWD that sets out the bulk of business warranties.

Tax Warranties:
These are specific warranties related to tax compliance, tax liabilities, filings, disputes, or position of the target group. They may appear in a dedicated tax schedule or section of the warranties. 

Tax Indemnity:
Usually a separate indemnity clause, sometimes called “Tax Covenant,” often providing that the seller indemnifies the buyer for pre-completion tax liabilities. If the term “Tax Indemnity” is not expressly used, treat these tax indemnities/covenants as the Tax Indemnity.

Summarized Answer:"""
        try:
            response = self.client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            answer = self._extract_text_from_response(response)
            logger.debug(f"Raw summarized answer response: {answer[:200]}...")
            logger.info(f"Summarized answer generated: {answer}")
            return answer
        except Exception as e:
            logger.error(f"Summarized answer generation failed: {str(e)}")
            return "Information not found in the provided documents"

    def generate_explanation(self, prompt: str, verbatim_answer: str, context_chunks: List[dict], context_pages: dict) -> str:
        """Generate an evidence-based explanation for the answer.

        Args:
            prompt: The user query.
            verbatim_answer: The generated answer to the query.
            context_chunks: List of document chunks with metadata (e.g., text, section_title, key_terms).
            context_pages: Dictionary of full page context (key: doc_type::page:num, value: page content).

        Returns:
            str: Evidence-based explanation supporting the answer or explaining why information is absent.
        """
        system_prompt = """
    You are an expert in extracting evidence-based explanations from transaction documents (e.g., Share Purchase Agreements, CIMs, Term Sheets) to support a given answer to a specific query. Your role is to provide a concise, textual explanation that directly supports the answer or explains why information is absent if the answer indicates it was not found, using only the provided context and aligning with the query's intent.

    Instructions:
    - Analyze the query to understand its intent (e.g., seeking specific facts, terms, conditions, or obligations) and tailor the explanation to address that intent precisely.
    - If the answer contains substantive information (e.g., names, dates, amounts, clauses, or terms), extract verbatim text or specific references (e.g., clause numbers like "Clause 9.2", section titles like "Section 9: Representations", schedule references like "Schedule A", or defined terms like "Purchase Price") from `context_chunks` or `context_pages` that match the query and answer.
    - Quote exact text from the context, preserving original wording and formatting, and format citations as: [Clause X.X / Section X / Schedule X]: "exact quoted text".
    - Mention only the specific clauses, sections, or schedules directly tied to the generated answer, using phrases like ‘as mentioned in [Clause X.X]’ or ‘as stated in [Section X]’. Do not include unrelated or additional context.    - If the answer indicates information was not found, explain why by citing specific sections, clauses, or terms searched in the context or noting the absence of relevant content.
    - The explanation must be distinct from the answer and directly demonstrate the match between the query, answer, and context.
    - If the answer indicates information was not found (e.g., "Information not found in the provided documents", "not available", "no data"), explain why by citing specific sections, clauses, or terms in the context that were searched but lacked the required information, or note the absence of matching terms or relevant content (e.g., "No terms related to [query topic] found").
    - Always provide a non-empty explanation in plain text when an answer is provided: if the answer is generated, support it with evidence from the context; if not generated (i.e., indicates absence), provide an evidence-based rationale for the absence.
    - Stick strictly to the provided context; do not hallucinate, invent, or assume any information not present in `context_chunks` or `context_pages`.
    - Do not paraphrase, interpret, or infer beyond the provided context.
    - Do not mention page numbers, document names, or metadata (e.g., "from the document").
    - Do not include commentary like "this confirms", "this supports", or "this justifies".
    - Do not repeat the *answer* in the explanation. 
    - Keep the explanation concise (50–150 words) yet comprehensive, typically 1-3 sentences, focusing on the most direct supporting evidence or absence rationale from the context.
    """
        user_prompt = f"""
    You are given a generated answer to a query. Your task is to provide a textual explanation from the provided documents that directly supports the answer or explains why the information is absent if the answer indicates it was not found, aligning with the query's intent.

    Search only the following:
    1. Full Document Context:
    {context_pages}
    2. Retrieved Chunks:
    {context_chunks}
    3. Query:
    {prompt}
    4. Generated Answer:
    {verbatim_answer}

    Extraction Guidelines:
    - Based on the query's intent, extract exact text or specific references (e.g., clause numbers, section titles, schedules, defined terms) that match the query and generated answer, showing the direct connection.
    - Mention only the specific clauses, sections, or schedules directly tied to the generated answer, using phrases like ‘as mentioned in [Clause X.X]’ or ‘as stated in [Section X]’. Do not include unrelated or additional context.    - If the answer indicates information was not found, explain why by citing specific sections, clauses, or terms searched in the context or noting the absence of relevant content.
    - If the answer indicates information was not found, explain why by citing specific sections, clauses, or terms searched in the context or noting the absence of relevant content.
    - Keep the explanation concise (50-150 words) and comprehensive, using only the provided context.
    - Do not hallucinate, invent, or assume any information not in the context.
    - Do not mention page numbers, document names, or metadata.
    - Do not add commentary like "this supports the answer" or "this confirms".
    - Return a plain text explanation.

    Supporting Explanation:
    """
        try:
            response = self.client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            answer = self._extract_text_from_response(response)
            logger.debug(f"Raw explanation response: {answer[:200]}...")
            if not answer or answer.strip() == "":
                logger.warning("Empty explanation generated; returning fallback message.")
                return "No specific evidence found in the provided context."
            logger.info(f"Generated explanation: {answer[:100]}...")
            return answer
        except Exception as e:
            logger.error(f"Explanation generation failed: {str(e)}")
            return "No specific evidence found in the provided documents"

    def generate_fallback_response(self, prompt: str, context_documents: List[dict], collection_id: str, explanation_needed: bool = False, prompt_type: Optional[str] = None) -> LLMResponse:
        """
        Generate a response for the fallback agent using full document text, including both answer and explanation.

        Args:
            prompt: User's query
            context_documents: List of documents with text and metadata
            explanation_needed: Whether to include an explanation
            prompt_type: "summarize" or "verbatim" to control response style
            collection_id: Weaviate collection ID for page selection

        Returns:
            Dictionary with verbatim_answer, explanation, page_numbers, and page_scores
        """
        documents_text = "\n\n".join(
            f"File: {doc.get('filename', 'N/A')}\nFull Text: {doc.get('text', '')}"
            for doc in context_documents
        ) or "No document text provided."

        # Extract page numbers from context_documents
        page_numbers = sorted(list(set(
            page for doc in context_documents
            for page in (doc.get("page_numbers", []) if isinstance(doc.get("page_numbers"), list) else [doc.get("page_numbers")] if isinstance(doc.get("page_numbers"), int) else [])
        )))

        # Convert documents to context_pages format
        context_pages = {}
        for doc in context_documents:
            filename = doc.get('filename', 'N/A')
            pages = doc.get("page_numbers", [])
            if isinstance(pages, int):
                pages = [pages]
            text = doc.get('text', '')
            for page in pages:
                context_pages[f"{filename}::page:{page}"] = text

        if prompt_type == "summarize":
            verbatim_answer = self._generate_fallback_summarized_answer(prompt, context_documents, documents_text)
        else:
            verbatim_answer = self._generate_fallback_verbatim_answer(prompt, context_documents, documents_text)
        
        explanation = None
        if explanation_needed:
            explanation = self.generate_fallback_explanation(prompt, verbatim_answer, context_documents, documents_text)
        
        return LLMResponse(
            verbatim_answer=verbatim_answer,
            explanation=explanation,
            source=None
        )

    def _generate_fallback_verbatim_answer(self, prompt: str, context_documents: List[dict], documents_text: str) -> str:
        """Generate the verbatim answer for the query using provided document context."""
        system_prompt = """You are an expert at extracting exact text from documents. Follow these instructions:

1. Extract the exact answer from the provided documents that directly answers the query.
2. Quote the text verbatim, preserving original wording, punctuation, and formatting.
3. If the question requires sentence completion or fill-in-the-blank, complete it using the exact matching text from the documents.
4. If options are provided in the question, select the correct option using the exact phrasing from the documents.
5. If multiple relevant sections exist, select the most precise and concise match.
6. If no exact match is found, return an empty string.
7. Do not paraphrase, summarize, interpret, or add any external information.
8. Always provide the response strictly in English — if the input is in another language, translate the response into English.
9. Return the answer in plain text format only.

Guidelines:
- Verbatim Answer Only: Provide a concise, standalone factual statement or direct completion as required by the query.
- Sentence Completion: If the query contains a sentence to complete, do so using exact matching text.
- Use document text to extract precise and targeted details. Always prioritize content that is most relevant to the query.

Always follow HTML Formatting Guidelines:
- Output must be in **basic HTML format only** in string.
- Allowed tags: <p>, <i>, <u>.
- Use <p> for paragraphs and lists.
- Use <i> for italic text where present in the original.
- Use line breaks (\n) inside the same paragraph if requires.
- Do not use <html>, <head>, <body>, <div>, <span>, or CSS/JavaScript.
- Do not add any extra structure, metadata, or attributes inside tags.
- Do not use any special character unicodes.
- Ensure the HTML is clean and minimal — only wrap the extracted answer text.

"""
        user_prompt = f"""Context Information:
1. ### Full Document Context:
{documents_text}
2. ### Documents Metadata:
{context_documents}

Question: {prompt}

Instructions:
Based on the above context, extract the exact text that answers the question. Follow these rules:
- Use the precise wording from the documents.
- Do not paraphrase or summarize.
- If the question asks to complete a sentence or fill in the blank, do so using the exact matching text.
- If options are provided, complete the question with the correct option using verbatim text.
- Return only the final answer as plain text.
"""
        try:
            response = self.fallback_client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            answer = self._extract_text_from_response(response)
            logger.debug(f"Raw fallback verbatim answer response: {answer[:200]}...")
            logger.info(f"Fallback verbatim answer generated: {answer}")
            return answer
        except Exception as e:
            logger.error(f"Fallback verbatim answer generation failed: {str(e)}")
            return ""

    def _generate_fallback_summarized_answer(self, prompt: str, context_documents: List[dict], documents_text: str) -> str:
        """Generate a summarized answer for the query using provided document context."""
        system_prompt = """You are an expert in summarizing financial and legal documents for executive teams. Your task is to generate concise, business-ready executive summaries from sources such as CIMs, SPAs and Warranty Deed. Follow these strict instructions:
           1. Provide an accurate and concise summary that answers the query strictly based on the provided context.
           2. Do not paraphrase—extract the exact relevant content directly from the document.
           3. Ensure the answer includes everything explicitly asked in the query (e.g., complete-the-sentence requests, specific word limits, clause references, etc.).
           4. If the query requires a specific format (e.g., complete a sentence, limit to 30 words), adhere to it strictly.
           5. Use only the information available in the 'documents_text'. Do not rely on external knowledge or make assumptions.
           6. If the answer is not found in the document, respond with: "Information not found in the provided documents."
           7. Always provide the response strictly in English — if the input is in another language, translate the response into English.
		   8. Ensure the first letter of the output is capitalized, even if the source text begins with a lowercase word.
           9. Keep the tone clear and professional. Return the answer in plain text format only.

           Always follow HTML Formatting Guidelines:
           - Output must be in **basic HTML format only** in string.
           - Allowed tags: <p>, <i>, <u>.
           - Use <p> for paragraphs and lists.
           - Use <i> for italic text where present in the original.
           - Use line breaks (\n) inside the same paragraph if requires.
           - Do not use <html>, <head>, <body>, <div>, <span>, or CSS/JavaScript.
           - Do not add any extra structure, metadata, or attributes inside tags.
           - Do not use any special character unicodes.
           - Ensure the HTML is clean and minimal — only wrap the extracted answer text.

           Omit Missing Data Commentary
            •	Only summarize facts that are explicitly available in the source material.
            •	Do not mention or speculate on missing information.
            •	If a requested detail (e.g., headquarters, revenue split) is not stated, simply omit it and continue summarizing what is available.
            •   If the query is descriptive or narrative (e.g., business model, product description, customers, management team, M&A activity): a) summarize only what is explicitly available; b) If part of the requested detail is missing, omit it silently and continue with what is present; and c) Do not say “not found”, “not available”, or “not provided” for missing details.
            •	Write in a direct, declarative style suitable for executives.
            •	Ensure the first word of the response starts with a capital letter.
            •	Keep the response concise and within the requested word limit.
           """
        user_prompt = f"""Context Information:

1. ### Full Document Context:
{documents_text}

2. ### Documents Metadata:
{context_documents}

### Query:
{prompt}

Instructions:
- Use only the information available in the 'Full Document Context'.
- Answer the question exactly as asked, without paraphrasing or rephrasing unless explicitly instructed.
- If the question specifies a word/character limit or asks to complete a sentence, follow it strictly.
- If the question provides a partial sentence, placeholder (e.g., "[...]"), or requires insertion of a clause/section reference:
 - Find the exact clause/section number or reference from the provided context.
 - Insert it directly into the sentence, replacing the placeholder exactly as shown.
 - Do not modify any other part of the provided text.
- Include all elements explicitly requested in the query (e.g., clause numbers, financial metrics, specific terms).
- If the query requests a table format, provide the answer strictly in table format with clear spacing and proper column separation.
 - Do not add any headings, explanatory text, or extra wording unless explicitly requested.
- Do not add hallucinated or assumed values for financials, clause numbers, schedules, or any other specific details.
 - If the requested information is not present, leave it blank or keep the placeholder as is.
- If no relevant information is found, return an empty string ("").
- Keep the answer clear, concise, and professional.
- Return the final answer in plain text only.

Voice & framing
	•	Write in a neutral, declarative voice for executives.
	•	Do not refer to the source (no “this slide shows…”, “described as…”, “according to…”, “in the materials…”).
    • Do not describe formatting, visuals, or how the information is presented (e.g., “this slide shows”, “photos of executives”, “cards list prior employers”).
    • Focus only on the substantive facts: average experience, tenure, industries, functional mix.
    • Phrase as direct factual statements suitable for an executive summary.
    • Never mention photos, slides, graphics, tables, cards, logos, layouts, pages, or any presentation elements.

	•	Avoid hedging and meta-language (no “it appears…”, “it seems…”, “the document indicates…”).

Banned phrases (hard prohibition)
	•	Do not use any of:
“described as”, “this slide shows”, “the slide shows”, “the slide indicates”, “headline says”, “this slide”, “photo shows”, “according to”, “per the”, “as per”, “the document states”, “the materials state”, “the source”.
	•	If these phrases appear in the source, rewrite into a direct factual statement.

Style & length
	•	Prefer short sentences. Remove marketing fluff; keep only verifiable facts.
	•	Use compact bullets only when multiple items are required (e.g., key metrics, customer stats).
	•	No citations, clause numbers, or page refs in the output.

Warranties & Indemnities Clauses
You are an expert in extracting legal provisions from Share Purchase Agreements (SPAs) and Management Warranty Deeds (MWDs). Identify the precise clause and sub-clause numbers, and relevant Schedules/Parts/Sections, when prompted, for the following categories:

Fundamental Warranties:
These usually cover title to shares, capacity/authority to enter into the agreement, ownership of the seller’s shares, ability to sell the shares free from encumbrances, due authorization. Fundamental Warranties also includes, but not limited to, Title Warranties. If the term “Fundamental Warranties” is not expressly used, treat these warranties as the Fundamental warranties. 

General Warranties:
These typically cover operational/business warranties such as financial statements, contracts, assets, IP, employees, compliance, litigation, etc. If not labelled, identify the main section in the SPA or MWD that sets out the bulk of business warranties.

Tax Warranties:
These are specific warranties related to tax compliance, tax liabilities, filings, disputes, or position of the target group. They may appear in a dedicated tax schedule or section of the warranties. 

Tax Indemnity:
Usually a separate indemnity clause, sometimes called “Tax Covenant,” often providing that the seller indemnifies the buyer for pre-completion tax liabilities. If the term “Tax Indemnity” is not expressly used, treat these tax indemnities/covenants as the Tax Indemnity.

Summarized Answer:"""
        try:
            response = self.fallback_client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            answer = self._extract_text_from_response(response)
            logger.debug(f"Raw fallback summarized answer response: {answer[:200]}...")
            logger.info(f"Fallback summarized answer generated: {answer}")
            return answer
        except Exception as e:
            logger.error(f"Fallback summarized answer generation failed: {str(e)}")
            return "Information not found in the provided documents"

    def generate_fallback_explanation(self, prompt: str, verbatim_answer: str, context_documents: List[dict], documents_text: str) -> str:
        """Generate an evidence-based explanation for the fallback answer.

        Args:
            prompt: The user query.
            verbatim_answer: The generated answer to the query.
            context_documents: List of documents with metadata (e.g., doc_type, text, page_numbers).
            documents_text: Concatenated text of all documents for context.

        Returns:
            str: Evidence-based explanation supporting the answer or explaining why information is absent.
        """
        system_prompt = """
    You are an expert in extracting evidence-based explanations from transaction documents (e.g., Share Purchase Agreements, CIMs, Term Sheets) to support a given answer to a specific query. Your role is to provide a concise, textual explanation that directly supports the answer or explains why information is absent if the answer indicates it was not found, using only the provided context and aligning with the query's intent.

    Instructions:
    - Analyze the query to understand its intent (e.g., seeking specific facts, terms, conditions, or obligations) and tailor the explanation to address that intent precisely.
    - If the answer contains substantive information (e.g., names, dates, amounts, clauses, or terms), extract verbatim text or specific references (e.g., clause numbers like "Clause 9.2", section titles like "Section 9: Representations", schedule references like "Schedule A", or defined terms like "Purchase Price") from `context_documents` or `documents_text` that match the query and answer.
    - Quote exact text from the context, preserving original wording and formatting, and format citations as: [Clause X.X / Section X / Schedule X]: "exact quoted text".
    - Mention only the specific clauses, sections, or schedules directly tied to the generated answer, using phrases like ‘as mentioned in [Clause X.X]’ or ‘as stated in [Section X]’. Do not include unrelated or additional context.    - If the answer indicates information was not found, explain why by citing specific sections, clauses, or terms searched in the context or noting the absence of relevant content.
    - The explanation must be distinct from the answer and directly demonstrate the match between the query, answer, and context.
    - If the answer indicates information was not found (e.g., "Information not found in the provided documents", "not available", "no data"), explain why by citing specific sections, clauses, or terms in the context that were searched but lacked the required information, or note the absence of matching terms or relevant content (e.g., "No terms related to [query topic] found").
    - Always provide a non-empty explanation in plain text when an answer is provided: if the answer is generated, support it with evidence from the context; if not generated (i.e., indicates absence), provide an evidence-based rationale for the absence.
    - Stick strictly to the provided context; do not hallucinate, invent, or assume any information not present in `context_documents` or `documents_text`.
    - Do not paraphrase, interpret, or infer beyond the provided context.
    - Do not mention page numbers, document names, or metadata (e.g., "from the document").
    - Do not include commentary like "this confirms", "this supports", or "this justifies".
    - Do not repeat the answer in the explanation.
    - Keep the explanation concise yet comprehensive, typically 1-3 sentences, focusing on the most direct supporting evidence or absence rationale from the context.
            """
        user_prompt = f"""
    You are given a generated answer to a query. Your task is to provide a textual explanation from the provided documents that directly supports the answer or explains why the information is absent if the answer indicates it was not found, aligning with the query's intent.

    Search only the following:
    1. Full Document Context:
    {documents_text}
    2. Documents Metadata:
    {context_documents}
    3. Query:
    {prompt}
    4. Generated Answer:
    {verbatim_answer}

    Extraction Guidelines:
    - Based on the query's intent, extract exact text or specific references (e.g., clause numbers, section titles, schedules, defined terms) that match the query and generated answer, showing the direct connection.
    - Mention only the specific clauses, sections, or schedules directly tied to the generated answer, using phrases like ‘as mentioned in [Clause X.X]’ or ‘as stated in [Section X]’. Do not include unrelated or additional context.    - If the answer indicates information was not found, explain why by citing specific sections, clauses, or terms searched in the context or noting the absence of relevant content.
    - If the answer indicates information was not found, explain why by citing specific sections, clauses, or terms searched in the context or noting the absence of relevant content.
    - Keep the explanation concise (50-150 words) and comprehensive, using only the provided context.
    - Do not hallucinate, invent, or assume any information not in the context.
    - Do not mention page numbers, document names, or metadata.
    - Do not add commentary like "this supports the answer" or "this confirms".
    - Return a plain text explanation.

    Supporting Explanation:
    """
        try:
            response = self.fallback_client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            answer = self._extract_text_from_response(response)
            logger.debug(f"Raw fallback explanation response: {answer[:200]}...")
            if not answer or answer.strip() == "":
                logger.warning("Empty fallback explanation generated; returning fallback message.")
                return "No specific evidence found in the provided context."
            logger.info(f"Fallback explanation generated: {answer[:100]}...")
            return answer
        except Exception as e:
            logger.error(f"Fallback explanation generation failed: {str(e)}")
            return "No specific evidence found in the provided context"

    def format_fallback_response(self, response: LLMResponse) -> dict:
        """
        Format the fallback LLM response into the required structure.
        """
        verbatim_answer = response.verbatim_answer or ""
        explanation = response.explanation or "No specific evidence found in the provided context."
        formatted_answer = verbatim_answer if verbatim_answer else ""
        formatted_explanation = explanation if explanation else "No specific evidence found in the provided context."
        return {
            "final_answer": formatted_answer,
            "final_answer_explanation": formatted_explanation,
            "final_confidence_score": 1.0,
            "page_numbers": [],
            "page_scores": {}
        }

    def _parse_structured_response(self, response: str, explanation_needed: bool) -> dict:
        """
        Parse the LLM's structured JSON response into verbatim_answer and explanation.

        Args:
            response: Raw response from the LLM
            explanation_needed: Whether an explanation is required

        Returns:
            Dictionary with verbatim_answer and explanation
        """
        try:
            json_match = json.loads(response)
            verbatim_answer = json_match.get("verbatim_answer", "")
            explanation = json_match.get("explanation", "No specific evidence found in the provided text.") if explanation_needed else None
            return {"verbatim_answer": verbatim_answer, "explanation": explanation if explanation else None}
        except json.JSONDecodeError:
            logger.warning("LLM response is not valid JSON. Attempting to parse manually.")
            verbatim_answer = ""
            explanation = None if explanation_needed else ""
            lines = response.split("\n")
            current_section = None
            for line in lines:
                line = line.strip()
                if any(line.lower().startswith(prefix) for prefix in [
                    "verbatim answer:", "- verbatim answer:", "**verbatim answer:**"
                ]):
                    current_section = "verbatim"
                    for prefix in ["verbatim answer:", "- verbatim answer:", "**verbatim answer:**"]:
                        if line.lower().startswith(prefix):
                            verbatim_answer = line[len(prefix):].strip("* ")
                            break
                elif explanation_needed and any(line.lower().startswith(prefix) for prefix in [
                    "explanation:", "- explanation:", "**explanation:**"
                ]):
                    current_section = "explanation"
                    for prefix in ["explanation:", "- explanation:", "**explanation:**"]:
                        if line.lower().startswith(prefix):
                            explanation = line[len(prefix):].strip("* ")
                            break
                elif current_section == "verbatim" and line:
                    verbatim_answer += " " + line.strip()
                elif current_section == "explanation" and explanation_needed and line:
                    explanation += " " + line.strip()
            if not verbatim_answer:
                verbatim_answer = ""
            if explanation_needed and not explanation:
                explanation = "No specific evidence found in the provided text."
            return {"verbatim_answer": verbatim_answer, "explanation": explanation if explanation else None}

    def combine_per_doc_responses(
        self,
        prompt: str,
        per_doc_answers: List[str],
        per_doc_explanations: Optional[List[str]],
        explanation_needed: bool,
        prompt_type: str
    ) -> Dict:
        """
        Combine per-document responses into a final accurate answer using the original prompt as the query.
        """
        if prompt_type == "summarize":
            system_prompt = """You are an expert in combining and summarizing responses from multiple documents to provide an accurate, concise answer to the query.
    Follow these instructions:
    1. Use the provided per-document answers (and explanations if available) as references.
    2. Generate a final summarized answer that directly addresses the original query.
    3. Ensure completeness, accuracy, and relevance without adding external information.
    4. If the query requires a specific format (e.g., table, sentence completion), adhere to it.
    5. If no relevant information across documents, return "Information not found in the provided documents."
    6. For the final explanation (if needed): Combine verbatim evidence from per-doc explanations without paraphrasing.
    7. Output in JSON format with keys: "final_answer" and "final_answer_explanation" (if needed)."""
        else:  # verbatim
            system_prompt = """You are an expert at combining exact extracts from multiple documents to answer the query verbatim.
    Follow these instructions:
    1. Use the provided per-document answers as references to extract and combine exact text that answers the query.
    2. Preserve original wording, punctuation, and formatting.
    3. If multiple documents provide relevant text, select and concatenate the most precise matches.
    4. If no exact match across documents, return an empty string.
    5. Do not paraphrase or add interpretations.
    6. For the final explanation (if needed): Combine verbatim evidence from per-doc explanations.
    7. Output in JSON format with keys: "final_answer" and "final_answer_explanation" (if needed)."""

        references_text = "\n\n".join([
            f"Document {i+1} Answer: {ans}" for i, ans in enumerate(per_doc_answers)
        ])
        if explanation_needed and per_doc_explanations:
            references_text += "\n\n" + "\n\n".join([
                f"Document {i+1} Explanation: {exp}" for i, exp in enumerate(per_doc_explanations)
            ])

        user_prompt = f"""
        Original Query: {prompt}

        References from Documents:
        {references_text}

        Combine the references to generate the final accurate response to the query.
        Return JSON:
        {{
          "final_answer": "<combined_answer>",
          "final_answer_explanation": "<combined_explanation>"  # Only if needed
        }}
        """
        try:
            response = self.client.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            response_content = self._extract_text_from_response(response)
            logger.debug(f"Raw combined response: {response_content[:200]}...")
            parsed = self.parse_ai_message_to_json(response_content)
            if "error" in parsed:
                logger.error(f"Failed to parse combined response: {parsed['error']}")
                return {
                    "final_answer": "Information not found in the provided documents",
                    "final_answer_explanation": "No specific evidence found." if explanation_needed else None
                }
            logger.info(f"Parsed combined response: {parsed}")
            final_answer = parsed.get("final_answer", "")
            final_explanation = parsed.get("final_answer_explanation", "No specific evidence found.") if explanation_needed else None
            return {
                "final_answer": final_answer,
                "final_answer_explanation": final_explanation
            }
        except Exception as e:
            logger.error(f"Combined response generation failed: {str(e)}")
            return {
                "final_answer": "Information not found in the provided documents",
                "final_answer_explanation": "No specific evidence found." if explanation_needed else None
            }