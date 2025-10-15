"""Database operations for project management."""

from typing import List, Dict, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from app.db.models import Project, Document, FieldResult, ProcessingQueue
from app.logging_config import logger
import json


class ProjectOperations:
    """Operations for project management."""
    
    @staticmethod
    def create_project(
        db: Session,
        project_name: str,
        fields_config: List[Dict],
        documents: List[Dict]
    ) -> Project:
        """Create a new project with documents."""
        try:
            # Create project
            project = Project(
                project_name=project_name,
                fields_config=fields_config,
                total_documents=len(documents),
                status="queued"
            )
            db.add(project)
            db.flush()  # Get project ID
            
            # Create documents
            for doc_data in documents:
                document = Document(
                    project_id=project.id,
                    doc_name=doc_data["doc_name"],
                    file_path=doc_data["file_path"],
                    status="pending"
                )
                db.add(document)
            
            # Add to processing queue
            # Get the next queue position
            max_position = db.query(ProcessingQueue.queue_position).order_by(
                desc(ProcessingQueue.queue_position)
            ).first()
            
            next_position = (max_position[0] + 1) if max_position else 1
            
            queue_entry = ProcessingQueue(
                project_id=project.id,
                queue_position=next_position,
                status="waiting"
            )
            db.add(queue_entry)
            
            db.commit()
            db.refresh(project)
            
            logger.info(f"Created project {project.id} with {len(documents)} documents")
            return project
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create project: {str(e)}")
            raise
    
    @staticmethod
    def get_project(db: Session, project_id: str) -> Optional[Project]:
        """Get project by ID."""
        return db.query(Project).filter(Project.id == project_id).first()
    
    @staticmethod
    def update_project_status(
        db: Session,
        project_id: str,
        status: str,
        **kwargs
    ) -> Optional[Project]:
        """Update project status and metadata."""
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                return None
            
            project.status = status
            project.updated_at = datetime.utcnow()
            
            # Update additional fields if provided
            for key, value in kwargs.items():
                if hasattr(project, key):
                    setattr(project, key, value)
            
            # Set completed_at if status is final
            if status in ["completed", "failed", "completed_with_errors"]:
                project.completed_at = datetime.utcnow()
            
            db.commit()
            db.refresh(project)
            return project
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update project status: {str(e)}")
            raise
    
    @staticmethod
    def list_projects(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None
    ) -> List[Project]:
        """List projects with optional filtering."""
        query = db.query(Project)
        
        if status:
            query = query.filter(Project.status == status)
        
        return query.order_by(desc(Project.created_at)).offset(skip).limit(limit).all()
    
    @staticmethod
    def delete_project(db: Session, project_id: str) -> bool:
        """Delete a project and all related data."""
        try:
            project = db.query(Project).filter(Project.id == project_id).first()
            if not project:
                return False
            
            db.delete(project)
            db.commit()
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete project: {str(e)}")
            raise


class DocumentOperations:
    """Operations for document management."""
    
    @staticmethod
    def get_document(db: Session, doc_id: str) -> Optional[Document]:
        """Get document by ID."""
        return db.query(Document).filter(Document.id == doc_id).first()
    
    @staticmethod
    def get_project_documents(db: Session, project_id: str) -> List[Document]:
        """Get all documents for a project."""
        return db.query(Document).filter(Document.project_id == project_id).all()
    
    @staticmethod
    def update_document_status(
        db: Session,
        doc_id: str,
        status: str,
        **kwargs
    ) -> Optional[Document]:
        """Update document status and metadata."""
        try:
            document = db.query(Document).filter(Document.id == doc_id).first()
            if not document:
                return None
            
            document.status = status
            document.updated_at = datetime.utcnow()
            
            # Update additional fields
            for key, value in kwargs.items():
                if hasattr(document, key):
                    setattr(document, key, value)
            
            # Set completed_at if status is final
            if status in ["completed", "failed"]:
                document.completed_at = datetime.utcnow()
            
            db.commit()
            db.refresh(document)
            return document
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update document status: {str(e)}")
            raise


class FieldResultOperations:
    """Operations for field result management."""
    
    @staticmethod
    def create_field_result(
        db: Session,
        document_id: str,
        field_name: str,
        result_data: Dict[str, Any]
    ) -> FieldResult:
        """Create or update a field result."""
        try:
            # Check if result already exists
            existing = db.query(FieldResult).filter(
                and_(
                    FieldResult.document_id == document_id,
                    FieldResult.field_name == field_name
                )
            ).first()
            
            if existing:
                # Update existing result
                for key, value in result_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
                field_result = existing
            else:
                # Create new result
                field_result = FieldResult(
                    document_id=document_id,
                    field_name=field_name,
                    **result_data
                )
                db.add(field_result)
            
            db.commit()
            db.refresh(field_result)
            return field_result
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create/update field result: {str(e)}")
            raise
    
    @staticmethod
    def get_document_results(db: Session, document_id: str) -> List[FieldResult]:
        """Get all field results for a document."""
        return db.query(FieldResult).filter(
            FieldResult.document_id == document_id
        ).all()
    
    @staticmethod
    def get_project_results(db: Session, project_id: str) -> Dict[str, List[Dict]]:
        """Get all field results for a project grouped by document."""
        documents = db.query(Document).filter(
            Document.project_id == project_id
        ).all()
        
        results = {}
        for doc in documents:
            field_results = db.query(FieldResult).filter(
                FieldResult.document_id == doc.id
            ).all()
            
            results[doc.id] = [
                {
                    "field_name": fr.field_name,
                    "value": fr.value,
                    "answer_html": fr.answer_html,
                    "explanation": fr.explanation,
                    "confidence": fr.confidence,
                    "source_pages": fr.source_pages,
                    "chunks": fr.chunks,
                    "status": fr.status,
                    "error_message": fr.error_message
                }
                for fr in field_results
            ]
        
        return results


class QueueOperations:
    """Operations for processing queue management."""
    
    @staticmethod
    def get_next_project(db: Session, worker_id: str) -> Optional[ProcessingQueue]:
        """Get the next project from the queue for processing."""
        try:
            # Find next waiting project in queue
            queue_entry = db.query(ProcessingQueue).filter(
                ProcessingQueue.status == "waiting"
            ).order_by(
                desc(ProcessingQueue.priority),
                ProcessingQueue.queue_position
            ).first()
            
            if queue_entry:
                queue_entry.status = "processing"
                queue_entry.worker_id = worker_id
                queue_entry.started_at = datetime.utcnow()
                db.commit()
                db.refresh(queue_entry)
            
            return queue_entry
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to get next project from queue: {str(e)}")
            raise
    
    @staticmethod
    def complete_queue_entry(
        db: Session,
        project_id: str,
        status: str = "completed"
    ) -> Optional[ProcessingQueue]:
        """Mark a queue entry as completed."""
        try:
            queue_entry = db.query(ProcessingQueue).filter(
                ProcessingQueue.project_id == project_id
            ).first()
            
            if queue_entry:
                queue_entry.status = status
                queue_entry.completed_at = datetime.utcnow()
                db.commit()
                db.refresh(queue_entry)
            
            return queue_entry
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to complete queue entry: {str(e)}")
            raise
    
    @staticmethod
    def get_queue_position(db: Session, project_id: str) -> Optional[int]:
        """Get the queue position for a project."""
        queue_entry = db.query(ProcessingQueue).filter(
            ProcessingQueue.project_id == project_id
        ).first()
        
        if not queue_entry or queue_entry.status != "waiting":
            return None
        
        # Count how many projects are ahead in queue
        ahead_count = db.query(ProcessingQueue).filter(
            and_(
                ProcessingQueue.status == "waiting",
                ProcessingQueue.queue_position < queue_entry.queue_position
            )
        ).count()
        
        return ahead_count + 1
