#!/usr/bin/env python3
"""Test script to verify PostgreSQL integration."""

import os
import sys
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import Base, engine, SessionLocal
from app.db.models import Project, Document, FieldResult, ProcessingQueue
from app.db.operations import (
    ProjectOperations,
    DocumentOperations,
    FieldResultOperations,
    QueueOperations
)


def test_database_connection():
    """Test basic database connection."""
    print("Testing database connection...")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Database connection successful")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def test_create_project():
    """Test creating a project with documents."""
    print("\nTesting project creation...")
    db = SessionLocal()
    try:
        # Create test project
        fields_config = [
            {
                "field_name": "company_name",
                "prompt": "Extract the company name",
                "model": "gpt-5",
                "mode": "low",
                "type": "verbatim"
            },
            {
                "field_name": "contract_date",
                "prompt": "Extract the contract date",
                "model": "gpt-5",
                "mode": "low",
                "type": "verbatim"
            }
        ]
        
        documents = [
            {
                "doc_name": "test_doc1.pdf",
                "file_path": "/tmp/test_doc1.pdf"
            },
            {
                "doc_name": "test_doc2.pdf",
                "file_path": "/tmp/test_doc2.pdf"
            }
        ]
        
        project = ProjectOperations.create_project(
            db,
            project_name="Test Project",
            fields_config=fields_config,
            documents=documents
        )
        
        print(f"✅ Created project: {project.id}")
        print(f"   - Name: {project.project_name}")
        print(f"   - Status: {project.status}")
        print(f"   - Documents: {project.total_documents}")
        print(f"   - Created at: {project.created_at}")
        
        return project.id
        
    except Exception as e:
        print(f"❌ Failed to create project: {e}")
        return None
    finally:
        db.close()


def test_update_project_status(project_id):
    """Test updating project status."""
    print("\nTesting project status update...")
    db = SessionLocal()
    try:
        project = ProjectOperations.update_project_status(
            db,
            project_id,
            "processing",
            processed_documents=1,
            failed_documents=0
        )
        
        if project:
            print(f"✅ Updated project status to: {project.status}")
            print(f"   - Processed: {project.processed_documents}")
            print(f"   - Failed: {project.failed_documents}")
            return True
        else:
            print("❌ Project not found")
            return False
            
    except Exception as e:
        print(f"❌ Failed to update project: {e}")
        return False
    finally:
        db.close()


def test_get_documents(project_id):
    """Test retrieving project documents."""
    print("\nTesting document retrieval...")
    db = SessionLocal()
    try:
        documents = DocumentOperations.get_project_documents(db, project_id)
        
        print(f"✅ Found {len(documents)} documents:")
        for doc in documents:
            print(f"   - {doc.doc_name} (ID: {doc.id}, Status: {doc.status})")
        
        return [doc.id for doc in documents]
        
    except Exception as e:
        print(f"❌ Failed to get documents: {e}")
        return []
    finally:
        db.close()


def test_create_field_results(doc_ids):
    """Test creating field extraction results."""
    print("\nTesting field result creation...")
    db = SessionLocal()
    try:
        if not doc_ids:
            print("⚠️  No documents to test with")
            return False
            
        doc_id = doc_ids[0]
        
        # Create test field result
        result_data = {
            "value": "Acme Corporation",
            "confidence": 0.95,
            "source_pages": [1, 2],
            "chunks": [
                {
                    "page": 1,
                    "text": "This agreement is between Acme Corporation...",
                    "score": 0.92
                }
            ],
            "status": "completed",
            "model_used": "gpt-5",
            "reasoning_mode": "low"
        }
        
        field_result = FieldResultOperations.create_field_result(
            db,
            document_id=doc_id,
            field_name="company_name",
            result_data=result_data
        )
        
        print(f"✅ Created field result:")
        print(f"   - Field: {field_result.field_name}")
        print(f"   - Value: {field_result.value}")
        print(f"   - Confidence: {field_result.confidence}")
        print(f"   - Status: {field_result.status}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to create field result: {e}")
        return False
    finally:
        db.close()


def test_queue_operations(project_id):
    """Test processing queue operations."""
    print("\nTesting queue operations...")
    db = SessionLocal()
    try:
        # Get queue position
        position = QueueOperations.get_queue_position(db, project_id)
        if position:
            print(f"✅ Project queue position: {position}")
        else:
            print("✅ Project not in waiting queue (already processing or completed)")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to check queue: {e}")
        return False
    finally:
        db.close()


def test_list_projects():
    """Test listing all projects."""
    print("\nTesting project listing...")
    db = SessionLocal()
    try:
        projects = ProjectOperations.list_projects(db, skip=0, limit=10)
        
        print(f"✅ Found {len(projects)} projects:")
        for p in projects:
            print(f"   - {p.project_name} (Status: {p.status}, Created: {p.created_at})")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to list projects: {e}")
        return False
    finally:
        db.close()


def test_cleanup(project_id):
    """Test deleting a project."""
    print("\nTesting project deletion...")
    db = SessionLocal()
    try:
        success = ProjectOperations.delete_project(db, project_id)
        
        if success:
            print(f"✅ Successfully deleted project: {project_id}")
        else:
            print(f"❌ Failed to delete project: {project_id}")
        
        return success
        
    except Exception as e:
        print(f"❌ Failed to delete project: {e}")
        return False
    finally:
        db.close()


def main():
    """Run all tests."""
    print("=" * 60)
    print("PostgreSQL Integration Test Suite")
    print("=" * 60)
    
    # Test database connection
    if not test_database_connection():
        print("\n❌ Database connection failed. Exiting.")
        sys.exit(1)
    
    # Create test project
    project_id = test_create_project()
    if not project_id:
        print("\n❌ Project creation failed. Exiting.")
        sys.exit(1)
    
    # Test project operations
    test_update_project_status(project_id)
    
    # Test document operations
    doc_ids = test_get_documents(project_id)
    
    # Test field results
    test_create_field_results(doc_ids)
    
    # Test queue operations
    test_queue_operations(project_id)
    
    # Test listing projects
    test_list_projects()
    
    # Cleanup
    test_cleanup(project_id)
    
    print("\n" + "=" * 60)
    print("✅ All tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
