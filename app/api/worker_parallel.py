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
import asyncio
import concurrent.futures
from typing import Dict, Optional, List
from datetime import datetime
import redis as rqredis
from sqlalchemy.orm import Session
from rq import Queue, get_current_job
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from app.core.weaviate_client import WeaviateClient
from app.core.embedding import EmbeddingService
from app.core.llm import LLMService
from app.core.validate_agents import ValidationSystem
from app.utils.file_handler import DocumentLoader
from app.logging_config import logger
from app.db.database import SessionLocal
from app.utils.worker_manager import WorkerManager
from app.db.operations import (
    ProjectOperations,
    DocumentOperations,
    FieldResultOperations,
    DocumentQueueOperations,
    FieldQueueOperations
)
from app.db.models import Document, FieldQueue, FieldResult
from collections import defaultdict

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", 86400 * 7))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))

sync_redis = rqredis.from_url(REDIS_URL)

# Create separate queues for documents and fields
document_queue = Queue("documents", connection=sync_redis)
field_queue = Queue("fields", connection=sync_redis)


def get_queue_for_project(project_id: str, queue_type: str = "documents") -> Queue:
    """Get a project-specific queue for hierarchical processing."""
    queue_name = f"{queue_type}:{project_id}"
    return Queue(queue_name, connection=sync_redis)


def get_queue_for_document(project_id: str, document_id: str) -> Queue:
    """Get a document-specific field queue for hierarchical processing."""
    queue_name = f"fields:{project_id}:{document_id}"
    return Queue(queue_name, connection=sync_redis)


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


def extract_page_numbers(chunk: Dict) -> List[int]:
    """Extract page numbers from a chunk, handling both single and multiple page formats."""
    page_numbers = chunk.get("page_numbers", chunk.get("page_number", []))
    
    if isinstance(page_numbers, int):
        return [page_numbers]
    elif isinstance(page_numbers, list):
        return [int(p) for p in page_numbers if p is not None]
    else:
        return []


def extract_page_numbers_from_keys(page_keys: List[str], doc_id: str) -> List[int]:
    """
    Extract page numbers from page keys.
    Page keys are in format: {doc_id}::page:{page_number}
    """
    pages = []
    for key in page_keys:
        try:
            # Extract page number from key format: doc_id::page:123
            if "::page:" in key:
                page_str = key.split("::page:")[-1]
                pages.append(int(page_str))
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to extract page number from key {key}: {e}")
    return sorted(pages)


def transform_page_scores(page_scores: Dict[str, float], doc_id: str) -> Dict[int, float]:
    """
    Transform page scores from key format to page number format.
    Input: {"{doc_id}::page:1": 0.95, "{doc_id}::page:2": 0.87}
    Output: {1: 0.95, 2: 0.87}
    """
    transformed = {}
    for key, score in page_scores.items():
        try:
            if "::page:" in key:
                page_num = int(key.split("::page:")[-1])
                transformed[page_num] = score
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to transform page score for key {key}: {e}")
    return transformed


def process_document(
    project_id: str,
    document_id: str,
    is_regeneration: bool = False,
    field_names: list = None,
    custom_prompts: dict = None,
    **kwargs
):
    # Update document status to 'analysing' at the start of processing
    db = SessionLocal()
    try:
        if is_regeneration:
            DocumentOperations.update_document_status(
                db, document_id, "generating",
                status_message="Re-analyzing document and preparing chunks..."
            )
        else:
            DocumentOperations.update_document_status(
                db, document_id, "analysing",
                status_message="Analyzing document and preparing chunks..."
            )
    except Exception as e:
        logger.error(f"Error updating document status: {str(e)}")
    finally:
        db.close()
    """
    Process a document by extracting text, splitting into chunks, generating embeddings, and storing in Weaviate.
    
    Args:
        project_id: The ID of the project
        document_id: The ID of the document to process
        is_regeneration: Whether this is a regeneration of an existing document
        field_names: Optional list of field names to process (if None, all fields will be processed)
        custom_prompts: Optional dictionary of custom prompts to override JSON config {field_name: {prompt, type_of_prompt, explanation_needed}}
        **kwargs: Additional arguments (e.g., timeout from RQ)
    """
    import time
    import psutil
    from datetime import datetime
    
    # Initialize timing and process tracking
    start_time = time.time()
    process = psutil.Process()
    worker_id = os.getenv("WORKER_ID", str(uuid.uuid4())[:8])  # Use env worker ID or generate one
    worker_type = os.getenv("WORKER_TYPE", "document")
    use_hierarchical = os.getenv("USE_HIERARCHICAL_WORKERS", "false").lower() == "true"
    
    db = SessionLocal()
    worker_manager = None
    
    try:
        # Get document from database - ensure we're using the correct ID fields
        logger.info(f"[Worker {worker_id}] Fetching document {document_id} from project {project_id}")
        document = DocumentOperations.get_document(db, document_id)
        if not document:
            error_msg = f"Document {document_id} not found in project {project_id}"
            logger.error(f"[Worker {worker_id}] {error_msg}")
            # Try to update document status if possible
            try:
                DocumentOperations.update_document_status(
                    db, document_id, "failed",
                    error_message=error_msg
                )
                db.commit()
            except Exception as e:
                logger.error(f"[Worker {worker_id}] Failed to update document status: {str(e)}")
            return
            
        logger.info(f"[Worker {worker_id}] Found document: {document.doc_name}")
        
        # Get project for field configurations
        project = ProjectOperations.get_project(db, project_id)
        
        # Get project for field configurations
        project = ProjectOperations.get_project(db, project_id)
        if not project:
            error_msg = f"Project {project_id} not found in database"
            logger.error(f"[Worker {worker_id}] {error_msg}")
            DocumentOperations.update_document_status(
                db, document_id, "failed",
                error_message=error_msg
            )
            db.commit()
            return
        
        # Update document status
        DocumentOperations.update_document_status(db, document_id, "analysing")

        # Initialize services
        services = init_services()
        embedding_service = services["embedding_service"]
        weaviate_client = services["weaviate_client"]
        
        try:
            if is_regeneration:
                # For regeneration, skip chunk creation and embedding generation
                logger.info(f"[Worker {worker_id}] Regeneration mode: Skipping chunk creation and embedding generation")
                logger.info(f"[Worker {worker_id}] Verifying document file exists: {document.file_path}")
                
                # Verify the document exists
                if not os.path.exists(document.file_path):
                    error_msg = f"Error processing document {document.doc_name}: File not found at path: {document.file_path}"
                    logger.error(error_msg)
                    
                    # Check if we have any successful field results before failing
                    try:
                        if 'db' in locals() and db:
                            # First check if we have any completed fields
                            completed_fields = db.query(FieldResult).filter(
                                FieldResult.document_id == document_id,
                                FieldResult.status == 'completed'
                            ).count()
                            
                            if completed_fields > 0:
                                # We have some successful fields, let's check the full status
                                logger.info(f"[Worker {worker_id}] Document has {completed_fields} completed fields, checking status...")
                                check_and_update_document_status(db, document_id, project_id)
                                logger.info(f"[Worker {worker_id}] Document status updated based on field completion")
                            else:
                                # No fields completed, mark as failed
                                logger.error(f"[Worker {worker_id}] No fields completed, marking document as failed")
                                DocumentOperations.update_document_status(
                                    db, document_id, "failed",
                                    error_message=error_msg[:1000]
                                )
                                DocumentQueueOperations.complete_document(
                                    db, document_id, "failed",
                                    error_message=error_msg[:1000]
                                )
                                db.commit()
                        else:
                            logger.error(f"[Worker {worker_id}] Could not update document status - DB connection not available")
                    except Exception as db_err:
                        logger.error(f"[Worker {worker_id}] Error in error handler: {str(db_err)}")
                        # As a last resort, try to set status to failed
                        try:
                            if 'db' in locals() and db:
                                DocumentOperations.update_document_status(
                                    db, document_id, "failed",
                                    error_message=f"Critical error: {str(db_err)[:1000]}"
                                )
                                db.commit()
                        except:
                            pass
                    
                    logger.error("="*80 + "\n")
                    # Only raise if it's a critical error, otherwise let the status update complete
                    raise
                
                # Check if document has existing chunks in Weaviate
                logger.info(f"[Worker {worker_id}] Checking for existing chunks in Weaviate...")
                has_chunks = weaviate_client.has_existing_chunks(project_id, document_id)
                logger.info(f"[Worker {worker_id}] Existing chunks found: {has_chunks}")
                
                if not has_chunks:
                    error_msg = "No existing chunks found for regeneration"
                    logger.error(f"[Worker {worker_id}] {error_msg}")
                    logger.error(f"[Worker {worker_id}] Cannot regenerate fields without existing chunks")
                    
                    # Check if we have any successful field results before failing
                    try:
                        if 'db' in locals() and db:
                            # First check if we have any completed fields
                            completed_fields = db.query(FieldResult).filter(
                                FieldResult.document_id == document_id,
                                FieldResult.status == 'completed'
                            ).count()
                            
                            if completed_fields > 0:
                                # We have some successful fields, let's check the full status
                                logger.info(f"[Worker {worker_id}] Document has {completed_fields} completed fields, checking status...")
                                check_and_update_document_status(db, document_id, project_id)
                                logger.info(f"[Worker {worker_id}] Document status updated based on field completion")
                            else:
                                # No fields completed, mark as failed
                                logger.error(f"[Worker {worker_id}] No fields completed, marking document as failed")
                                DocumentOperations.update_document_status(
                                    db, document_id, "failed",
                                    error_message=error_msg[:1000]
                                )
                                DocumentQueueOperations.complete_document(
                                    db, document_id, "failed",
                                    error_message=error_msg[:1000]
                                )
                                db.commit()
                        else:
                            logger.error(f"[Worker {worker_id}] Could not update document status - DB connection not available")
                    except Exception as db_err:
                        logger.error(f"[Worker {worker_id}] Error in error handler: {str(db_err)}")
                        # As a last resort, try to set status to failed
                        try:
                            if 'db' in locals() and db:
                                DocumentOperations.update_document_status(
                                    db, document_id, "failed",
                                    error_message=f"Critical error: {str(db_err)[:1000]}"
                                )
                                db.commit()
                        except:
                            pass
                    
                    logger.error("="*80 + "\n")
                    # Only raise if it's a critical error, otherwise let the status update complete
                    if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
                        # For timeouts, try to complete the document with error status
                        try:
                            if 'db' in locals() and db:
                                DocumentQueueOperations.complete_document(
                                    db, document_id, "failed",
                                    error_message=f"Processing timed out: {str(e)}"
                                )
                                db.commit()
                        except Exception as timeout_err:
                            logger.error(f"[Worker {worker_id}] Error completing document on timeout: {str(timeout_err)}")
                    # Re-raise the original exception
                    raise
                
                logger.info(f"[Worker {worker_id}] Document has existing chunks, proceeding with field regeneration")
                # Get chunk count for logging
                chunk_count = weaviate_client.get_chunk_count(project_id, document_id)
                logger.info(f"[Worker {worker_id}] Found {chunk_count} existing chunks for this document")
                
            else:
                # Original processing for new documents
                # Get the file path from the document
                file_path = document.file_path
                logger.info(f"Processing new document at path: {file_path}")
                
                # Check if file exists
                if not os.path.exists(file_path):
                    error_msg = f"File not found at path: {file_path}"
                    logger.error(f"Current working directory: {os.getcwd()}")
                    
                    # Log the contents of the temp_files directory for debugging
                    temp_files_dir = "/app/temp_files"
                    if os.path.exists(temp_files_dir):
                        logger.error(f"Contents of {temp_files_dir}: {os.listdir(temp_files_dir)}")
                    else:
                        logger.error(f"Directory not found: {temp_files_dir}")
                    logger.error(error_msg)
                    DocumentOperations.update_document_status(
                        db, document_id, "failed",
                        error_message=error_msg
                    )
                    DocumentQueueOperations.complete_document(
                        db, document_id, "failed",
                        error_message=error_msg
                    )
                    return
                    
                # Read file content
                with open(document.file_path, 'rb') as f:
                    file_content = f.read()
                
                # Process document and create chunks
                logger.info(f"Creating chunks for new document {document.doc_name}")
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
                
                # Store chunks in Weaviate
                logger.info(f"[Worker {worker_id}] Storing {len(chunks)} chunks in Weaviate")
                try:
                    stored_count = weaviate_client.insert_chunks(
                        project_id=project_id,
                        doc_id=document_id,
                        doc_name=document.doc_name,
                        chunks=chunks,
                        embeddings=embeddings
                    )
                    logger.info(f"[Worker {worker_id}] Successfully stored {stored_count} chunks in Weaviate")
                except Exception as e:
                    error_msg = f"Error updating document status: {str(e)}"
                    # Safely get error code if it exists
                    error_code = getattr(e, 'code', None)
                    if error_code is not None:
                        error_msg += f" (code: {error_code})"
                    logger.error(error_msg, exc_info=True)
                    raise RuntimeError(error_msg) from e
                
                # Update document with chunk count and page count
                # Get the maximum page number from all chunks
                max_page_number = 0
                for chunk in chunks:
                    # Handle both 'page_numbers' (list) and 'page_number' (int) for backward compatibility
                    page_numbers = chunk.get("page_numbers")
                    if isinstance(page_numbers, list) and page_numbers:
                        max_page_number = max(max_page_number, max(page_numbers))
                    else:
                        # Fallback to single page_number if page_numbers is not available
                        page_number = chunk.get("page_number", 0)
                        max_page_number = max(max_page_number, page_number)
                
                DocumentOperations.update_document_status(
                    db,
                    document_id,
                    status="processing",
                    chunks_count=len(chunks),
                    page_count=max_page_number if chunks else 0
                )
                if is_regeneration:
                    logger.info(f"Successfully prepared document {document.doc_name} for regeneration")
                else:
                    logger.info(f"Successfully processed document {document.doc_name} with {len(chunks)} chunks")
            
            # Mark document as chunks_ready in queue (for chunk processing)
            DocumentQueueOperations.complete_document(db, document_id, "chunks_ready")
            
            # Get the requested field names from either the function parameter or project metadata
            requested_fields = field_names or []
            if not requested_fields and project.metadata and 'requested_fields' in project.metadata:
                requested_fields = project.metadata.get('requested_fields', [])
            
            # Get the fields configuration from the project
            fields_config = project.fields_config or []
            
            # Update document status to 'generating' when chunks are ready and fields are loaded
            DocumentOperations.update_document_status(
                db, document_id, "generating",
                status_message=f"Chunks ready. Starting field extraction for {len(fields_config)} fields..."
            )
            
            # Process field extraction tasks for this document
            
            # If no specific fields are requested, process all fields
            if not requested_fields:
                logger.info(f"No field filtering applied, processing all {len(fields_config)} fields")
            else:
                # Filter to only include requested fields that exist in the config
                fields_config = [
                    field for field in fields_config 
                    if field and field.get('field_name') in requested_fields
                ]
                logger.info(f"Filtered to {len(fields_config)} requested fields out of {len(project.fields_config)} total fields")
            
            if not fields_config:
                warning_msg = f"No valid fields found to process for document {document_id}"
                logger.warning(f"[Worker {worker_id}] {warning_msg}")
                
                # Log available fields for debugging
                if project.fields_config:
                    available_fields = [f.get('field_name', 'unnamed') for f in project.fields_config if f and f.get('field_name')]
                    logger.warning(f"[Worker {worker_id}] Available fields in project: {', '.join(available_fields)}")
                
                # Mark document as completed since there are no fields to process
                DocumentOperations.update_document_status(
                    db, document_id, "completed",
                    error_message=warning_msg
                )
                DocumentQueueOperations.complete_document(
                    db, document_id, "completed",
                    error_message=warning_msg
                )
                logger.warning(f"[Worker {worker_id}] Document marked as completed with warning: {warning_msg}")
                return
            
            # Process fields in parallel using ThreadPoolExecutor
            max_field_workers = int(os.getenv("MAX_CONCURRENT_FIELDS", "5"))
            logger.info(f"[Worker {worker_id}] Processing {len(fields_config)} fields in parallel (max {max_field_workers} concurrent)")
            
            field_results = {}
            field_errors = {}
            field_start_time = time.time()
            
            # Prepare field configurations with custom prompts
            for field_config in fields_config:
                if not field_config or not field_config.get('field_name'):
                    continue
                    
                field_name = field_config["field_name"]
                
                # Override field config with custom prompts if provided
                if custom_prompts and field_name in custom_prompts:
                    custom_prompt_data = custom_prompts[field_name]
                    if custom_prompt_data.get('prompt'):
                        field_config['prompt'] = custom_prompt_data['prompt']
                        logger.info(f"[Worker {worker_id}] Using custom prompt for field '{field_name}'")
                    if custom_prompt_data.get('type_of_prompt'):
                        field_config['typeOfPrompt'] = custom_prompt_data['type_of_prompt']
                        field_config['prompt_type'] = custom_prompt_data['type_of_prompt']
                    if custom_prompt_data.get('explanation_needed') is not None:
                        field_config['explanationNeeded'] = custom_prompt_data['explanation_needed']
                        field_config['explanation_needed'] = custom_prompt_data['explanation_needed']
                    if custom_prompt_data.get('model'):
                        field_config['model'] = custom_prompt_data['model']
                        logger.info(f"[Worker {worker_id}] Using custom model '{custom_prompt_data['model']}' for field '{field_name}'")
            
            # Process fields in parallel
            with ThreadPoolExecutor(max_workers=max_field_workers) as field_executor:
                # Submit all field processing tasks
                future_to_field = {}
                for field_config in fields_config:
                    if not field_config or not field_config.get('field_name'):
                        logger.warning(f"Skipping invalid field config: {field_config}")
                        continue
                        
                    field_name = field_config["field_name"]
                    field_type = field_config.get('type', 'unknown')
                    field_model = field_config.get('model', 'default')
                    
                    logger.info(f"[Worker {worker_id}] Submitting field extraction for '{field_name}' (Type: {field_type}, Model: {field_model})")
                    
                    # Add field to database queue
                    try:
                        FieldQueueOperations.enqueue_field(
                            db,
                            document_id=document_id,
                            project_id=project_id,
                            field_name=field_name,
                            field_config=field_config,
                            priority=0,
                            depends_on_doc=True
                        )
                        
                        # Submit field for parallel processing
                        try:
                            future = field_executor.submit(
                                process_field,
                                document_id,
                                project_id,
                                field_name,
                                field_config
                            )
                            future_to_field[future] = field_name
                            logger.info(f"[Worker {worker_id}] Enqueued field extraction for '{field_name}'")
                        except Exception as e:
                            logger.error(f"[Worker {worker_id}] Failed to submit field '{field_name}': {str(e)}", exc_info=True)
                            field_errors[field_name] = str(e)
                            
                            # Update field status in database immediately on submission failure
                            try:
                                field_entry = db.query(FieldQueue).filter(
                                    FieldQueue.document_id == document_id,
                                    FieldQueue.field_name == field_name
                                ).first()
                                if field_entry:
                                    FieldQueueOperations.complete_field(
                                        db, field_entry.id, "failed",
                                        error_message=f"Failed to submit for processing: {str(e)}"
                                    )
                                    db.commit()
                            except Exception as db_error:
                                logger.error(f"Failed to update field status: {str(db_error)}")
                    except Exception as e:
                        logger.error(f"[Worker {worker_id}] Failed to submit field '{field_name}': {str(e)}", exc_info=True)
                        field_errors[field_name] = str(e)
                
                # Process completed field extractions with timeout handling
                done, not_done = concurrent.futures.wait(
                    future_to_field.keys(),
                    timeout=7200,  # 2 hour overall timeout for all fields
                    return_when=concurrent.futures.FIRST_EXCEPTION
                )
                
                # Process completed fields
                for future in done:
                    field_name = future_to_field[future]
                    try:
                        if future.exception() is not None:
                            raise future.exception()
                            
                        result = future.result()
                        field_results[field_name] = result
                        logger.info(f"[Worker {worker_id}] Successfully processed field '{field_name}'")
                    except concurrent.futures.TimeoutError as te:
                        error_msg = f"Timeout processing field '{field_name}': {str(te)}"
                        logger.error(f"[Worker {worker_id}] {error_msg}")
                        field_errors[field_name] = error_msg
                        # Don't mark as failed yet, just log the timeout
                    except Exception as e:
                        error_msg = f"Error processing field '{field_name}': {str(e)}"
                        logger.error(f"[Worker {worker_id}] {error_msg}", exc_info=True)
                        field_errors[field_name] = error_msg
                        # Update field status in database
                        try:
                            field_entry = db.query(FieldQueue).filter(
                                FieldQueue.document_id == document_id,
                                FieldQueue.field_name == field_name
                            ).first()
                            if field_entry:
                                FieldQueueOperations.complete_field(
                                    db, field_entry.id, "failed",
                                    error_message=error_msg
                                )
                                db.commit()
                        except Exception as db_error:
                            logger.error(f"Failed to update field status: {str(db_error)}")
            
            # Check if we have any successful field results
            if field_results:
                logger.info(f"[Worker {worker_id}] Successfully processed {len(field_results)} fields, {len(field_errors)} failed")
                
                # Update document status based on field processing results
                try:
                    if 'db' in locals() and db:
                        # First check if we have any completed fields
                        completed_fields = db.query(FieldResult).filter(
                            FieldResult.document_id == document_id,
                            FieldResult.status == 'completed'
                        ).count()
                        
                        if completed_fields > 0:
                            # We have some successful fields, update status based on field completion
                            logger.info(f"[Worker {worker_id}] Document has {completed_fields} completed fields, checking status...")
                            check_and_update_document_status(db, document_id, project_id)
                            logger.info(f"[Worker {worker_id}] Document status updated based on field completion")
                            
                            # If we had a timeout but processed some fields, don't mark as failed
                            if any(isinstance(e, concurrent.futures.TimeoutError) for e in field_errors.values()):
                                logger.warning(f"[Worker {worker_id}] Timeout occurred but {completed_fields} fields were processed successfully")
                                return {
                                    "document_id": document_id,
                                    "status": "completed_with_errors",
                                    "error": "Some fields timed out but others were processed successfully",
                                    "elapsed_time": time.time() - start_time
                                }
                except Exception as db_err:
                    logger.error(f"[Worker {worker_id}] Error checking document status: {str(db_err)}")
            
            # If we get here, either all fields failed or there was a critical error
            if not field_results and field_errors:
                error_msg = f"All {len(field_errors)} fields failed processing. First error: {next(iter(field_errors.values()))}"
                logger.error(f"[Worker {worker_id}] {error_msg}")
                
                # Update document status to failed
                try:
                    if 'db' in locals() and db:
                        DocumentOperations.update_document_status(
                            db, document_id, "failed",
                            error_message=error_msg[:1000]
                        )
                        db.commit()
                except Exception as db_err:
                    logger.error(f"[Worker {worker_id}] Failed to update document status: {str(db_err)}")
                
                return {
                    "document_id": document_id,
                    "status": "failed",
                    "error": error_msg,
                    "elapsed_time": time.time() - start_time
                }
            
            # Process completed field extractions
            for future in as_completed(future_to_field):
                field_name = future_to_field[future]
                try:
                    result = future.result(timeout=600)  # 10 minutes timeout per field
                    field_results[field_name] = result
                    logger.info(f"[Worker {worker_id}] Successfully processed field '{field_name}'")
                except Exception as e:
                    error_msg = f"Error processing field '{field_name}': {str(e)}"
                    logger.error(f"[Worker {worker_id}] {error_msg}")
                    field_errors[field_name] = error_msg
                    # Update field status in database
                    try:
                        field_entry = db.query(FieldQueue).filter(
                            FieldQueue.document_id == document_id,
                            FieldQueue.field_name == field_name
                        ).first()
                        if field_entry:
                            FieldQueueOperations.complete_field(
                                db, field_entry.id, "failed",
                                error_message=error_msg
                            )
                            db.commit()
                    except Exception as db_error:
                        logger.error(f"Failed to update field status: {str(db_error)}")
            
            # Calculate field processing results
            total_fields = len(fields_config)
            successful_fields = len(field_results)
            failed_fields = len(field_errors)
            field_elapsed = time.time() - field_start_time
            
            logger.info(f"[Worker {worker_id}] Field processing completed in {field_elapsed:.2f}s: "
                      f"{successful_fields}/{total_fields} successful, {failed_fields} failed")
            
            # Update document status based on field processing results
            elapsed_time = time.time() - start_time
            if not future_to_field and not field_results:
                # No fields were processed at all
                error_msg = "No fields were processed"
                logger.error(f"[Worker {worker_id}] {error_msg}")
                DocumentOperations.update_document_status(
                    db, document_id, "failed",
                    error_message=error_msg
                )
                db.commit()
            elif failed_fields == total_fields and total_fields > 0:
                DocumentOperations.update_document_status(
                    db, document_id, "completed_with_errors",
                    error_message=f"All {failed_fields} fields failed to process"
                )
            elif failed_fields > 0:
                DocumentOperations.update_document_status(
                    db, document_id, "completed_with_errors",
                    error_message=f"{failed_fields} out of {total_fields} fields failed"
                )
            else:
                DocumentOperations.update_document_status(
                    db, document_id, "completed"
                )
            
            # Complete document in queue
            DocumentQueueOperations.complete_document(
                db, document_id, 
                "completed_with_errors" if failed_fields > 0 else "completed"
            )
            
            db.commit()
            logger.info(f"[Worker {worker_id}] Document processing completed in {elapsed_time:.2f} seconds")
            logger.info(f"[Worker {worker_id}] Memory usage: {process.memory_info().rss / 1024 / 1024:.2f}MB")
            logger.info(f"[Worker {worker_id}] {'=' * 30} DOCUMENT PROCESSING COMPLETED {'=' * 30}")
            
            # Return processing results
            return {
                "document_id": document_id,
                "status": "completed_with_errors" if failed_fields > 0 else "completed",
                "fields_processed": successful_fields,
                "fields_failed": failed_fields,
                "processing_time": elapsed_time
            }
            
        except Exception as e:
            # Get elapsed time safely
            try:
                elapsed_time = time.time() - start_time
                mem_usage = f"{process.memory_info().rss / 1024 / 1024:.2f}MB"
                doc_name = getattr(document, 'doc_name', 'unknown')
            except Exception as log_err:
                elapsed_time = -1
                mem_usage = "unknown"
                doc_name = 'unknown'
                logger.error(f"[Worker {worker_id}] Error getting diagnostic info: {str(log_err)}")
            
            error_msg = f"Error processing document {doc_name}: {str(e)}"
            logger.error(error_msg)
            
            # Check if we have any successful field results before failing
            try:
                if 'db' in locals() and db:
                    # First check if we have any completed fields
                    completed_fields = db.query(FieldResult).filter(
                        FieldResult.document_id == document_id,
                        FieldResult.status == 'completed'
                    ).count()
                    
                    if completed_fields > 0:
                        # We have some successful fields, update status based on field completion
                        logger.info(f"[Worker {worker_id}] Document has {completed_fields} completed fields, checking status...")
                        check_and_update_document_status(db, document_id, project_id)
                        logger.info(f"[Worker {worker_id}] Document status updated based on field completion")
                        
                        # If this was a timeout, don't raise the error since we've processed some fields
                        if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
                            logger.warning(f"[Worker {worker_id}] Timeout occurred but {completed_fields} fields were processed successfully")
                            return {
                                "document_id": document_id,
                                "status": "completed_with_errors",
                                "error": str(e),
                                "elapsed_time": elapsed_time
                            }
                    else:
                        # No fields completed, mark as failed
                        logger.error(f"[Worker {worker_id}] No fields completed, marking document as failed")
                        DocumentOperations.update_document_status(
                            db, document_id, "failed",
                            error_message=error_msg[:1000]
                        )
                        DocumentQueueOperations.complete_document(
                            db, document_id, "failed",
                            error_message=error_msg[:1000]
                        )
                        db.commit()
                else:
                    logger.error(f"[Worker {worker_id}] Could not update document status - DB connection not available")
            except Exception as db_err:
                logger.error(f"[Worker {worker_id}] Error in error handler: {str(db_err)}")
                # As a last resort, try to set status to failed
                try:
                    if 'db' in locals() and db:
                        DocumentOperations.update_document_status(
                            db, document_id, "failed",
                            error_message=f"Critical error in error handler: {str(db_err)[:1000]}"
                        )
                        db.commit()
                except Exception as final_err:
                    logger.error(f"[Worker {worker_id}] Final error handler failed: {str(final_err)}")
            
            logger.error("="*80 + "\n")
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
        # Update document status to 'analysing' at the start of processing
        DocumentOperations.update_document_status(
            db, document_id, "generating", 
            status_message="Document is being analyzed and chunked"
        )
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
        prompt_type = (
            field_config.get("typeOfPrompt")
            or field_config.get("prompt_type")
            or field_config.get("type", "verbatim")
        )
        explanation_needed = field_config.get(
            "explanationNeeded",
            field_config.get("explanation_needed", True)
        )

        logger.debug(
            f"[Worker {worker_id}] Prompt for '{field_name}' (type={prompt_type}, explanation_needed={explanation_needed}): "
            f"{prompt[:200]}{'...' if len(prompt) > 200 else ''}"
        )
        
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
                limit=20,
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
                    # Handle both single page_number and page_numbers list
                    page_nums = result.get("page_numbers", result.get("page_number"))
                    if isinstance(page_nums, int):
                        page_nums = [page_nums]
                    elif not isinstance(page_nums, list):
                        page_nums = []
                    
                    context_chunks.append({
                        "text": result["text"],
                        "page_number": result.get("page_number", page_nums[0] if page_nums else 0),
                        "page_numbers": page_nums,
                        "chunk_number": result["chunk_number"],
                        "hybrid_score": result["hybrid_score"],
                        "doc_id": document_id,
                        "document_name": result.get("doc_name", ""),
                        "filename": result.get("doc_name", "")
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
                    explanation_needed=explanation_needed,
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
                
                # Check if initial answer is empty
                if not initial_answer or not initial_answer.strip():
                    logger.warning(f"[Worker {worker_id}] Initial answer is empty for field '{field_name}'")
                    initial_answer = "Information not found in the provided documents."
                    initial_explanation = "No relevant information could be extracted from the document chunks."
                
                # Validate and improve with fallback
                validation_timeout = int(os.getenv("VALIDATION_TIMEOUT_SECONDS", "300"))
                validation_max_retries = int(os.getenv("VALIDATION_MAX_RETRIES", "2"))

                try:
                    logger.info(
                        f"[Worker {worker_id}] Starting validation for field '{field_name}' (timeout {validation_timeout}s)"
                    )
                    with ThreadPoolExecutor(max_workers=1) as validation_executor:
                        validation_future = validation_executor.submit(
                            retry_api_call,
                            validation_system.validate_and_improve,
                            user_query=prompt,
                            initial_answer=initial_answer,
                            initial_explanation=initial_explanation,
                            explanation_needed=explanation_needed,
                            prompt_type=prompt_type,
                            chunks=context_chunks,
                            pages=context_pages,
                            max_retries=validation_max_retries
                        )
                        validated_response = validation_future.result(timeout=validation_timeout)
                    logger.info(f"[Worker {worker_id}] Validation completed for field '{field_name}'")
                except TimeoutError:
                    logger.warning(
                        f"[Worker {worker_id}] Validation timeout after {validation_timeout}s for field '{field_name}'. Using initial answer."
                    )
                    validated_response = {
                        "final_answer": initial_answer,
                        "final_answer_explanation": initial_explanation or "",
                        "final_confidence_score": 0.5
                    }
                except Exception as validation_error:
                    logger.warning(f"[Worker {worker_id}] Validation failed: {str(validation_error)}. Using initial answer without validation.")
                    # Fallback to initial answer if validation fails
                    validated_response = {
                        "final_answer": initial_answer,
                        "final_answer_explanation": initial_explanation or "",
                        "final_confidence_score": 0.5  # Lower confidence since not validated
                    }
                
                # Extract source pages using improved logic with BM25 scoring
                # Group chunks by document (in this case, single document)
                chunks_by_doc_id = defaultdict(list)
                for chunk in context_chunks:
                    doc_id = chunk.get("doc_id", document_id)
                    chunks_by_doc_id[doc_id].append(chunk)
                
                # Collect all pages from chunks
                all_pages = sorted(list(set(
                    page for chunk in context_chunks
                    for page in extract_page_numbers(chunk)
                )))
                
                # Use LLM-based page selection if pages are available
                source_pages = all_pages
                page_scores = {}
                
                if all_pages:
                    try:
                        # Call select_top_pages for intelligent page selection
                        selected_page_keys, page_scores = retry_api_call(
                            llm_service.select_top_pages,
                            prompt=prompt,
                            answer=validated_response["final_answer"],
                            context_pages=context_pages,
                            page_numbers=all_pages,
                            collection_id=project_id,
                            context_chunks=context_chunks,
                            explanation=validated_response.get("final_answer_explanation")
                        )
                        
                        # Extract page numbers from keys
                        source_pages = extract_page_numbers_from_keys(selected_page_keys, document_id)
                        
                        # Transform page scores for storage
                        transformed_page_scores = transform_page_scores(page_scores, document_id)
                        
                        logger.info(f"[Worker {worker_id}] Selected {len(source_pages)} pages using BM25 scoring: {source_pages}")
                        logger.info(f"[Worker {worker_id}] Page scores: {transformed_page_scores}")
                        
                    except Exception as e:
                        logger.warning(f"[Worker {worker_id}] Page selection failed: {str(e)}. Using all pages: {all_pages}")
                        source_pages = all_pages
                        transformed_page_scores = {}
                else:
                    transformed_page_scores = {}
                
                # Get unified references from LLM service
                unified_references = getattr(llm_service, '_last_unified_references', [])
                
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
                    "page_scores": transformed_page_scores,
                    "unified_references": unified_references,
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
            
            # Store page_scores and unified_references in chunks JSON field
            chunks_data = result.get("chunks", [])
            chunks_with_metadata = {
                "chunks": chunks_data,
                "page_scores": result.get("page_scores", {}),
                "unified_references": result.get("unified_references", [])
            }
            
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
                    "chunks": chunks_with_metadata,  # Store all metadata in chunks JSON
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
            
            # Return success result
            return {
                "field_name": field_name,
                "status": "completed",
                "value": result["value"],
                "confidence": result.get("confidence", 0)
            }
            
        except Exception as e:
            logger.error(f"Error processing field '{field_name}': {str(e)}")
            
            # Save error result with error_message field
            FieldResultOperations.create_field_result(
                db,
                document_id=document_id,
                field_name=field_name,
                result_data={
                    "value": "Error",
                    "confidence": 0.0,
                    "source_pages": [],
                    "chunks": {"chunks": [], "page_scores": {}, "unified_references": []},
                    "status": "failed",
                    "error_message": str(e),  # Use error_message instead of error
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
            
            # Re-raise the exception for the ThreadPoolExecutor to handle
            raise
            
    finally:
        db.close()


def check_and_update_document_status(db: Session, document_id: str, project_id: str):
    """
    Check if all fields for a document are processed and update document status accordingly.
    This function is idempotent and can be safely called multiple times.
    
    Status flow:
    - 'queued': Initial state when document is first uploaded
    - 'analysing': Document is being processed (chunking, embedding, etc.)
    - 'generating': Chunks are ready, field extraction in progress
    - 'completed': All fields processed successfully
    - 'completed_with_errors': Some fields failed but processing is complete
    - 'failed': Critical failure in processing
    """
    """
    Finalize a document once all field queue entries are resolved, even if some fields failed.
    This function ensures the document is only marked as completed when all fields are processed.
    
    Args:
        db: Database session
        document_id: ID of the document to check
        project_id: ID of the project (for logging)
    """
    try:
        # Get fresh document data to ensure we have the latest status
        db.expire_all()  # Clear any cached data
        document = DocumentOperations.get_document(db, document_id)
        if not document:
            logger.warning(f"Document {document_id} not found in database")
            return

        # Skip documents that already reached a terminal state
        if document.status in ["completed", "completed_with_errors", "failed"]:
            logger.debug(f"Document {document_id} already in terminal state: {document.status}")
            return

        # Get all fields that should be processed for this document
        project = ProjectOperations.get_project(db, project_id)
        if not project or not project.fields_config:
            logger.warning(f"Project {project_id} or its fields configuration not found - using default field list")
            # Get fields from existing field results if available
            existing_fields = db.query(FieldResult.field_name).filter(
                FieldResult.document_id == document_id
            ).distinct().all()
            active_fields = [{'name': field[0], 'isActive': True} for field in existing_fields] or [{'name': 'default_field'}]
            logger.info(f"Using {len(active_fields)} fields from existing results")
        else:
            # Get all active fields from the fields_config
            if isinstance(project.fields_config, dict):
                # Handle dictionary format: {"field1": {"isActive": true, ...}, ...}
                active_fields = [
                    {'name': field_name, **field_config}
                    for field_name, field_config in project.fields_config.items()
                    if field_config.get('isActive', True)
                ]
            elif isinstance(project.fields_config, list):
                # Handle list format: [{"name": "field1", "isActive": true, ...}, ...]
                active_fields = [
                    field for field in project.fields_config
                    if field.get('isActive', True)
                ]
            else:
                logger.warning(f"Unexpected fields_config format: {type(project.fields_config)}"
                             f" - using empty field list")
                active_fields = []
        
        total_expected_fields = len(active_fields)
        
        # Check if all fields have been processed (either succeeded or failed)
        field_results = db.query(FieldResult).filter(
            FieldResult.document_id == document_id
        ).all()
        
        # Get count of fields that are still in progress
        pending_fields = db.query(FieldQueue).filter(
            FieldQueue.document_id == document_id,
            FieldQueue.status.in_(["waiting", "processing"])
        ).all()
        
        # Get all field results including failed ones
        all_field_results = db.query(FieldResult).filter(
            FieldResult.document_id == document_id
        ).all()
        
        # Log detailed status
        logger.info(
            f"Document {document_id} status check - "
            f"Pending: {len(pending_fields)}, "
            f"Completed: {len([fr for fr in all_field_results if fr.status == 'completed'])}, "
            f"Failed: {len([fr for fr in all_field_results if fr.status == 'failed'])}"
        )
        
        # Log pending field details
        for field in pending_fields:
            logger.debug(f"Field {field.field_name} is {field.status} (attempt {field.retry_count + 1})")
        
        if pending_fields:
            logger.info(
                f"Document {document_id}: {len(pending_fields)} field(s) still processing. "
                f"Processed so far: {len(all_field_results)}/{total_expected_fields}"
            )
            return

        # Double-check for any pending or processing fields
        pending_fields = db.query(FieldQueue).filter(
            FieldQueue.document_id == document_id,
            FieldQueue.status.in_(["waiting", "processing"])
        ).all()
        
        if pending_fields:
            pending_names = [f"{f.field_name} ({f.status})" for f in pending_fields]
            logger.info(
                f"Document {document_id}: Found {len(pending_fields)} active fields - "
                f"delaying completion. Pending: {', '.join(pending_names)}"
            )
            return
            
        # Get final field results
        field_results = db.query(FieldResult).filter(
            FieldResult.document_id == document_id
        ).all()
        
        processed_field_names = {fr.field_name for fr in field_results}
        
        # Build expected field names with robust field access
        expected_field_names = set()
        for field in active_fields:
            if isinstance(field, dict):
                # Try to get the field code, fall back to 'name' if not available
                field_code = field.get('code') or field.get('name')
                if field_code:
                    expected_field_names.add(field_code)
            elif hasattr(field, 'code'):
                expected_field_names.add(field.code)
            elif hasattr(field, 'name'):
                expected_field_names.add(field.name)
            else:
                # As a last resort, try to convert the field to string
                field_str = str(field)
                if field_str and field_str != '{}':  # Skip empty strings and empty dicts
                    expected_field_names.add(field_str)
        
        # Log the fields being processed
        logger.debug(f"Processing fields for document {document_id}: {', '.join(sorted(expected_field_names))}")
        
        # Check for missing fields
        missing_fields = expected_field_names - processed_field_names
        if missing_fields:
            logger.warning(
                f"Document {document_id}: Missing results for {len(missing_fields)} fields. "
                f"Expected {len(expected_field_names)} fields, got {len(processed_field_names)}. "
                f"Missing: {', '.join(sorted(missing_fields))}"
            )
            
            # In regeneration mode, we need to be extra careful about completion
        if document.status == 'regenerating':
            # Get the list of fields that were requested for regeneration
            regenerating_fields = set()
            if document.metadata and 'regenerating_fields' in document.metadata:
                regenerating_fields = set(document.metadata['regenerating_fields'])
            
            logger.info(
                f"Regenerating document {document_id} - "
                f"Processing {len(regenerating_fields)} fields: {', '.join(regenerating_fields) if regenerating_fields else 'all fields'}"
            )
            
            # If we have pending fields, don't mark as completed yet
            if pending_fields:
                pending_field_names = {f.field_name for f in pending_fields}
                logger.info(
                    f"Document {document_id}: Still processing {len(pending_fields)} fields - "
                    f"{', '.join(pending_field_names)}"
                )
                return
                
            # Check if all requested regeneration fields are complete
            if regenerating_fields:
                completed_fields = {fr.field_name for fr in field_results if fr.status == 'completed'}
                pending_regeneration = regenerating_fields - completed_fields
                
                if pending_regeneration:
                    logger.info(
                        f"Document {document_id}: Still waiting for regeneration of {len(pending_regeneration)} fields - "
                        f"{', '.join(pending_regeneration)}"
                    )
                    return
            # If no fields were processed at all, that's an error
            elif not field_results:
                error_msg = "No fields were processed during regeneration"
                logger.error(error_msg)
                DocumentOperations.update_document_status(
                    db, document_id, "failed", error_message=error_msg
                )
                logger.error(f"Document {document_id} failed: {error_msg}")
                return

        # Calculate success/failure counts with more detailed logging
        completed_fields = [fr for fr in field_results if fr.status == "completed"]
        failed_fields = [fr for fr in field_results if fr.status == "failed"]
        
        # Log field status summary
        logger.info(
            f"[Status Check] Document {document_id} - "
            f"Completed: {len(completed_fields)}, "
            f"Failed: {len(failed_fields)}, "
            f"Missing: {len(missing_fields) if 'missing_fields' in locals() else 0}"
        )
        
        # Log detailed field statuses
        for fr in field_results:
            logger.debug(f"[Field Status] {fr.field_name}: {fr.status} "
                       f"(Confidence: {getattr(fr, 'confidence', 'N/A')})")
            if fr.status == "failed" and hasattr(fr, 'error_message'):
                logger.debug(f"[Field Error] {fr.field_name}: {fr.error_message}")
        total_processed = completed_fields + failed_fields

        # Log detailed status before updating
        logger.info(
            f"[Status Update] Document {document_id} - "
            f"Completed: {completed_fields}, Failed: {failed_fields}, "
            f"Missing: {len(missing_fields) if missing_fields else 0}, "
            f"Pending: {len(pending_fields) if 'pending_fields' in locals() else 0}"
        )
        
        # Determine final status
        if len(completed_fields) > 0:  # If at least one field was successfully processed
            final_status = "completed"
            error_parts = []
            if len(failed_fields) > 0:
                error_parts.append(f"{len(failed_fields)} field(s) failed extraction")
            if missing_fields:
                error_parts.append(f"{len(missing_fields)} field(s) missing results")
            
            error_message = "; ".join(error_parts) if error_parts else None
            
            if error_message:
                logger.warning(
                    f"[Status Update] Document {document_id} completed with {completed_fields} successful fields, "
                    f"but had some issues: {error_message}"
                )
            else:
                logger.info(
                    f"[Status Update] Document {document_id} completed successfully: "
                    f"{completed_fields} fields processed"
                )
        else:
            # No fields were successfully processed
            final_status = "failed"
            error_parts = []
            if len(failed_fields) > 0:
                error_parts.append(f"{failed_fields} field(s) failed extraction")
            if missing_fields:
                error_parts.append(f"{len(missing_fields)} field(s) missing results")
            error_message = "; ".join(error_parts) or "No fields were successfully processed"
            
            logger.error(
                f"[Status Update] Document {document_id} failed: {error_message}"
            )

        # Log before updating document status
        logger.info(
            f"[Document Status] Attempting to update document {document_id} to status: {final_status}, "
            f"Error: {error_message or 'None'}"
        )
        
        try:
            # Update document status
            DocumentOperations.update_document_status(
                db,
                document_id,
                final_status,
                error_message=error_message
            )
            
            # Verify the status was updated using DocumentOperations
            updated_doc = DocumentOperations.get_document(db, document_id)
            if updated_doc and updated_doc.status == final_status:
                logger.info(
                    f"[Document Status] Successfully updated document {document_id} to status: {final_status}"
                )
            else:
                current_status = updated_doc.status if updated_doc else 'not found'
                logger.error(
                    f"[Document Status] Status update verification failed for document {document_id}. "
                    f"Expected: {final_status}, Actual: {current_status}"
                )
                
        except Exception as e:
            logger.error(
                f"[Document Status] Failed to update document {document_id} status to {final_status}: {str(e)}",
                exc_info=True
            )
            raise
        DocumentQueueOperations.complete_document(
            db,
            document_id,
            final_status,
            error_message=error_message
        )

    except Exception as e:
        logger.error(f"Error updating document status: {str(e)}")


def check_and_update_project_status(db: Session, project_id: str):
    """
    Update overall project status based on document and field outcomes.
    """
    try:
        project = ProjectOperations.get_project(db, project_id)
        if not project:
            return

        documents = DocumentOperations.get_project_documents(db, project_id)
        total_docs = len(documents)

        completed_docs = sum(
            1 for doc in documents if doc.status in ["completed", "completed_with_errors"]
        )
        failed_docs = sum(1 for doc in documents if doc.status == "failed")

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

        if total_fields > 0 and completed_fields + failed_fields == total_fields:
            if failed_fields == 0 and failed_docs == 0:
                status = "completed"
                error_message = None
            else:
                status = "completed_with_errors"
                error_message = f"{failed_docs} document(s) or {failed_fields} field(s) failed"
        else:
            status = "processing"
            error_message = None

        ProjectOperations.update_project_status(
            db,
            project_id,
            status,
            processed_documents=completed_docs,
            failed_documents=failed_docs,
            error_message=error_message
        )

    except Exception as e:
        logger.error(f"Error updating project status: {str(e)}")


def process_project_parallel(project_id: str):
    """
    Main entry point for parallel project processing.
    This function processes all documents in parallel using ThreadPoolExecutor.
    """
    worker_id = os.getenv("WORKER_ID", "unknown")
    max_doc_workers = int(os.getenv("MAX_CONCURRENT_DOCS", "2"))
    logger.info(f"[Project Worker {worker_id}] Starting parallel project processing: {project_id} with max {max_doc_workers} concurrent documents")
    
    db = SessionLocal()
    start_time = time.time()
    
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
        
        logger.info(f"[Project Worker {worker_id}] Processing {len(documents)} documents in parallel (max {max_doc_workers} concurrent)")
        
        # Track document results
        doc_results = {}
        doc_errors = {}
        
        # Process documents in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_doc_workers) as executor:
            # Submit all document processing tasks
            future_to_doc = {}
            for document in documents:
                # Add to document queue in database
                DocumentQueueOperations.enqueue_document(
                    db,
                    document_id=document.id,
                    project_id=project_id,
                    priority=0
                )
                
                # Submit document for parallel processing
                future = executor.submit(
                    process_document,
                    project_id,
                    document.id
                )
                future_to_doc[future] = document
                logger.info(f"[Project Worker {worker_id}] Submitted document {document.doc_name} for processing")
            
            # Process completed documents
            for future in as_completed(future_to_doc):
                document = future_to_doc[future]
                try:
                    result = future.result(timeout=1800)  # 30 minutes timeout per document
                    doc_results[document.id] = result
                    logger.info(f"[Project Worker {worker_id}] Successfully processed document {document.doc_name}")
                except Exception as e:
                    error_msg = f"Error processing document {document.doc_name}: {str(e)}"
                    logger.error(f"[Project Worker {worker_id}] {error_msg}")
                    doc_errors[document.id] = error_msg
                    # Update document status to failed
                    try:
                        DocumentOperations.update_document_status(
                            db, document.id, "failed", error_message=error_msg
                        )
                        db.commit()
                    except Exception as db_error:
                        logger.error(f"Failed to update document status: {str(db_error)}")
        
        # Calculate project completion status
        total_docs = len(documents)
        successful_docs = len(doc_results)
        failed_docs = len(doc_errors)
        
        elapsed_time = time.time() - start_time
        logger.info(f"[Project Worker {worker_id}] Project {project_id} processing completed in {elapsed_time:.2f}s: "
                    f"{successful_docs}/{total_docs} successful, {failed_docs} failed")
        
        # Update project status based on results
        if failed_docs == total_docs:
            ProjectOperations.update_project_status(db, project_id, "failed", 
                                                   error_message="All documents failed to process")
        elif failed_docs > 0:
            ProjectOperations.update_project_status(db, project_id, "completed_with_errors",
                                                   error_message=f"{failed_docs} documents failed")
        else:
            ProjectOperations.update_project_status(db, project_id, "completed")
        
        db.commit()
        logger.info(f"[Project Worker {worker_id}] Successfully completed project {project_id}")
        
    except Exception as e:
        logger.error(f"[Project Worker {worker_id}] Error in parallel project processing: {str(e)}")
        ProjectOperations.update_project_status(db, project_id, "failed", error_message=str(e))
        db.commit()
        raise
    finally:
        db.close()
