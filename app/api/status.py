import os
import json
from typing import List, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import redis as rqredis
from app.logging_config import logger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
sync_redis = rqredis.from_url(REDIS_URL)

status_router = APIRouter()


class DocumentStatus(BaseModel):
    doc_id: str
    doc_name: str
    status: str
    processed_fields: int
    total_fields: int


class ProjectListItem(BaseModel):
    project_id: str
    project_name: str
    status: str
    total_documents: int
    processed_documents: int
    created_at: str


@status_router.get("/projects", response_model=List[ProjectListItem])
async def list_projects():
    """List all projects"""
    try:
        # Get all project keys
        project_keys = sync_redis.keys("project:*")
        # Filter out result keys
        project_keys = [k.decode('utf-8') if isinstance(k, bytes) else k 
                       for k in project_keys if not k.endswith(b':results') and not k.endswith(':results')]
        
        projects = []
        for key in project_keys:
            try:
                project_data_json = sync_redis.get(key)
                if project_data_json:
                    project_data = json.loads(project_data_json)
                    projects.append(ProjectListItem(
                        project_id=project_data["project_id"],
                        project_name=project_data["project_name"],
                        status=project_data["status"],
                        total_documents=project_data["total_documents"],
                        processed_documents=project_data["processed_documents"],
                        created_at=project_data["created_at"]
                    ))
            except Exception as e:
                logger.warning(f"Error parsing project {key}: {str(e)}")
                continue
        
        # Sort by created_at descending
        projects.sort(key=lambda x: x.created_at, reverse=True)
        
        return projects
        
    except Exception as e:
        logger.error(f"Error listing projects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {str(e)}")


@status_router.get("/project/{project_id}/documents", response_model=List[DocumentStatus])
async def get_document_statuses(project_id: str):
    """Get status of all documents in a project"""
    try:
        project_data_json = sync_redis.get(f"project:{project_id}")
        if not project_data_json:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        project_data = json.loads(project_data_json)
        documents = project_data.get("documents", [])
        total_fields = len(project_data.get("fields_config", []))
        
        doc_statuses = []
        for doc in documents:
            # Get processed fields count from results
            results_json = sync_redis.get(f"project:{project_id}:results")
            results = json.loads(results_json) if results_json else {}
            doc_results = results.get(doc["doc_id"], {})
            processed_fields = len([f for f in doc_results.values() if f.get("status") == "completed"])
            
            doc_statuses.append(DocumentStatus(
                doc_id=doc["doc_id"],
                doc_name=doc["doc_name"],
                status=doc.get("status", "pending"),
                processed_fields=processed_fields,
                total_fields=total_fields
            ))
        
        return doc_statuses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document statuses: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get document statuses: {str(e)}")


@status_router.get("/project/{project_id}/document/{doc_id}/results")
async def get_document_results(project_id: str, doc_id: str):
    """Get extraction results for a specific document"""
    try:
        results_json = sync_redis.get(f"project:{project_id}:results")
        if not results_json:
            raise HTTPException(status_code=404, detail=f"No results found for project {project_id}")
        
        results = json.loads(results_json)
        doc_results = results.get(doc_id)
        
        if not doc_results:
            raise HTTPException(status_code=404, detail=f"No results found for document {doc_id}")
        
        return {
            "project_id": project_id,
            "doc_id": doc_id,
            "results": doc_results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get document results: {str(e)}")
