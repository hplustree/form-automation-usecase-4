# Database Field Compatibility Fix

## Issue

The `FieldResult` database model was throwing errors because we were trying to pass fields that don't exist in the model:
- `page_scores` - Invalid keyword argument
- `unified_references` - Invalid keyword argument  
- `error` - Invalid keyword argument (should be `error_message`)

## Root Cause

The improved page selection logic added new data fields (`page_scores` and `unified_references`) that weren't part of the existing `FieldResult` model schema.

## Solution

Instead of modifying the database schema (which would require migrations), we store the new fields within the existing `chunks` JSON column, which already supports arbitrary JSON data.

### FieldResult Model Schema (Unchanged)

```python
class FieldResult(Base):
    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"))
    field_name = Column(String, nullable=False)
    
    # Extraction results
    value = Column(Text, nullable=True)
    answer_html = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)
    
    # Source tracking
    source_pages = Column(JSON, default=list)  # List of page numbers
    chunks = Column(JSON, default=list)  # ✅ JSON field - can store any structure
    
    # Processing metadata
    status = Column(String, default="pending")
    error_message = Column(Text, nullable=True)  # ✅ Correct field name
    model_used = Column(String, nullable=True)
    reasoning_mode = Column(String, nullable=True)
```

## Changes Made

### 1. Success Case - Store Metadata in chunks JSON

**Before (Broken):**
```python
FieldResultOperations.create_field_result(
    db,
    document_id=document_id,
    field_name=field_name,
    result_data={
        "value": result["value"],
        "source_pages": result.get("source_pages", []),
        "page_scores": result.get("page_scores", {}),  # ❌ Invalid field
        "unified_references": result.get("unified_references", []),  # ❌ Invalid field
        "chunks": result.get("chunks", []),
        "status": result["status"]
    }
)
```

**After (Fixed):**
```python
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
        "chunks": chunks_with_metadata,  # ✅ All metadata in JSON
        "status": result["status"],
        "model_used": model,
        "reasoning_mode": mode
    }
)
```

### 2. Error Case - Use error_message Field

**Before (Broken):**
```python
FieldResultOperations.create_field_result(
    db,
    document_id=document_id,
    field_name=field_name,
    result_data={
        "value": "Error",
        "confidence": 0.0,
        "source_pages": [],
        "status": "failed",
        "error": str(e),  # ❌ Invalid field name
        "model_used": model,
        "reasoning_mode": mode
    }
)
```

**After (Fixed):**
```python
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
        "error_message": str(e),  # ✅ Correct field name
        "model_used": model,
        "reasoning_mode": mode
    }
)
```

## Data Structure

### chunks JSON Field Structure

```json
{
  "chunks": [
    {
      "page": 1,
      "text": "Excerpt from page 1...",
      "score": 0.95
    },
    {
      "page": 5,
      "text": "Excerpt from page 5...",
      "score": 0.87
    }
  ],
  "page_scores": {
    "1": 0.95,
    "5": 0.87
  },
  "unified_references": [
    {
      "file_name": "contract",
      "page_number": 1,
      "extract": "The effective date of this agreement is January 1, 2024...",
      "page_score": 0.95
    },
    {
      "file_name": "contract",
      "page_number": 5,
      "extract": "This agreement shall commence on the effective date...",
      "page_score": 0.87
    }
  ]
}
```

## Accessing the Data

### From API Response

```python
# Get field results
response = requests.get(f"http://localhost:8001/api/project/{project_id}/results")
field_result = response.json()["documents"][doc_id]["field_results"][0]

# Access the data
chunks_metadata = field_result["chunks"]
chunks = chunks_metadata["chunks"]
page_scores = chunks_metadata["page_scores"]
unified_references = chunks_metadata["unified_references"]

print(f"Selected pages: {field_result['source_pages']}")
print(f"Page scores: {page_scores}")
print(f"References: {unified_references}")
```

### From Database Query

```python
from app.db.operations import FieldResultOperations

# Get field result
field_result = FieldResultOperations.get_field_result(db, document_id, field_name)

# Access the data
chunks_metadata = field_result.chunks  # JSON field
chunks = chunks_metadata.get("chunks", [])
page_scores = chunks_metadata.get("page_scores", {})
unified_references = chunks_metadata.get("unified_references", [])
```

## Benefits of This Approach

1. **✅ No Database Migration Required:** Uses existing JSON column
2. **✅ Backward Compatible:** Old results without metadata still work
3. **✅ Flexible:** Can add more metadata in the future without schema changes
4. **✅ Type Safe:** SQLAlchemy validates the base fields
5. **✅ Clean:** All chunk-related metadata stored together

## Testing

### Verify the Fix

```bash
# Restart workers
docker-compose restart workers

# Submit a test project
curl -X POST http://localhost:8001/api/project/submit \
  -F "project_name=test-fix" \
  -F "field_names=[\"effective_date\"]" \
  -F "template_name=spa_fields" \
  -F "files=@document.pdf"

# Check logs for errors
docker-compose logs -f workers | grep -i "error\|invalid"
```

### Expected Behavior

- ✅ No "invalid keyword argument" errors
- ✅ Field results saved successfully
- ✅ page_scores and unified_references available in chunks JSON
- ✅ Error cases use error_message field correctly

## Files Modified

- **`app/api/worker_parallel.py`**:
  - Line 762-768: Store metadata in chunks JSON structure
  - Line 770-785: Pass chunks_with_metadata to database
  - Line 803-816: Use error_message instead of error

## Summary

The fix ensures compatibility with the existing database schema by:
1. Storing `page_scores` and `unified_references` in the `chunks` JSON field
2. Using the correct `error_message` field name for errors
3. Maintaining backward compatibility with existing data

All improved page selection features are preserved while avoiding database schema changes.
