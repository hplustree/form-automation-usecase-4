# Quick Start: Hierarchical Workers

## What You Asked For

You wanted a hierarchical worker system where:
- **1 project worker** spawns **2 document workers**
- **Each document worker** spawns **5 field workers**
- Workers only process tasks assigned to their parent
- For 2 projects: 2 project workers → 4 doc workers → 20 field workers

## ✅ Implementation Complete

The system now supports this exact configuration!

## How to Enable

### Step 1: Update `.env` File

Add these lines to your `.env` file:

```bash
# Enable hierarchical mode
USE_HIERARCHICAL_WORKERS=true

# Configuration: 1 project → 2 doc workers → 5 field workers each
NUM_PROJECT_WORKERS=1
NUM_DOC_WORKERS_PER_PROJECT=2
NUM_FIELD_WORKERS_PER_DOC=5
```

### Step 2: Restart Workers

```bash
docker-compose restart workers
```

### Step 3: Verify Configuration

```bash
# Check worker logs
docker-compose logs workers | head -20

# You should see:
# "Starting HIERARCHICAL workers: 1 project workers, 2 doc workers per project, 5 field workers per doc"
```

## How It Works

### When You Submit a Project:

1. **Project Worker** picks up the project
   - Spawns 2 dedicated document workers
   - Creates queue: `documents:{project_id}`
   - Enqueues all documents

2. **Document Worker 1** picks up Document 1
   - Processes document (chunks, embeddings)
   - Spawns 5 dedicated field workers
   - Creates queue: `fields:{project_id}:{doc1_id}`
   - Enqueues all fields for Document 1

3. **Document Worker 2** picks up Document 2
   - Processes document (chunks, embeddings)
   - Spawns 5 dedicated field workers
   - Creates queue: `fields:{project_id}:{doc2_id}`
   - Enqueues all fields for Document 2

4. **Field Workers** (10 total: 5 per document)
   - 5 workers process fields from Document 1
   - 5 workers process fields from Document 2
   - Each worker only processes fields from its assigned document

### Resource Allocation

**For 1 Project:**
- 1 project worker
- 2 document workers
- 10 field workers (5 per document)
- **Total: 13 workers**

**For 2 Projects:**
- 2 project workers
- 4 document workers (2 per project)
- 20 field workers (5 per document × 2 documents per project)
- **Total: 26 workers**

## Testing

### Test the Configuration

```bash
# Run the test script
python test_hierarchical_workers.py

# Monitor queue activity in real-time
python test_hierarchical_workers.py --monitor 60
```

### Submit a Test Project

```bash
curl -X POST http://localhost:8001/api/project/submit \
  -F "project_name=test-hierarchical" \
  -F "field_names=[\"effective_date\",\"parties\"]" \
  -F "template_name=spa_fields" \
  -F "files=@document1.pdf" \
  -F "files=@document2.pdf"
```

### Watch Workers Spawn

```bash
# Terminal 1: Watch worker logs
docker-compose logs -f workers

# You'll see:
# [Project Worker 1] Spawning 2 document workers for project {id}
# [Doc Worker 1] Spawning 5 field workers for document {doc1_id}
# [Doc Worker 2] Spawning 5 field workers for document {doc2_id}
```

### Check Queue Structure

```bash
docker-compose exec workers rq info --url redis://redis:6379/0

# You should see queues like:
# - projects (global)
# - documents:{project_id} (project-specific)
# - fields:{project_id}:{doc_id} (document-specific)
```

## Configuration Examples

### Small Projects (< 5 documents)
```bash
NUM_DOC_WORKERS_PER_PROJECT=1
NUM_FIELD_WORKERS_PER_DOC=3
```

### Medium Projects (5-20 documents) - **Your Use Case**
```bash
NUM_DOC_WORKERS_PER_PROJECT=2
NUM_FIELD_WORKERS_PER_DOC=5
```

### Large Projects (> 20 documents)
```bash
NUM_DOC_WORKERS_PER_PROJECT=3
NUM_FIELD_WORKERS_PER_DOC=5
```

## Switching Back to Traditional Mode

If you want to go back to the old system:

```bash
# In .env
USE_HIERARCHICAL_WORKERS=false

# Restart
docker-compose restart workers
```

## Key Differences from Before

### Before (Traditional Parallel):
```
All Projects → 2 Doc Workers (shared) → 10 Field Workers (shared)
```
- Workers shared across all projects
- Fixed worker pools
- Potential resource contention

### After (Hierarchical):
```
Project 1 → 2 Doc Workers → 10 Field Workers (5 per doc)
Project 2 → 2 Doc Workers → 10 Field Workers (5 per doc)
```
- Dedicated workers per project
- Dynamic worker spawning
- Complete isolation

## Troubleshooting

### Workers Not Spawning?

Check the environment variable:
```bash
docker-compose exec workers env | grep USE_HIERARCHICAL_WORKERS
# Should show: USE_HIERARCHICAL_WORKERS=true
```

### Not Seeing Hierarchical Queues?

The queues are created dynamically when processing starts. Submit a project first, then check:
```bash
python test_hierarchical_workers.py
```

### High Memory Usage?

Reduce worker counts:
```bash
NUM_DOC_WORKERS_PER_PROJECT=1
NUM_FIELD_WORKERS_PER_DOC=3
```

## Summary

✅ **Implemented:** Hierarchical worker allocation  
✅ **Configuration:** 1 project → 2 doc workers → 5 field workers  
✅ **Isolation:** Each project/document gets dedicated workers  
✅ **Scalability:** Automatically scales with number of projects  

**Enable it now:** Set `USE_HIERARCHICAL_WORKERS=true` in `.env` and restart workers!

For detailed documentation, see: `HIERARCHICAL_WORKERS.md`
