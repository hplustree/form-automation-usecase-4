import os
import uuid
import json
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
import redis as rqredis
from rq import Queue
from datetime import datetime
from app.logging_config import logger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "projects")
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", 86400 * 7))  # 7 days for projects

sync_redis = rqredis.from_url(REDIS_URL)
project_queue = Queue(QUEUE_NAME, connection=sync_redis)

project_router = APIRouter()

from pathlib import Path

# Path to the templates directory
TEMPLATES_DIR = Path("/app/templates")
# For local development, fall back to the local path
if not TEMPLATES_DIR.exists():
    TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Create templates directory if it doesn't exist
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

def load_template(template_name: str = "spa_fields") -> Dict[str, Any]:
    """Load field configurations from a JSON template file."""
    template_path = str(TEMPLATES_DIR / f"{template_name}.json")
    try:
        with open(template_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Template '{template_name}' not found in {TEMPLATES_DIR}")
    except json.JSONDecodeError:
        raise ValueError(f"Invalid JSON in template file: {template_path}")


class FieldConfig(BaseModel):
    field_name: str = Field(..., description="Name of the field to extract")
    prompt: str = Field(..., description="Prompt to extract the field value")
    model: str = Field(default="gpt-5", description="LLM model to use")
    mode: str = Field(default="low", description="Reasoning effort mode")
    type: str = Field(default="verbatim", description="Prompt type: verbatim or summarize")


class ProjectSubmitRequest(BaseModel):
    project_name: str = Field(..., description="Name of the project")
    field_names: List[str] = Field(..., description="List of field names to extract from the template")
    template_name: str = Field(default="spa_fields", description="Name of the template to use")


class ProjectSubmitResponse(BaseModel):
    project_id: str
    status: str
    message: str


class ProjectStatusResponse(BaseModel):
    project_id: str
    project_name: str
    status: str
    total_documents: int
    processed_documents: int
    failed_documents: int
    created_at: str
    updated_at: str
    documents: List[dict]


class ProjectResultsResponse(BaseModel):
    project_id: str
    project_name: str
    status: str
    results: dict  # doc_id -> field results


@project_router.post("/project/submit", response_model=ProjectSubmitResponse)
async def submit_project(
    project_name: str = Form(...),
    field_names: str = Form(...),  # JSON array of field names
    template_name: str = Form("spa_fields"),
    files: List[UploadFile] = File(...)
):
    """
    Submit a new project with documents and field extraction configuration.
    
    Args:
        project_name: Name of the project
        field_names: JSON array of field names to extract (e.g., ["effective_date", "escrow_account_details"])
        template_name: Name of the template to use (default: "spa_fields")
        files: List of document files to process
    
    Returns:
        ProjectSubmitResponse with project_id and status
    """
    try:
        # Generate project ID
        project_id = str(uuid.uuid4())
        
        # Load template and get field configurations
        try:
            # Parse field names
            requested_fields = json.loads(field_names)
            if not isinstance(requested_fields, list):
                raise ValueError("field_names must be a JSON array of strings")
                
            # Load template
            template = load_template(template_name)
            
            # Get configurations for requested fields
            fields = []
            
            # Check if template has a 'fields' array
            if 'fields' not in template or not isinstance(template['fields'], list):
                raise ValueError("Template must contain a 'fields' array")
                
            # Create a mapping of field codes to their configs
            field_map = {field['code']: field for field in template['fields']}
            
            for field_name in requested_fields:
                if field_name not in field_map:
                    raise ValueError(f"Field '{field_name}' not found in template")
                    
                field_config = field_map[field_name].copy()
                # Map the template fields to the expected FieldConfig format
                config = {
                    "field_name": field_name,
                    "prompt": field_config.get("prompt", ""),
                    "model": field_config.get("model", template.get("defaultModel", "gpt-5")),
                    "mode": field_config.get("mode", template.get("defaultMode", "low")),
                    "type": field_config.get("typeOfPrompt", "verbatim")
                }
                fields.append(FieldConfig(**config))
                
            if not fields:
                raise ValueError("No valid field names provided")
                
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error processing field configurations: {str(e)}")
        
        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="At least one document file is required")
        
        # Store uploaded files temporarily and create document metadata
        documents = []
        temp_dir = f"temp_files/{project_id}"
        os.makedirs(temp_dir, exist_ok=True)
        
        for idx, file in enumerate(files):
            # Generate doc_id
            doc_id = f"{project_id}_doc_{idx+1}"
            
            # Read file content
            file_content = await file.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
            
            # Save file temporarily
            file_path = f"{temp_dir}/{file.filename}"
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            documents.append({
                "doc_id": doc_id,
                "doc_name": file.filename,
                "file_path": file_path,
                "file_hash": file_hash,
                "file_size": len(file_content),
                "status": "pending"
            })
            
            logger.info(f"Saved file {file.filename} for project {project_id}")
        
        # Create project metadata
        project_data = {
            "project_id": project_id,
            "project_name": project_name,
            "status": "queued",
            "total_documents": len(documents),
            "processed_documents": 0,
            "failed_documents": 0,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "documents": documents,
            "fields_config": [field.model_dump() for field in fields],
            "temp_dir": temp_dir
        }
        
        # Store in Redis
        sync_redis.set(
            f"project:{project_id}",
            json.dumps(project_data),
            ex=REDIS_TTL_SECONDS
        )
        
        # Initialize results storage
        sync_redis.set(
            f"project:{project_id}:results",
            json.dumps({}),
            ex=REDIS_TTL_SECONDS
        )
        
        # Enqueue project for processing
        job = project_queue.enqueue(
            'app.api.worker.process_project',
            args=(project_id,),
            job_id=project_id,
            job_timeout=7200,  # 2 hours
            result_ttl=REDIS_TTL_SECONDS
        )
        
        logger.info(f"Project {project_id} queued for processing with {len(documents)} documents")
        
        return ProjectSubmitResponse(
            project_id=project_id,
            status="queued",
            message=f"Project submitted successfully with {len(documents)} documents"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to submit project: {str(e)}")


@project_router.get("/project/{project_id}", response_model=ProjectStatusResponse)
async def get_project_status(project_id: str):
    """Get the status of a project"""
    try:
        project_data_json = sync_redis.get(f"project:{project_id}")
        if not project_data_json:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        project_data = json.loads(project_data_json)
        
        return ProjectStatusResponse(
            project_id=project_data["project_id"],
            project_name=project_data["project_name"],
            status=project_data["status"],
            total_documents=project_data["total_documents"],
            processed_documents=project_data["processed_documents"],
            failed_documents=project_data["failed_documents"],
            created_at=project_data["created_at"],
            updated_at=project_data["updated_at"],
            documents=project_data["documents"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get project status: {str(e)}")


@project_router.get("/project/{project_id}/results", response_model=ProjectResultsResponse)
async def get_project_results(project_id: str):
    """Get the extraction results for a project"""
    try:
        # Get project metadata
        project_data_json = sync_redis.get(f"project:{project_id}")
        if not project_data_json:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        project_data = json.loads(project_data_json)
        
        # Get results
        results_json = sync_redis.get(f"project:{project_id}:results")
        results = json.loads(results_json) if results_json else {}
        
        return ProjectResultsResponse(
            project_id=project_data["project_id"],
            project_name=project_data["project_name"],
            status=project_data["status"],
            results=results
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get project results: {str(e)}")


@project_router.delete("/project/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and its data"""
    try:
        project_data_json = sync_redis.get(f"project:{project_id}")
        if not project_data_json:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        project_data = json.loads(project_data_json)
        
        # Delete temporary files
        import shutil
        temp_dir = project_data.get("temp_dir")
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            logger.info(f"Deleted temp directory: {temp_dir}")
        
        # Delete from Redis
        sync_redis.delete(f"project:{project_id}")
        sync_redis.delete(f"project:{project_id}:results")
        
        # Delete from Weaviate (will be done by worker if needed)
        
        logger.info(f"Deleted project {project_id}")
        
        return {"status": "success", "message": f"Project {project_id} deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")
         