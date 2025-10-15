import os
import json
import time
import random
import shutil
import re
import html as htmllib
from typing import List, Dict, Optional
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import redis as rqredis
from sqlalchemy.orm import Session
from app.core.weaviate_client import WeaviateClient
from app.core.embedding import EmbeddingService
from app.core.llm import LLMService
from app.core.validate_agents import ValidationSystem
from app.utils.file_handler import DocumentLoader
from app.logging_config import logger
from app.db.database import SessionLocal
from app.db.operations import (
    ProjectOperations,
    DocumentOperations,
    FieldResultOperations,
    QueueOperations
)

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", 86400 * 7))
MAX_CONCURRENT_FIELDS = int(os.getenv("MAX_CONCURRENT_FIELDS", 5))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

sync_redis = rqredis.from_url(REDIS_URL)


def retry_api_call(func, *args, max_retries=MAX_RETRIES, **kwargs):
    """Retry API call on rate limit errors with exponential backoff."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e).lower()
            if '429' in error_str or 'rate limit' in error_str or 'throttling' in error_str:
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Rate limit hit, retrying attempt {attempt+1}/{max_retries} after {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
            else:
                raise
    raise Exception("Max retries exceeded due to rate limiting")


def init_services(model: str = None, reasoning_effort: str = None):
    """Initialize all required services"""
    model = (model or os.getenv("LLM_MODEL_GPT_5", "gpt-5")).lower()
    reasoning_effort = (reasoning_effort or os.getenv("REASONING_EFFORT", "low")).lower()
    
    document_loader = DocumentLoader()
    weaviate_client = WeaviateClient(
        url=os.getenv("WEAVIATE_URL", "http://localhost:8080"),
        document_loader=document_loader
    )
    embedding_service = EmbeddingService(
        api_key=os.getenv("LITELLM_MASTER_KEY"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
        min_chunk_size=int(os.getenv("MIN_CHUNK_SIZE", "100")),
        llm_model=model,
        chunk_size=int(os.getenv("CHUNK_SIZE", 1000)),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", 200))
    )
    llm_service = LLMService(
        model=model,
        reasoning_effort=reasoning_effort,
        fallback_model=os.getenv("LLM_MODEL_GPT_5_MINI", "gpt-4.1-mini").lower(),
        page_model=os.getenv("LLM_MODEL_GPT_4_MINI", "gpt-4.1-mini").lower()
    )
    validation_system = ValidationSystem(
        llm_model=model,
        reasoning_effort=reasoning_effort,
        max_iterations=int(os.getenv("VALIDATION_MAX_ITERATIONS", 3))
    )
    
    return {
        "weaviate_client": weaviate_client,
        "embedding_service": embedding_service,
        "llm_service": llm_service,
        "validation_system": validation_system,
        "document_loader": document_loader
    }


def update_project_status(project_id: str, status: str, **kwargs):
    """Update project status in both Redis and PostgreSQL"""
    try:
        # Update in PostgreSQL
        db = SessionLocal()
        try:
            ProjectOperations.update_project_status(
                db, project_id, status, **kwargs
            )
        finally:
            db.close()
        
        # Also update in Redis for backward compatibility
        project_data_json = sync_redis.get(f"project:{project_id}")
        if project_data_json:
            project_data = json.loads(project_data_json)
            project_data["status"] = status
            project_data["updated_at"] = datetime.now().isoformat()
            project_data.update(kwargs)
            sync_redis.set(
                f"project:{project_id}",
                json.dumps(project_data),
                ex=REDIS_TTL_SECONDS
            )
            logger.info(f"Updated project {project_id} status to {status}")
    except Exception as e:
        logger.error(f"Failed to update project status: {str(e)}")


def update_document_status(project_id: str, doc_id: str, status: str, **kwargs):
    """Update document status in both Redis and PostgreSQL"""
    try:
        # Update in PostgreSQL
        db = SessionLocal()
        try:
            DocumentOperations.update_document_status(
                db, doc_id, status, **kwargs
            )
        finally:
            db.close()
        
        # Also update in Redis for backward compatibility
        project_data_json = sync_redis.get(f"project:{project_id}")
        if project_data_json:
            project_data = json.loads(project_data_json)
            for doc in project_data["documents"]:
                if doc["doc_id"] == doc_id:
                    doc["status"] = status
                    break
            project_data["updated_at"] = datetime.now().isoformat()
            sync_redis.set(
                f"project:{project_id}",
                json.dumps(project_data),
                ex=REDIS_TTL_SECONDS
            )
            logger.info(f"Updated document {doc_id} status to {status}")
    except Exception as e:
        logger.error(f"Failed to update document status: {str(e)}")


def process_document_chunks(project_id: str, doc_id: str, doc_name: str, file_path: str, services: Dict) -> int:
    """Process document and store chunks in Weaviate"""
    try:
        logger.info(f"Processing document {doc_name} for project {project_id}")
        
        embedding_service = services["embedding_service"]
        weaviate_client = services["weaviate_client"]
        
        # Read file content
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # Process document and create chunks
        chunks = embedding_service.process_document_from_content(file_content, doc_name)
        
        if not chunks:
            logger.warning(f"No chunks extracted from {doc_name}")
            return False
        
        # Generate embeddings
        chunk_texts = [chunk["text"] for chunk in chunks]
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        embeddings = retry_api_call(embedding_service.generate_embeddings, chunk_texts)
        
        # Insert into Weaviate
        logger.info(f"Inserting {len(chunks)} chunks into Weaviate")
        retry_api_call(
            weaviate_client.insert_chunks,
            project_id,
            doc_id,
            doc_name,
            chunks,
            embeddings
        )
        
        logger.info(f"Successfully processed {len(chunks)} chunks for {doc_name}")
        
        # Update document with chunk count in PostgreSQL
        update_document_status(
            project_id, doc_id, "processing",
            chunks_count=len(chunks),
            page_count=max([c.get("page_number", 0) for c in chunks]) if chunks else 0
        )
        
        return len(chunks)
        
    except Exception as e:
        logger.error(f"Error processing document {doc_name}: {str(e)}")
        return 0


def process_single_field(
    project_id: str,
    doc_id: str,
    field_config: Dict,
    services: Dict
) -> Dict:
    """Process a single field extraction for a document"""
    field_name = field_config["field_name"]
    prompt = field_config["prompt"]
    model = field_config.get("model", "gpt-5").lower()
    mode = field_config.get("mode", "low").lower()
    prompt_type = field_config.get("type", "verbatim")
    
    logger.info(f"Processing field '{field_name}' for doc {doc_id}")
    
    try:
        weaviate_client = services["weaviate_client"]
        embedding_service = services["embedding_service"]
        llm_service = services["llm_service"]
        # Create a fresh ValidationSystem per field to ensure thread-safety
        validation_system = ValidationSystem(
            llm_model=model,
            reasoning_effort=mode,
            max_iterations=int(os.getenv("VALIDATION_MAX_ITERATIONS", 3))
        )
        
        # Generate query embedding
        query_embedding = retry_api_call(embedding_service.generate_prompt_embedding, prompt)
        
        # Search for relevant chunks
        search_results = retry_api_call(
            weaviate_client.search_similar,
            project_id=project_id,
            doc_id=doc_id,
            query_vector=query_embedding,
            query_text=prompt,
            limit=10,
            alpha=0.5
        )
        
        if not search_results:
            logger.warning(f"No relevant chunks found for field '{field_name}'")
            return {
                "field_name": field_name,
                "value": "Not found",
                "confidence": 0.0,
                "source_pages": [],
                "status": "completed",
                "error": "No relevant content found"
            }
        
        # Build context from search results
        context_chunks = []
        for result in search_results:
            context_chunks.append({
                "text": result["text"],
                "page_number": result["page_number"],
                "chunk_number": result["chunk_number"],
                "hybrid_score": result["hybrid_score"]
            })
        # logger.info(f"Context chunks: {context_chunks}")
        # Generate initial answer using LLM
        logger.info(f"Generating answer for field '{field_name}' using {model}")
        context_pages = {}  # Not using full pages for now
        initial_response = retry_api_call(
            llm_service.generate_rag_response,
            prompt,
            context_chunks,
            context_pages,
            project_id,
            explanation_needed=False,
            prompt_type=prompt_type,
        )

        # Extract initial answer/explanation robustly (handles pydantic or dict)
        try:
            if hasattr(initial_response, "model_dump"):
                _data = initial_response.model_dump()
            elif isinstance(initial_response, dict):
                _data = initial_response
            else:
                _data = {}
            initial_answer = _data.get("verbatim_answer") or getattr(initial_response, "verbatim_answer", "")
            initial_explanation = _data.get("explanation") or getattr(initial_response, "explanation", None)
            if not isinstance(initial_answer, str):
                initial_answer = str(initial_answer) if initial_answer is not None else ""
        except Exception:
            # Fallback safety
            initial_answer = str(initial_response) if initial_response else ""
            initial_explanation = None

        # Use validation system for iterative refinement with correct args
        validated_response = retry_api_call(
            validation_system.validate_and_improve,
            user_query=prompt,
            initial_answer=initial_answer,
            initial_explanation=initial_explanation,
            explanation_needed=False,
            prompt_type=prompt_type,
            chunks=context_chunks,
            pages=context_pages,
        )
        
        # Extract source pages
        source_pages = sorted(list(set([chunk["page_number"] for chunk in context_chunks[:3]])))
        # logger.info(f"Source pages: {source_pages}")
        # Build result with improved formatting
        def _clean_answer(raw: str) -> tuple[str, str]:
            """Return (plain_text, original_html_or_text).
            - If raw looks like "verbatim_answer='...'", extract inner.
            - Strip HTML tags for plain text, unescape entities, normalize spaces.
            """
            if raw is None:
                raw = ""
            if not isinstance(raw, str):
                raw = str(raw)
            # Extract from pattern like: verbatim_answer='...'
            m = re.search(r"verbatim_answer=['\"](.*?)['\"]", raw, re.DOTALL)
            if m:
                raw_inner = m.group(1)
            else:
                raw_inner = raw
            # Plain text: remove tags, unescape, normalize
            try:
                no_tags = re.sub(r"<[^>]+>", " ", raw_inner)
                unescaped = htmllib.unescape(no_tags)
                normalized = re.sub(r"\s+", " ", unescaped).strip()
            except Exception:
                normalized = raw_inner.strip()
            return normalized, raw_inner

        final_text_html = validated_response.get("final_answer", "")
        final_text, final_html_or_text = _clean_answer(final_text_html)
        final_explanation = validated_response.get("final_answer_explanation", "")

        result = {
            "field_name": field_name,
            "value": final_text,
            "answer_html": final_html_or_text,
            "explanation": final_explanation,
            "confidence": validated_response["final_confidence_score"],
            "source_pages": source_pages,
            "chunks": [
                {
                    "page": chunk["page_number"],
                    "text": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"],
                    "score": chunk["hybrid_score"]
                }
                for chunk in context_chunks[:3]
            ],
            "status": "completed"
        }
        
        logger.info(f"Completed field '{field_name}' with confidence {result['confidence']:.2f}")
        
        # Store field result in PostgreSQL
        db = SessionLocal()
        try:
            FieldResultOperations.create_field_result(
                db,
                document_id=doc_id,
                field_name=field_name,
                result_data={
                    "value": result["value"],
                    "answer_html": result.get("answer_html"),
                    "explanation": result.get("explanation"),
                    "confidence": result["confidence"],
                    "source_pages": result["source_pages"],
                    "chunks": result["chunks"],
                    "status": result["status"],
                    "model_used": model,
                    "reasoning_mode": mode
                }
            )
        finally:
            db.close()
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing field '{field_name}': {str(e)}")
        return {
            "field_name": field_name,
            "value": "Error",
            "confidence": 0.0,
            "source_pages": [],
            "status": "failed",
            "error": str(e)
        }


def process_document_fields(
    project_id: str,
    doc_id: str,
    fields_config: List[Dict],
    services: Dict
) -> Dict:
    """Process all fields for a document with concurrent execution"""
    logger.info(f"Processing {len(fields_config)} fields for document {doc_id}")
    logger.info(f"Field concurrency: MAX_CONCURRENT_FIELDS={MAX_CONCURRENT_FIELDS}")
    
    results = {}
    
    # Process fields concurrently
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FIELDS) as executor:
        futures_to_field = {}
        
        for field_config in fields_config:
            logger.info(f"Submitting field '{field_config['field_name']}' to thread pool")
            future = executor.submit(
                process_single_field,
                project_id,
                doc_id,
                field_config,
                services
            )
            futures_to_field[future] = field_config["field_name"]
        
        # Collect results
        completed = 0
        for future in as_completed(futures_to_field):
            field_name = futures_to_field[future]
            completed += 1
            
            try:
                result = future.result()
                results[field_name] = result
                logger.info(f"Completed field {completed}/{len(fields_config)}: {field_name} (thread={threading.current_thread().name})")
            except Exception as e:
                logger.error(f"Error processing field {field_name}: {str(e)}")
                results[field_name] = {
                    "field_name": field_name,
                    "value": "Error",
                    "confidence": 0.0,
                    "source_pages": [],
                    "status": "failed",
                    "error": str(e)
                }
    
    return results


def process_project(project_id: str):
    """
    Main worker function to process a project.
    Processes documents sequentially, fields concurrently.
    """
    logger.info(f"Starting project processing: {project_id}")
    
    try:
        # Get project data
        project_data_json = sync_redis.get(f"project:{project_id}")
        if not project_data_json:
            logger.error(f"Project {project_id} not found")
            return
        
        project_data = json.loads(project_data_json)
        documents = project_data["documents"]
        fields_config = project_data["fields_config"]
        
        # Update status to processing
        update_project_status(project_id, "processing")
        
        # Initialize services
        services = init_services()
        
        # Process each document sequentially
        all_results = {}
        processed_count = 0
        failed_count = 0
        
        for doc in documents:
            doc_id = doc["doc_id"]
            doc_name = doc["doc_name"]
            file_path = doc["file_path"]
            
            logger.info(f"Processing document {doc_name} ({processed_count + failed_count + 1}/{len(documents)})")
            
            try:
                # Update document status
                update_document_status(project_id, doc_id, "processing")
                
                # Step 1: Process and store document chunks
                start_time = time.time()
                chunks_count = process_document_chunks(
                    project_id,
                    doc_id,
                    doc_name,
                    file_path,
                    services
                )
                
                if chunks_count == 0:
                    logger.error(f"Failed to process chunks for {doc_name}")
                    update_document_status(
                        project_id, doc_id, "failed",
                        error_message="No chunks extracted from document"
                    )
                    failed_count += 1
                    continue
                
                # Step 2: Process all fields concurrently
                doc_results = process_document_fields(
                    project_id,
                    doc_id,
                    fields_config,
                    services
                )
                
                # Store results
                all_results[doc_id] = doc_results
                
                # Update Redis with results
                sync_redis.set(
                    f"project:{project_id}:results",
                    json.dumps(all_results),
                    ex=REDIS_TTL_SECONDS
                )
                
                # Update document status with processing time
                processing_time = time.time() - start_time
                update_document_status(
                    project_id, doc_id, "completed",
                    processing_time=processing_time
                )
                processed_count += 1
                
                # Update project progress
                update_project_status(
                    project_id,
                    "processing",
                    processed_documents=processed_count,
                    failed_documents=failed_count
                )
                
                logger.info(f"Completed document {doc_name}")
                
            except Exception as e:
                logger.error(f"Error processing document {doc_name}: {str(e)}")
                update_document_status(project_id, doc_id, "failed")
                failed_count += 1
                update_project_status(
                    project_id,
                    "processing",
                    processed_documents=processed_count,
                    failed_documents=failed_count
                )
        
        # Final status update
        final_status = "completed" if failed_count == 0 else "completed_with_errors"
        update_project_status(
            project_id,
            final_status,
            processed_documents=processed_count,
            failed_documents=failed_count
        )
        
        # Mark queue entry as completed in PostgreSQL
        db = SessionLocal()
        try:
            QueueOperations.complete_queue_entry(db, project_id, final_status)
        finally:
            db.close()
        
        # Cleanup temporary files
        temp_dir = project_data.get("temp_dir")
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
        
        logger.info(f"Project {project_id} processing completed: {processed_count} succeeded, {failed_count} failed")
        
    except Exception as e:
        logger.error(f"Fatal error processing project {project_id}: {str(e)}")
        update_project_status(project_id, "failed")
        raise
