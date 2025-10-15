"""Database models for project tracking."""

from sqlalchemy import Column, String, Text, DateTime, Integer, Float, JSON, ForeignKey, Index, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base
import uuid


def generate_uuid():
    """Generate a UUID string."""
    return str(uuid.uuid4())


class Project(Base):
    """Project model for tracking document processing projects."""
    
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    project_name = Column(String, nullable=False)
    status = Column(String, default="queued")  # queued, processing, completed, failed, completed_with_errors
    fields_config = Column(JSON, nullable=False)  # Store field configurations as JSON
    
    # Tracking fields
    total_documents = Column(Integer, default=0)
    processed_documents = Column(Integer, default=0)
    failed_documents = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Additional metadata
    temp_dir = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_project_status', 'status'),
        Index('idx_project_created_at', 'created_at'),
    )


class Document(Base):
    """Document model for tracking individual documents in a project."""
    
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    doc_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    
    # Document metadata
    file_size = Column(Integer, nullable=True)
    file_type = Column(String, nullable=True)
    page_count = Column(Integer, nullable=True)
    
    # Processing metadata
    chunks_count = Column(Integer, default=0)
    processing_time = Column(Float, nullable=True)  # in seconds
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    project = relationship("Project", back_populates="documents")
    field_results = relationship("FieldResult", back_populates="document", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_document_project_id', 'project_id'),
        Index('idx_document_status', 'status'),
    )


class FieldResult(Base):
    """Field extraction results for each document."""
    
    __tablename__ = "field_results"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String, nullable=False)
    
    # Extraction results
    value = Column(Text, nullable=True)
    answer_html = Column(Text, nullable=True)  # HTML formatted answer if applicable
    explanation = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    
    # Source tracking
    source_pages = Column(JSON, default=list)  # List of page numbers
    chunks = Column(JSON, default=list)  # Top relevant chunks with scores
    
    # Processing metadata
    status = Column(String, default="pending")  # pending, completed, failed
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    processing_time = Column(Float, nullable=True)
    
    # Model configuration used
    model_used = Column(String, nullable=True)
    reasoning_mode = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="field_results")
    
    # Indexes
    __table_args__ = (
        Index('idx_field_result_document_id', 'document_id'),
        Index('idx_field_result_field_name', 'field_name'),
        Index('idx_field_result_confidence', 'confidence'),
    )


class ProcessingQueue(Base):
    """Queue management for project processing."""
    
    __tablename__ = "processing_queue"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # Queue metadata
    queue_position = Column(Integer, nullable=False)
    priority = Column(Integer, default=0)  # Higher number = higher priority
    worker_id = Column(String, nullable=True)  # ID of worker processing this
    
    # Status tracking
    status = Column(String, default="waiting")  # waiting, processing, completed, failed
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Timestamps
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_queue_status', 'status'),
        Index('idx_queue_position', 'queue_position'),
        Index('idx_queue_priority', 'priority'),
    )


class DocumentQueue(Base):
    """Queue for document processing tasks."""
    
    __tablename__ = "document_queue"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # Queue metadata
    priority = Column(Integer, default=0)  # Higher number = higher priority
    worker_id = Column(String, nullable=True)  # ID of worker processing this
    
    # Status tracking
    status = Column(String, default="waiting")  # waiting, processing, completed, failed
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    document = relationship("Document", backref="queue_entry")
    
    # Indexes
    __table_args__ = (
        Index('idx_doc_queue_status', 'status'),
        Index('idx_doc_queue_priority', 'priority'),
        Index('idx_doc_queue_document_id', 'document_id'),
    )


class FieldQueue(Base):
    """Queue for field extraction tasks."""
    
    __tablename__ = "field_queue"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String, nullable=False)
    
    # Field configuration
    field_config = Column(JSON, nullable=False)  # Contains prompt, model, mode, type
    
    # Queue metadata
    priority = Column(Integer, default=0)  # Higher number = higher priority
    worker_id = Column(String, nullable=True)  # ID of worker processing this
    depends_on_doc = Column(Boolean, default=True)  # Whether this needs doc chunks to be ready
    
    # Status tracking
    status = Column(String, default="waiting")  # waiting, processing, completed, failed
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    queued_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    document = relationship("Document", backref="field_queue_entries")
    
    # Indexes
    __table_args__ = (
        Index('idx_field_queue_status', 'status'),
        Index('idx_field_queue_priority', 'priority'),
        Index('idx_field_queue_document_id', 'document_id'),
        Index('idx_field_queue_field_name', 'field_name'),
    )
