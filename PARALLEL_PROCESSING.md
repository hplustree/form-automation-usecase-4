# Parallel Processing Architecture

## Overview

The SISO Pipeline has been refactored to support parallel processing at multiple levels:
1. **Parallel Document Processing**: Multiple documents can be processed simultaneously
2. **Queued Field Extraction**: Each field extraction is a separate queue job
3. **Individual Field Saving**: Results are saved to the database immediately upon completion

## Architecture Changes

### Previous Architecture (Sequential)
```
Project → Process Doc1 → Extract Fields (parallel) → Process Doc2 → Extract Fields (parallel) → Complete
```

### New Architecture (Parallel)
```
Project ┬→ Process Doc1 ─┬→ Extract Field1 → Save to DB
        │                ├→ Extract Field2 → Save to DB
        │                └→ Extract Field3 → Save to DB
        ├→ Process Doc2 ─┬→ Extract Field1 → Save to DB
        │                ├→ Extract Field2 → Save to DB
        │                └→ Extract Field3 → Save to DB
        └→ Process Doc3 ─┬→ Extract Field1 → Save to DB
                         ├→ Extract Field2 → Save to DB
                         └→ Extract Field3 → Save to DB
```

## Components

### 1. Queue System

The system now uses three separate RQ queues:

- **`projects` queue**: Handles project initialization and coordination
- **`documents` queue**: Processes document chunking and embedding
- **`fields` queue**: Performs individual field extractions

### 2. Database Tables

New tables have been added to track queue status:

#### `document_queue`
- Tracks document processing tasks
- Manages retry logic and error handling
- Ensures documents are processed in priority order

#### `field_queue`
- Tracks individual field extraction tasks
- Ensures fields are only processed after document chunks are ready
- Manages dependencies between documents and fields

### 3. Worker Types

The system now runs three types of workers:

#### Document Workers (`NUM_DOC_WORKERS`)
- Process document chunking and embedding
- Store chunks in Weaviate
- Enqueue field extraction tasks

#### Field Workers (`NUM_FIELD_WORKERS`)
- Extract individual fields from documents
- Save results immediately to database
- Handle validation and confidence scoring

#### Project Workers (`NUM_PROJECT_WORKERS`)
- Coordinate overall project processing
- Monitor progress and update status
- Handle project-level error recovery

## Configuration

### Environment Variables

```bash
# Worker configuration
NUM_DOC_WORKERS=3        # Number of document processing workers
NUM_FIELD_WORKERS=5      # Number of field extraction workers
NUM_PROJECT_WORKERS=1    # Number of project coordination workers

# Processing limits
MAX_RETRIES=3            # Maximum retries for failed tasks
REDIS_TTL_SECONDS=604800 # TTL for Redis data (7 days)
```

### Docker Compose

The `docker-compose.yml` has been updated to use the parallel worker launcher:

```yaml
workers:
  environment:
    - NUM_DOC_WORKERS=${NUM_DOC_WORKERS:-3}
    - NUM_FIELD_WORKERS=${NUM_FIELD_WORKERS:-5}
    - NUM_PROJECT_WORKERS=${NUM_PROJECT_WORKERS:-1}
  command: python -m app.utils.worker_launcher_parallel
```

## Benefits

### 1. Improved Performance
- Documents are processed in parallel, reducing total processing time
- Field extractions happen independently, maximizing resource utilization
- No waiting for all fields in a document to complete before moving to the next

### 2. Better Fault Tolerance
- Individual field failures don't block entire document processing
- Failed tasks can be retried independently
- Partial results are saved immediately

### 3. Real-time Progress Updates
- Each field result is saved as soon as it's completed
- Users can see partial results while processing continues
- Better visibility into processing status

### 4. Resource Optimization
- Different worker pools for different task types
- Can scale workers based on workload characteristics
- Better CPU and memory utilization

## Migration Guide

### 1. Database Migration

Run the Alembic migration to create new tables:

```bash
docker-compose exec api alembic upgrade head
```

### 2. Update Environment Variables

Add the new worker configuration to your `.env` file:

```bash
# Parallel processing configuration
NUM_DOC_WORKERS=3
NUM_FIELD_WORKERS=5
NUM_PROJECT_WORKERS=1
```

### 3. Restart Services

```bash
docker-compose down
docker-compose up -d
```

## Monitoring

### Check Queue Status

```python
import redis
from rq import Queue

r = redis.Redis(host='localhost', port=6379)

# Check document queue
doc_queue = Queue('documents', connection=r)
print(f"Document queue: {len(doc_queue)} jobs")

# Check field queue
field_queue = Queue('fields', connection=r)
print(f"Field queue: {len(field_queue)} jobs")

# Check project queue
project_queue = Queue('projects', connection=r)
print(f"Project queue: {len(project_queue)} jobs")
```

### Database Monitoring

```sql
-- Check document processing status
SELECT status, COUNT(*) 
FROM document_queue 
GROUP BY status;

-- Check field processing status
SELECT status, COUNT(*) 
FROM field_queue 
GROUP BY status;

-- View active workers
SELECT worker_id, COUNT(*) 
FROM field_queue 
WHERE status = 'processing' 
GROUP BY worker_id;
```

## Troubleshooting

### Issue: Fields not processing
- Check if document chunks are ready: `status = 'chunks_ready'` in documents table
- Verify document_queue entry is marked as completed
- Check field_queue for error messages

### Issue: Slow processing
- Increase number of workers in `.env`
- Check for rate limiting in LLM API calls
- Monitor Redis memory usage

### Issue: Duplicate field results
- Check for multiple field_queue entries for same document/field
- Verify field completion is properly marked in queue

## Performance Tuning

### Optimal Worker Ratios

For typical workloads:
- 1 document worker per 2-3 field workers
- More field workers if fields are complex
- Single project worker is usually sufficient

### Memory Considerations

- Each worker uses ~200-500MB RAM
- Document workers need more memory for chunk processing
- Field workers are more CPU-intensive

### Scaling Guidelines

```bash
# For small projects (< 10 documents)
NUM_DOC_WORKERS=2
NUM_FIELD_WORKERS=3

# For medium projects (10-50 documents)
NUM_DOC_WORKERS=3
NUM_FIELD_WORKERS=5

# For large projects (> 50 documents)
NUM_DOC_WORKERS=5
NUM_FIELD_WORKERS=10
```
