# Regenerate Function Verification

## Overview

This document verifies that the regenerate endpoint will properly use all the updated features including:
1. ✅ Improved BM25 page selection with updated parameters
2. ✅ Validation error handling with fallback
3. ✅ Database field compatibility
4. ✅ Multi-page coverage (threshold=0.15, max=5)

## Regenerate Flow

### 1. API Endpoint

**URL:** `POST /project/{project_id}/documents/{document_id}/regenerate?field_names=target`

**Location:** `app/api/project.py` (lines 1053-1138)

### 2. What Happens

```python
# 1. Clear existing field results for specified fields
field_result_query = db.query(FieldResult).filter(FieldResult.document_id == document_id)
if fields_to_regenerate:
    field_result_query = field_result_query.filter(FieldResult.field_name.in_(fields_to_regenerate))
field_result_query.delete()

# 2. Clear queue entries
db.query(FieldQueue).filter(
    FieldQueue.document_id == document_id,
    FieldQueue.field_name.in_(fields_to_regenerate)
).delete()

# 3. Reset document status
document.status = "pending"
document.completed_at = None
document.error_message = None

# 4. Enqueue for reprocessing with field_names parameter
job = document_queue.enqueue(
    process_document,
    document_id=document_id,
    project_id=project_id,
    is_regeneration=True,
    field_names=fields_to_regenerate,  # ✅ Passed to worker
    job_id=f"doc_{document_id}_{timestamp}",
    timeout="30m"
)
```

### 3. Process Document Worker

**Location:** `app/api/worker_parallel.py` (lines 160-439)

```python
def process_document(
    project_id: str,
    document_id: str,
    is_regeneration: bool = False,
    field_names: list = None,  # ✅ Receives field_names
    **kwargs
):
    # 1. Skip chunk creation if regeneration
    if is_regeneration:
        logger.info("Regeneration mode: Skipping chunk creation")
        # Verify existing chunks in Weaviate
        has_chunks = weaviate_client.has_existing_chunks(project_id, document_id)
    
    # 2. Filter fields to process
    requested_fields = field_names or []  # ✅ Uses passed field_names
    
    if requested_fields:
        # Filter to only requested fields
        fields_config = [
            field for field in fields_config 
            if field.get('field_name') in requested_fields
        ]
        logger.info(f"Filtered to {len(fields_config)} requested fields")
    
    # 3. Spawn field workers for each field
    for field_config in fields_config:
        field_queue.enqueue(
            process_field,  # ✅ Will use updated page selection
            project_id=project_id,
            document_id=document_id,
            field_name=field_config['field_name'],
            ...
        )
```

### 4. Process Field Worker

**Location:** `app/api/worker_parallel.py` (lines 580-800)

```python
def process_field(...):
    # 1. Get context chunks from Weaviate
    context_chunks = weaviate_client.hybrid_search(...)
    
    # 2. Generate initial answer
    initial_response = llm_service.generate_answer(...)
    initial_answer = initial_response.get("verbatim_answer", "")
    
    # 3. Validate with fallback ✅ NEW
    try:
        validated_response = validation_system.validate_and_improve(...)
    except Exception as validation_error:
        logger.warning("Validation failed. Using initial answer without validation.")
        validated_response = {
            "final_answer": initial_answer,
            "final_answer_explanation": initial_explanation or "",
            "final_confidence_score": 0.5
        }
    
    # 4. Select pages with BM25 ✅ UPDATED PARAMETERS
    selected_page_keys, page_scores = llm_service.select_top_pages(
        prompt=prompt,
        answer=validated_response["final_answer"],
        context_pages=context_pages,
        page_numbers=all_pages,
        collection_id=project_id,
        context_chunks=context_chunks,
        explanation=validated_response.get("final_answer_explanation")
    )
    # Uses threshold=0.15, max_results=5 ✅
    
    # 5. Store results with metadata ✅ DATABASE FIX
    chunks_with_metadata = {
        "chunks": chunks_data,
        "page_scores": page_scores,  # ✅ Stored in JSON
        "unified_references": unified_references  # ✅ Stored in JSON
    }
    
    FieldResultOperations.create_field_result(
        db,
        document_id=document_id,
        field_name=field_name,
        result_data={
            "value": final_answer,
            "source_pages": source_pages,  # ✅ Now includes 3-5 pages
            "chunks": chunks_with_metadata,  # ✅ All metadata in JSON
            "confidence": confidence,
            "status": "completed"
        }
    )
```

## Verification Checklist

### ✅ All Features Will Be Used

1. **✅ Improved Page Selection**
   - Location: `app/core/llm.py` lines 516-521
   - Parameters: `threshold=0.15`, `max_results=5`
   - Result: Will return 3-5 pages instead of 1

2. **✅ Validation Fallback**
   - Location: `app/api/worker_parallel.py` lines 665-677
   - Behavior: If validation fails, uses initial answer with confidence=0.5
   - Result: No crashes on empty validation responses

3. **✅ Database Compatibility**
   - Location: `app/api/worker_parallel.py` lines 762-785
   - Storage: `page_scores` and `unified_references` in `chunks` JSON field
   - Result: No "invalid keyword argument" errors

4. **✅ Field Filtering**
   - Location: `app/api/worker_parallel.py` lines 383-399
   - Behavior: Only processes specified fields
   - Result: Only "target" field will be regenerated

## Expected Behavior for Your Test

### Command
```bash
curl -X POST "http://localhost:8001/project/66ffa875-9399-4c59-903c-9ed396e14099/documents/89cd5fbd-d6a4-4fd2-858c-d466272ffcbd/regenerate?field_names=target"
```

### Expected Flow

1. **API Response (Immediate)**
```json
{
  "status": "queued",
  "message": "Document 89cd5fbd-d6a4-4fd2-858c-d466272ffcbd has been queued for reprocessing",
  "job_id": "doc_89cd5fbd-d6a4-4fd2-858c-d466272ffcbd_1730277000",
  "document_id": "89cd5fbd-d6a4-4fd2-858c-d466272ffcbd",
  "project_id": "66ffa875-9399-4c59-903c-9ed396e14099",
  "fields_to_regenerate": ["target"]
}
```

2. **Worker Processing**
```
[Worker abc123] Regeneration mode: Skipping chunk creation
[Worker abc123] Existing chunks found: True
[Worker abc123] Filtered to 1 requested fields out of 7 total fields
[Worker abc123] Spawning field workers for 1 fields
[Field Worker xyz789] Processing field 'target' for document 89cd5fbd...
[Field Worker xyz789] Retrieved 10 context chunks
[Field Worker xyz789] Generated initial answer
[Field Worker xyz789] Validation successful (or fallback used)
[Field Worker xyz789] Selected 3 pages using BM25 scoring: [3, 5, 6]
[Field Worker xyz789] Page scores: {"3": 1.0, "5": 0.92, "6": 0.85}
[Field Worker xyz789] Successfully completed field 'target'
```

3. **Result Structure**
```json
{
  "field_name": "target",
  "value": "OCM Luxembourg POW VI Omega S.à.r.l. ...",
  "confidence": 0.98,
  "source_pages": [3, 5, 6],  // ✅ Multiple pages now!
  "chunks": {
    "chunks": [...],
    "page_scores": {  // ✅ New
      "3": 1.0,
      "5": 0.92,
      "6": 0.85
    },
    "unified_references": [  // ✅ New
      {
        "file_name": "document",
        "page_number": 3,
        "extract": "...",
        "page_score": 1.0
      },
      {
        "file_name": "document",
        "page_number": 5,
        "extract": "...",
        "page_score": 0.92
      },
      {
        "file_name": "document",
        "page_number": 6,
        "extract": "...",
        "page_score": 0.85
      }
    ]
  },
  "status": "completed"
}
```

## Monitoring Commands

### 1. Check Worker Logs
```bash
# Watch for page selection
docker-compose logs -f workers | grep "Page selection"

# Expected output:
# "Page selection - doc_id=89cd5fbd: selected 3 pages with scores >= 0.5"
# "Page scores: {'89cd5fbd::page:3': 1.0, '89cd5fbd::page:5': 0.92, '89cd5fbd::page:6': 0.85}"
```

### 2. Check for Validation Fallback
```bash
# Watch for validation warnings
docker-compose logs -f workers | grep "Validation failed"

# If validation fails, you'll see:
# "Validation failed: Empty text extracted. Using initial answer without validation."
```

### 3. Check for Database Errors
```bash
# Watch for database errors (should see none)
docker-compose logs -f workers | grep -i "invalid keyword"

# Expected: No output (no errors)
```

### 4. Get Results
```bash
# Get field results
curl "http://localhost:8001/api/project/66ffa875-9399-4c59-903c-9ed396e14099/results" | jq '.documents["89cd5fbd-d6a4-4fd2-858c-d466272ffcbd"].field_results[] | select(.field_name == "target")'
```

## What to Look For

### ✅ Success Indicators

1. **Multiple Pages Selected**
   - `source_pages` should have 2-5 pages (not just 1)
   - Pages should match those cited in explanation

2. **Page Scores Present**
   - `chunks.page_scores` should have scores for each page
   - Scores should be between 0.5 and 1.0

3. **Unified References**
   - `chunks.unified_references` should have extracts from each page
   - Each reference should have `file_name`, `page_number`, `extract`, `page_score`

4. **No Errors**
   - No "invalid keyword argument" errors
   - No "Empty text extracted" crashes
   - Field status = "completed"

### ⚠️ Potential Issues

1. **Still Only 1 Page**
   - Check if there's genuinely a big gap (>0.15) in scores
   - Check logs for "Page selection" messages

2. **Validation Fallback Used**
   - Check for "Validation failed" warnings
   - Confidence will be 0.5 instead of higher

3. **Database Errors**
   - Should not happen with current fixes
   - If they do, check `chunks` field structure

## Summary

✅ **All updates are properly integrated into the regenerate flow:**

1. Regenerate endpoint passes `field_names` to worker
2. Worker filters to only process specified fields
3. Field extraction uses updated page selection (threshold=0.15, max=5)
4. Validation has fallback for empty responses
5. Database storage uses JSON fields for new metadata

**Your test command will:**
- Only regenerate the "target" field
- Use all the latest improvements
- Return 3-5 relevant pages instead of 1
- Include page scores and unified references
- Handle validation errors gracefully

Run the command and check the logs to see the improvements in action!
