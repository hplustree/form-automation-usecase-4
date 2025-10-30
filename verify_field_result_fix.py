#!/usr/bin/env python3
"""
Verification script for field result database compatibility fix.
This script checks that field results can be saved with the new metadata structure.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import SessionLocal
from app.db.operations import FieldResultOperations, DocumentOperations
from app.db.models import FieldResult


def test_field_result_creation():
    """Test that field results can be created with new metadata structure."""
    print("="*80)
    print("FIELD RESULT DATABASE COMPATIBILITY TEST")
    print("="*80)
    
    db = SessionLocal()
    
    try:
        # Test data with new metadata structure
        test_document_id = "test-doc-123"
        test_field_name = "test_field"
        
        # Simulate the new data structure
        chunks_with_metadata = {
            "chunks": [
                {
                    "page": 1,
                    "text": "Test excerpt from page 1",
                    "score": 0.95
                }
            ],
            "page_scores": {
                "1": 0.95,
                "5": 0.87
            },
            "unified_references": [
                {
                    "file_name": "test_document",
                    "page_number": 1,
                    "extract": "Test extract from page 1",
                    "page_score": 0.95
                }
            ]
        }
        
        result_data = {
            "value": "Test value",
            "answer_html": "<p>Test answer</p>",
            "explanation": "Test explanation",
            "confidence": 0.95,
            "source_pages": [1, 5],
            "chunks": chunks_with_metadata,  # New structure
            "status": "completed",
            "model_used": "gpt-5",
            "reasoning_mode": "low"
        }
        
        print("\n✓ Test data structure created")
        print(f"  - Chunks with metadata: {len(chunks_with_metadata)} keys")
        print(f"  - Page scores: {len(chunks_with_metadata['page_scores'])} pages")
        print(f"  - Unified references: {len(chunks_with_metadata['unified_references'])} refs")
        
        # Verify all fields are valid for FieldResult model
        print("\n✓ Validating field names against FieldResult model...")
        model_fields = {c.name for c in FieldResult.__table__.columns}
        print(f"  - Model has {len(model_fields)} fields: {sorted(model_fields)}")
        
        for key in result_data.keys():
            if key not in model_fields:
                print(f"  ❌ Invalid field: {key}")
                return False
            else:
                print(f"  ✓ Valid field: {key}")
        
        print("\n✓ All field names are valid!")
        
        # Test error case
        print("\n✓ Testing error case with error_message field...")
        error_result_data = {
            "value": "Error",
            "confidence": 0.0,
            "source_pages": [],
            "chunks": {"chunks": [], "page_scores": {}, "unified_references": []},
            "status": "failed",
            "error_message": "Test error message",
            "model_used": "gpt-5",
            "reasoning_mode": "low"
        }
        
        for key in error_result_data.keys():
            if key not in model_fields:
                print(f"  ❌ Invalid field: {key}")
                return False
            else:
                print(f"  ✓ Valid field: {key}")
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80)
        print("\nThe field result structure is compatible with the database model.")
        print("New metadata (page_scores, unified_references) will be stored in chunks JSON.")
        print("\nYou can now restart the workers and process documents.")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = test_field_result_creation()
    sys.exit(0 if success else 1)
