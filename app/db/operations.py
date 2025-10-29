"""Database operations for project management."""

from typing import List, Dict, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
from app.db.models import Project, Document, FieldResult, ProcessingQueue, DocumentQueue, FieldQueue
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
    
    staticmethod
    def get_document_by_ids(db: Session, document_id: str, project_id: str) -> Optional[Document]:
        """Get document by both document ID and project ID for validation."""
        return db.query(Document).filter(
            Document.id == document_id,
            Document.project_id == project_id
        ).first()
    
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
    def get_field_result(db: Session, document_id: str, field_name: str) -> Optional[FieldResult]:
        """Get a specific field result for a document."""
        return db.query(FieldResult).filter(
            and_(
                FieldResult.document_id == document_id,
                FieldResult.field_name == field_name
            )
        ).first()
    
    @staticmethod
    def update_field_result(
        db: Session,
        document_id: str,
        field_name: str,
        updates: Dict[str, Any]
    ) -> Optional[FieldResult]:
        """Update a specific field result."""
        try:
            field_result = db.query(FieldResult).filter(
                and_(
                    FieldResult.document_id == document_id,
                    FieldResult.field_name == field_name
                )
            ).first()
            
            if not field_result:
                return None
            
            # Update fields
            for key, value in updates.items():
                if hasattr(field_result, key):
                    setattr(field_result, key, value)
            
            field_result.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(field_result)
            return field_result
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update field result: {str(e)}")
            raise
            
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


class DocumentQueueOperations:
    """Operations for document queue management."""
    
    @staticmethod
    def enqueue_document(
        db: Session,
        document_id: str,
        project_id: str,
        priority: int = 0
    ) -> DocumentQueue:
        """Add a document to the processing queue."""
        try:
            queue_entry = DocumentQueue(
                document_id=document_id,
                project_id=project_id,
                priority=priority,
                status="waiting"
            )
            db.add(queue_entry)
            db.commit()
            db.refresh(queue_entry)
            
            logger.info(f"Enqueued document {document_id} for processing")
            return queue_entry
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to enqueue document: {str(e)}")
            raise
    
    @staticmethod
    def get_next_document(db: Session, worker_id: str) -> Optional[DocumentQueue]:
        """Get the next document to process from the queue."""
        try:
            # Find the next waiting document with highest priority
            queue_entry = db.query(DocumentQueue).filter(
                DocumentQueue.status == "waiting"
            ).order_by(
                desc(DocumentQueue.priority),
                DocumentQueue.queued_at
            ).first()
            
            if queue_entry:
                # Mark as processing
                queue_entry.status = "processing"
                queue_entry.worker_id = worker_id
                queue_entry.started_at = datetime.utcnow()
                db.commit()
                db.refresh(queue_entry)
            
            return queue_entry
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to get next document: {str(e)}")
            raise
    
    @staticmethod
    def complete_document(
        db: Session,
        document_id: str,
        status: str = "completed",
        error_message: Optional[str] = None
    ) -> Optional[DocumentQueue]:
        """Mark a document as completed in the queue."""
        try:
            queue_entry = db.query(DocumentQueue).filter(
                DocumentQueue.document_id == document_id
            ).first()
            
            if queue_entry:
                queue_entry.status = status
                queue_entry.completed_at = datetime.utcnow()
                if error_message:
                    queue_entry.error_message = error_message
                db.commit()
                db.refresh(queue_entry)
            
            return queue_entry
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to complete document: {str(e)}")
            raise
    
    @staticmethod
    def get_pending_documents(db: Session, project_id: str) -> List[DocumentQueue]:
        """Get all pending documents for a project."""
        return db.query(DocumentQueue).filter(
            and_(
                DocumentQueue.project_id == project_id,
                DocumentQueue.status.in_(["waiting", "processing"])
            )
        ).all()


class FieldQueueOperations:
    """Operations for field queue management."""
    
    @staticmethod
    def enqueue_field(
        db: Session,
        document_id: str,
        project_id: str,
        field_name: str,
        field_config: Dict[str, Any],
        priority: int = 0,
        depends_on_doc: bool = True
    ) -> FieldQueue:
        """Add a field extraction task to the queue."""
        try:
            queue_entry = FieldQueue(
                document_id=document_id,
                project_id=project_id,
                field_name=field_name,
                field_config=field_config,
                priority=priority,
                depends_on_doc=depends_on_doc,
                status="waiting"
            )
            db.add(queue_entry)
            db.commit()
            db.refresh(queue_entry)
            
            logger.info(f"Enqueued field {field_name} for document {document_id}")
            return queue_entry
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to enqueue field: {str(e)}")
            raise
    
    @staticmethod
    def get_next_field(db: Session, worker_id: str) -> Optional[FieldQueue]:
        """Get the next field to process from the queue."""
        try:
            # Find the next waiting field where document is ready
            # Join with DocumentQueue to check if document processing is complete
            queue_entry = db.query(FieldQueue).join(
                DocumentQueue,
                FieldQueue.document_id == DocumentQueue.document_id
            ).filter(
                and_(
                    FieldQueue.status == "waiting",
                    # Only process fields where document chunks are ready
                    DocumentQueue.status == "completed"
                )
            ).order_by(
                desc(FieldQueue.priority),
                FieldQueue.queued_at
            ).first()
            
            if queue_entry:
                # Mark as processing
                queue_entry.status = "processing"
                queue_entry.worker_id = worker_id
                queue_entry.started_at = datetime.utcnow()
                db.commit()
                db.refresh(queue_entry)
            
            return queue_entry
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to get next field: {str(e)}")
            raise
    
    @staticmethod
    def complete_field(
        db: Session,
        field_queue_id: str,
        status: str = "completed",
        error_message: Optional[str] = None
    ) -> Optional[FieldQueue]:
        """Mark a field as completed in the queue."""
        try:
            queue_entry = db.query(FieldQueue).filter(
                FieldQueue.id == field_queue_id
            ).first()
            
            if queue_entry:
                queue_entry.status = status
                queue_entry.completed_at = datetime.utcnow()
                if error_message:
                    queue_entry.error_message = error_message
                db.commit()
                db.refresh(queue_entry)
            
            return queue_entry
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to complete field: {str(e)}")
            raise
    
    @staticmethod
    def get_pending_fields(db: Session, document_id: str) -> List[FieldQueue]:
        """Get all pending fields for a document."""
        return db.query(FieldQueue).filter(
            and_(
                FieldQueue.document_id == document_id,
                FieldQueue.status.in_(["waiting", "processing"])
            )
        ).all()
    
    @staticmethod
    def retry_field(
        db: Session,
        field_queue_id: str
    ) -> Optional[FieldQueue]:
        """Retry a failed field extraction."""
        try:
            queue_entry = db.query(FieldQueue).filter(
                FieldQueue.id == field_queue_id
            ).first()
            
            if queue_entry and queue_entry.retry_count < queue_entry.max_retries:
                queue_entry.status = "waiting"
                queue_entry.retry_count += 1
                queue_entry.worker_id = None
                queue_entry.error_message = None
                db.commit()
                db.refresh(queue_entry)
                return queue_entry
            
            return None
            
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to retry field: {str(e)}")
            raise
