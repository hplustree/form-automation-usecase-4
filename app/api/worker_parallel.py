"""
Parallel worker implementation for document and field processing.
This module provides separate worker functions for:
1. Document processing (chunks creation)
2. Field extraction (individual field processing)
"""

import os
import json
import time
import random
import uuid
from typing import Dict, Optional
from datetime import datetime
import redis as rqredis
from sqlalchemy.orm import Session
from rq import Queue, get_current_job
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
    DocumentQueueOperations,
    FieldQueueOperations
)
from app.db.models import FieldQueue, FieldResult

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", 86400 * 7))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

sync_redis = rqredis.from_url(REDIS_URL)

# Create separate queues for documents and fields
document_queue = Queue("documents", connection=sync_redis)
field_queue = Queue("fields", connection=sync_redis)


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


def process_document(document_id: str, project_id: str):
    """
    Worker function to process a single document.
    This function:
    1. Loads the document
    2. Creates chunks and embeddings
    3. Stores chunks in Weaviate
    4. Enqueues field extraction tasks
    """
    worker_id = str(uuid.uuid4())
    logger.info(f"[Worker {worker_id}] Starting document processing for {document_id}")
    
    db = SessionLocal()
    try:
        # Get document from database
        document = DocumentOperations.get_document(db, document_id)
        if not document:
            logger.error(f"Document {document_id} not found")
            return
        
        # Get project for field configurations
        project = ProjectOperations.get_project(db, project_id)
        if not project:
            logger.error(f"Project {project_id} not found")
            return
        
        # Update document status
        DocumentOperations.update_document_status(db, document_id, "processing")
        
        # Initialize services
        services = init_services()
        embedding_service = services["embedding_service"]
        weaviate_client = services["weaviate_client"]
        
        try:
            # Read file content
            with open(document.file_path, 'rb') as f:
                file_content = f.read()
            
            # Process document and create chunks
            logger.info(f"Creating chunks for document {document.doc_name}")
            chunks = embedding_service.process_document_from_content(
                file_content, 
                document.doc_name
            )
            
            if not chunks:
                logger.warning(f"No chunks extracted from {document.doc_name}")
                DocumentOperations.update_document_status(
                    db, document_id, "failed",
                    error_message="No chunks extracted from document"
                )
                DocumentQueueOperations.complete_document(
                    db, document_id, "failed",
                    error_message="No chunks extracted"
                )
                return
            
            # Generate embeddings
            chunk_texts = [chunk["text"] for chunk in chunks]
            logger.info(f"Generating embeddings for {len(chunks)} chunks")
            embeddings = retry_api_call(
                embedding_service.generate_embeddings, 
                chunk_texts
            )
            
            # Insert into Weaviate
            logger.info(f"Inserting {len(chunks)} chunks into Weaviate")
            retry_api_call(
                weaviate_client.insert_chunks,
                project_id,
                document_id,
                document.doc_name,
                chunks,
                embeddings
            )
            
            # Update document with chunk count and mark as chunks_ready (not completed yet)
            DocumentOperations.update_document_status(
                db, document_id, "processing",
                chunks_count=len(chunks),
                page_count=max([c.get("page_number", 0) for c in chunks]) if chunks else 0
            )
            
            # Mark document as completed in queue (for chunk processing)
            DocumentQueueOperations.complete_document(db, document_id, "completed")
            
            # Enqueue field extraction tasks for this document
            fields_config = project.fields_config
            for field_config in fields_config:
                FieldQueueOperations.enqueue_field(
                    db,
                    document_id=document_id,
                    project_id=project_id,
                    field_name=field_config["field_name"],
                    field_config=field_config,
                    priority=0,
                    depends_on_doc=True
                )
                
                # Also enqueue in RQ for processing
                field_queue.enqueue(
                    'app.api.worker_parallel.process_field',
                    args=(
                        document_id,
                        project_id,
                        field_config["field_name"],
                        field_config
                    ),
                    job_timeout=600,  # 10 minutes per field
                    result_ttl=REDIS_TTL_SECONDS
                )
            
            logger.info(f"Successfully processed document {document.doc_name} with {len(chunks)} chunks")
            logger.info(f"Enqueued {len(fields_config)} field extraction tasks")
            
        except Exception as e:
            logger.error(f"Error processing document {document.doc_name}: {str(e)}")
            DocumentOperations.update_document_status(
                db, document_id, "failed",
                error_message=str(e)
            )
            DocumentQueueOperations.complete_document(
                db, document_id, "failed",
                error_message=str(e)
            )
            raise
            
    finally:
        db.close()



def process_field(document_id: str, project_id: str, field_name: str, field_config: Dict):
    """
    Worker function to process a single field extraction.
    This function:
    1. Retrieves relevant chunks from Weaviate
    2. Performs field extraction using LLM
    3. Validates the result
    4. Saves the result to database immediately
    """
    worker_id = str(uuid.uuid4())
    logger.info(f"[Worker {worker_id}] Starting field extraction: {field_name} for document {document_id}")
    
    db = SessionLocal()
    try:
        # Get the field queue entry
        field_entry = db.query(FieldQueue).filter(
            FieldQueue.document_id == document_id,
            FieldQueue.field_name == field_name
        ).first()
        
        if field_entry:
            field_queue_id = field_entry.id
        else:
            field_queue_id = None
        
        # Initialize services with field-specific model config
        model = field_config.get("model", "gpt-5").lower()
        mode = field_config.get("mode", "low").lower()
        services = init_services(model, mode)
        
        weaviate_client = services["weaviate_client"]
        embedding_service = services["embedding_service"]
        llm_service = services["llm_service"]
        
        prompt = field_config["prompt"]
        prompt_type = field_config.get("type", "verbatim")
        
        try:
            # Generate query embedding
            query_embedding = retry_api_call(
                embedding_service.generate_prompt_embedding, 
                prompt
            )
            
            # Search for relevant chunks
            search_results = retry_api_call(
                weaviate_client.search_similar,
                project_id=project_id,
                doc_id=document_id,
                query_vector=query_embedding,
                query_text=prompt,
                limit=10,
                alpha=0.5
            )
            
            if not search_results:
                logger.warning(f"No relevant chunks found for field '{field_name}'")
                result = {
                    "field_name": field_name,
                    "value": "Not found",
                    "confidence": 0.0,
                    "source_pages": [],
                    "status": "completed",
                    "error": "No relevant content found"
                }
            else:
                # Build context from search results
                context_chunks = []
                for result in search_results:
                    context_chunks.append({
                        "text": result["text"],
                        "page_number": result["page_number"],
                        "chunk_number": result["chunk_number"],
                        "hybrid_score": result["hybrid_score"]
                    })
                
                # Generate initial answer using LLM
                logger.info(f"Generating answer for field '{field_name}' using {model}")
                context_pages = {}
                initial_response = retry_api_call(
                    llm_service.generate_rag_response,
                    prompt,
                    context_chunks,
                    context_pages,
                    project_id,
                    explanation_needed=False,
                    prompt_type=prompt_type,
                )
                
                # Extract and validate answer
                validation_system = ValidationSystem(
                    llm_model=model,
                    reasoning_effort=mode,
                    max_iterations=int(os.getenv("VALIDATION_MAX_ITERATIONS", 3))
                )
                
                # Extract initial answer
                if hasattr(initial_response, "model_dump"):
                    _data = initial_response.model_dump()
                elif isinstance(initial_response, dict):
                    _data = initial_response
                else:
                    _data = {}
                    
                initial_answer = _data.get("verbatim_answer", "")
                initial_explanation = _data.get("explanation", None)
                
                # Validate and improve
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
                source_pages = sorted(list(set([
                    chunk["page_number"] for chunk in context_chunks[:3]
                ])))
                
                # Clean and format answer
                import re
                import html as htmllib
                
                final_text_html = validated_response.get("final_answer", "")
                if final_text_html:
                    # Extract from pattern like: verbatim_answer='...'
                    m = re.search(r"verbatim_answer=['\"](.*?)['\"]", final_text_html, re.DOTALL)
                    if m:
                        final_text_html = m.group(1)
                    
                    # Plain text: remove tags, unescape, normalize
                    no_tags = re.sub(r"<[^>]+>", " ", final_text_html)
                    unescaped = htmllib.unescape(no_tags)
                    final_text = re.sub(r"\s+", " ", unescaped).strip()
                else:
                    final_text = ""
                    final_text_html = ""
                
                result = {
                    "field_name": field_name,
                    "value": final_text,
                    "answer_html": final_text_html,
                    "explanation": validated_response.get("final_answer_explanation", ""),
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
            
            # Save result to database immediately
            logger.info(f"Saving field result for '{field_name}' with confidence {result.get('confidence', 0):.2f}")
            
            FieldResultOperations.create_field_result(
                db,
                document_id=document_id,
                field_name=field_name,
                result_data={
                    "value": result["value"],
                    "answer_html": result.get("answer_html"),
                    "explanation": result.get("explanation"),
                    "confidence": result.get("confidence", 0),
                    "source_pages": result.get("source_pages", []),
                    "chunks": result.get("chunks", []),
                    "status": result["status"],
                    "model_used": model,
                    "reasoning_mode": mode
                }
            )
            
            # Mark field as completed in queue
            if field_queue_id:
                FieldQueueOperations.complete_field(db, field_queue_id, "completed")
            
            # Check if all fields for this document are completed
            check_and_update_document_status(db, document_id, project_id)
            
            # Update project progress
            check_and_update_project_status(db, project_id)
            
            logger.info(f"Successfully completed field '{field_name}' for document {document_id}")
            
        except Exception as e:
            logger.error(f"Error processing field '{field_name}': {str(e)}")
            
            # Save error result
            FieldResultOperations.create_field_result(
                db,
                document_id=document_id,
                field_name=field_name,
                result_data={
                    "value": "Error",
                    "confidence": 0.0,
                    "source_pages": [],
                    "status": "failed",
                    "error": str(e),
                    "model_used": model,
                    "reasoning_mode": mode
                }
            )
            
            # Mark field as failed in queue
            if field_queue_id:
                FieldQueueOperations.complete_field(
                    db, field_queue_id, "failed",
                    error_message=str(e)
                )
            
            # Check if all fields for this document are completed (even with errors)
            check_and_update_document_status(db, document_id, project_id)
            
            raise
            
    finally:
        db.close()


def check_and_update_document_status(db: Session, document_id: str, project_id: str):
    """
    Check if all fields for a document are completed and update document status accordingly.
    """
    try:
        # Get document and project
        document = DocumentOperations.get_document(db, document_id)
        project = ProjectOperations.get_project(db, project_id)
        
        if not document or not project:
            return
        
        # Skip if document is already completed or failed
        if document.status in ["completed", "failed"]:
            return
        
        # Get expected number of fields from project config
        expected_fields = len(project.fields_config)
        
        # Get all field results for this document
        field_results = db.query(FieldResult).filter(
            FieldResult.document_id == document_id
        ).all()
        
        # Count completed and failed fields
        completed_fields = sum(1 for fr in field_results if fr.status == "completed")
        failed_fields = sum(1 for fr in field_results if fr.status == "failed")
        total_processed = completed_fields + failed_fields
        
        # Check if all fields are processed
        if total_processed >= expected_fields:
            if failed_fields == 0:
                # All fields completed successfully
                DocumentOperations.update_document_status(
                    db, document_id, "completed"
                )
                logger.info(f"Document {document_id} completed: all {completed_fields} fields processed successfully")
            else:
                # Some fields failed
                DocumentOperations.update_document_status(
                    db, document_id, "completed",
                    error_message=f"{failed_fields} field(s) failed extraction"
                )
                logger.warning(f"Document {document_id} completed with errors: {completed_fields} succeeded, {failed_fields} failed")
        else:
            # Still processing fields
            logger.debug(f"Document {document_id}: {total_processed}/{expected_fields} fields processed")
            
    except Exception as e:
        logger.error(f"Error updating document status: {str(e)}")


def check_and_update_project_status(db: Session, project_id: str):
    """
    Check if all documents and fields are processed and update project status.
    """
    try:
        project = ProjectOperations.get_project(db, project_id)
        if not project:
            return
        
        # Get all documents for the project
        documents = DocumentOperations.get_project_documents(db, project_id)
        
        # Check document processing status
        total_docs = len(documents)
        completed_docs = sum(1 for doc in documents if doc.status in ["completed", "completed_with_errors"])
        failed_docs = sum(1 for doc in documents if doc.status == "failed")
        
        # Check field processing status
        total_fields = total_docs * len(project.fields_config)
        completed_fields = 0
        failed_fields = 0
        
        for doc in documents:
            field_results = db.query(FieldResult).filter(
                FieldResult.document_id == doc.id
            ).all()
            
            for field_result in field_results:
                if field_result.status == "completed":
                    completed_fields += 1
                elif field_result.status == "failed":
                    failed_fields += 1
        
        # Update project status
        if completed_fields + failed_fields == total_fields:
            # All fields processed
            if failed_fields == 0 and failed_docs == 0:
                status = "completed"
            else:
                status = "completed_with_errors"
            
            ProjectOperations.update_project_status(
                db, project_id, status,
                processed_documents=completed_docs,
                failed_documents=failed_docs
            )
            
            logger.info(f"Project {project_id} completed: {completed_docs}/{total_docs} docs, {completed_fields}/{total_fields} fields")
        else:
            # Still processing
            ProjectOperations.update_project_status(
                db, project_id, "processing",
                processed_documents=completed_docs,
                failed_documents=failed_docs
            )
            
    except Exception as e:
        logger.error(f"Error updating project status: {str(e)}")


def process_project_parallel(project_id: str):
    """
    Main entry point for parallel project processing.
    This function enqueues all documents for parallel processing.
    """
    logger.info(f"Starting parallel project processing: {project_id}")
    
    db = SessionLocal()
    try:
        # Get project from database
        project = ProjectOperations.get_project(db, project_id)
        if not project:
            logger.error(f"Project {project_id} not found")
            return
        
        # Update project status to processing
        ProjectOperations.update_project_status(db, project_id, "processing")
        
        # Get all documents for the project
        documents = DocumentOperations.get_project_documents(db, project_id)
        
        logger.info(f"Enqueueing {len(documents)} documents for parallel processing")
        
        # Enqueue each document for parallel processing
        for document in documents:
            # Add to document queue in database
            DocumentQueueOperations.enqueue_document(
                db,
                document_id=document.id,
                project_id=project_id,
                priority=0
            )
            
            # Enqueue in RQ for processing
            document_queue.enqueue(
                'app.api.worker_parallel.process_document',
                args=(document.id, project_id),
                job_timeout=1800,  # 30 minutes per document
                result_ttl=REDIS_TTL_SECONDS
            )
            
            logger.info(f"Enqueued document {document.doc_name} for processing")
        
        logger.info(f"Successfully enqueued all documents for project {project_id}")
        
    except Exception as e:
        logger.error(f"Error in parallel project processing: {str(e)}")
        ProjectOperations.update_project_status(db, project_id, "failed", error_message=str(e))
        raise
    finally:
        db.close()
