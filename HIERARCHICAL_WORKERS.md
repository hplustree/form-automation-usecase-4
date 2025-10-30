# Hierarchical Worker Architecture

## Overview

The SISO Pipeline now supports **hierarchical worker allocation**, where workers are spawned dynamically in a parent-child relationship. This ensures that each project gets dedicated resources and workers only process tasks assigned to their parent.

## Architecture Comparison

### Traditional Parallel Mode (Default)
```
Global Queues:
┌─────────────────────────────────────────────────┐
│ Projects Queue (1 worker)                       │
│   ↓                                             │
│ Documents Queue (2 workers - shared)            │
│   ↓                                             │
│ Fields Queue (10 workers - shared)              │
└─────────────────────────────────────────────────┘

All projects share the same worker pools
```

### Hierarchical Mode (New)
```
Project 1:
  Project Worker 1
    ├─ Doc Worker 1 (for Project 1)
    │   ├─ Field Worker 1 (for Doc 1)
    │   ├─ Field Worker 2 (for Doc 1)
    │   ├─ Field Worker 3 (for Doc 1)
    │   ├─ Field Worker 4 (for Doc 1)
    │   └─ Field Worker 5 (for Doc 1)
    └─ Doc Worker 2 (for Project 1)
        ├─ Field Worker 1 (for Doc 2)
        ├─ Field Worker 2 (for Doc 2)
        ├─ Field Worker 3 (for Doc 2)
        ├─ Field Worker 4 (for Doc 2)
        └─ Field Worker 5 (for Doc 2)

Project 2:
  Project Worker 2
    ├─ Doc Worker 1 (for Project 2)
    │   └─ 5 Field Workers...
    └─ Doc Worker 2 (for Project 2)
        └─ 5 Field Workers...

Each project has isolated worker hierarchy
```

## Key Features

### 1. **Isolated Worker Pools**
- Each project gets dedicated document workers
- Each document gets dedicated field workers
- No resource contention between projects

### 2. **Scoped Queues**
- **Project-specific document queues**: `documents:{project_id}`
- **Document-specific field queues**: `fields:{project_id}:{document_id}`
- Workers only listen to their assigned queue

### 3. **Dynamic Worker Spawning**
- Workers are spawned on-demand when processing starts
- Parent workers manage child worker lifecycle
- Automatic cleanup when processing completes

### 4. **Predictable Resource Allocation**
With configuration:
- `NUM_PROJECT_WORKERS=2`
- `NUM_DOC_WORKERS_PER_PROJECT=2`
- `NUM_FIELD_WORKERS_PER_DOC=5`

Processing 2 projects results in:
- **2 project workers** (1 per project)
- **4 document workers** (2 per project)
- **20 field workers** (5 per document × 2 documents per project × 2 projects)

## Configuration

### Environment Variables

#### Enable Hierarchical Mode
```bash
# Set to 'true' to enable hierarchical worker allocation
USE_HIERARCHICAL_WORKERS=true
```

#### Hierarchical Mode Settings
```bash
# Number of project workers (typically 1 per concurrent project)
NUM_PROJECT_WORKERS=1

# Number of document workers spawned per project
NUM_DOC_WORKERS_PER_PROJECT=2

# Number of field workers spawned per document
NUM_FIELD_WORKERS_PER_DOC=5
```

#### Traditional Parallel Mode Settings
```bash
# Used when USE_HIERARCHICAL_WORKERS=false
NUM_DOC_WORKERS=2
NUM_FIELD_WORKERS=10
NUM_PROJECT_WORKERS=1
```

### Docker Compose Configuration

Update your `.env` file:
```bash
# Enable hierarchical mode
USE_HIERARCHICAL_WORKERS=true

# Hierarchical worker configuration
NUM_PROJECT_WORKERS=1
NUM_DOC_WORKERS_PER_PROJECT=2
NUM_FIELD_WORKERS_PER_DOC=5
```

Then restart the workers:
```bash
docker-compose restart workers
```

## Worker Lifecycle

### 1. Project Worker Starts
```
1. Project worker picks up project from 'projects' queue
2. Spawns NUM_DOC_WORKERS_PER_PROJECT document workers
3. Creates project-specific queue: documents:{project_id}
4. Enqueues all documents to project-specific queue
5. Monitors document completion
```

### 2. Document Worker Processes Document
```
1. Document worker picks up document from documents:{project_id}
2. Processes document (chunking, embeddings, Weaviate storage)
3. Spawns NUM_FIELD_WORKERS_PER_DOC field workers
4. Creates document-specific queue: fields:{project_id}:{document_id}
5. Enqueues all fields to document-specific queue
6. Monitors field completion
```

### 3. Field Worker Extracts Field
```
1. Field worker picks up field from fields:{project_id}:{document_id}
2. Performs field extraction using LLM
3. Saves result to database
4. Updates document status when all fields complete
5. Updates project status when all documents complete
```

## Resource Calculation

### Example 1: Small Project
**Configuration:**
- 1 project with 5 documents
- `NUM_DOC_WORKERS_PER_PROJECT=2`
- `NUM_FIELD_WORKERS_PER_DOC=5`

**Resources:**
- 1 project worker
- 2 document workers (process 5 documents in parallel)
- 10 field workers (5 per document, 2 documents processing simultaneously)

**Total:** 13 workers

### Example 2: Multiple Projects
**Configuration:**
- 2 projects, each with 10 documents
- `NUM_PROJECT_WORKERS=2`
- `NUM_DOC_WORKERS_PER_PROJECT=3`
- `NUM_FIELD_WORKERS_PER_DOC=5`

**Resources per project:**
- 1 project worker
- 3 document workers
- 15 field workers (5 per document, 3 documents processing simultaneously)

**Total:** 2 + (2 × 3) + (2 × 15) = **38 workers**

### Example 3: Your Requirement
**Configuration:**
- 1 project worker → 2 doc workers → 5 field workers per doc
- `NUM_PROJECT_WORKERS=1`
- `NUM_DOC_WORKERS_PER_PROJECT=2`
- `NUM_FIELD_WORKERS_PER_DOC=5`

**For 1 project:**
- 1 project worker
- 2 document workers
- 10 field workers (5 per document × 2 documents)

**For 2 projects:**
- 2 project workers
- 4 document workers (2 per project)
- 20 field workers (5 per document × 2 documents per project)

## Monitoring

### Check Active Workers
```bash
# View all RQ workers
docker-compose exec workers rq info --url redis://redis:6379/0

# Check specific queue
docker-compose exec workers rq info --url redis://redis:6379/0 documents:project-123
```

### View Worker Logs
```bash
# All worker logs
docker-compose logs -f workers

# Filter for specific worker type
docker-compose logs -f workers | grep "Project Worker"
docker-compose logs -f workers | grep "Doc Worker"
docker-compose logs -f workers | grep "Field Worker"
```

### Check Queue Status
```python
import redis
from rq import Queue

r = redis.Redis(host='localhost', port=6379)

# List all queues
for key in r.keys('rq:queue:*'):
    queue_name = key.decode('utf-8').replace('rq:queue:', '')
    queue = Queue(queue_name, connection=r)
    print(f"{queue_name}: {len(queue)} jobs")
```

## Performance Tuning

### Memory Considerations
Each worker consumes approximately:
- **Project worker:** 100-200 MB
- **Document worker:** 300-500 MB (due to chunking/embeddings)
- **Field worker:** 200-400 MB (due to LLM calls)

**Example calculation for 2 projects:**
- 2 project workers: ~400 MB
- 4 document workers: ~1.6 GB
- 20 field workers: ~6 GB
- **Total:** ~8 GB RAM

### Optimal Configuration

#### For Small Projects (< 5 documents)
```bash
NUM_DOC_WORKERS_PER_PROJECT=1
NUM_FIELD_WORKERS_PER_DOC=3
```

#### For Medium Projects (5-20 documents)
```bash
NUM_DOC_WORKERS_PER_PROJECT=2
NUM_FIELD_WORKERS_PER_DOC=5
```

#### For Large Projects (> 20 documents)
```bash
NUM_DOC_WORKERS_PER_PROJECT=3
NUM_FIELD_WORKERS_PER_DOC=5
```

### Rate Limiting Considerations
If you're hitting LLM API rate limits:
- **Reduce field workers:** Lower `NUM_FIELD_WORKERS_PER_DOC`
- **Increase retry backoff:** Adjust `MAX_RETRIES` in `.env`
- **Use LiteLLM load balancing:** Configure multiple API keys

## Troubleshooting

### Issue: Workers not spawning
**Symptoms:** Only project workers visible, no document/field workers

**Solution:**
1. Check `USE_HIERARCHICAL_WORKERS=true` in `.env`
2. Verify worker logs: `docker-compose logs workers`
3. Ensure RQ can spawn subprocesses

### Issue: Queue not found
**Symptoms:** Errors like "Queue documents:project-123 not found"

**Solution:**
1. Verify project ID is correct
2. Check Redis connection: `docker-compose exec redis redis-cli ping`
3. Ensure project worker has created the queue

### Issue: High memory usage
**Symptoms:** System running out of memory

**Solution:**
1. Reduce worker counts:
   ```bash
   NUM_DOC_WORKERS_PER_PROJECT=1
   NUM_FIELD_WORKERS_PER_DOC=3
   ```
2. Process fewer projects concurrently
3. Increase system memory or use swap

### Issue: Workers not terminating
**Symptoms:** Zombie worker processes after project completion

**Solution:**
1. Check worker manager cleanup logic
2. Manually kill workers: `docker-compose restart workers`
3. Review logs for exceptions during cleanup

## Migration from Traditional Mode

### Step 1: Test with Single Project
```bash
# In .env
USE_HIERARCHICAL_WORKERS=true
NUM_PROJECT_WORKERS=1
NUM_DOC_WORKERS_PER_PROJECT=2
NUM_FIELD_WORKERS_PER_DOC=5
```

### Step 2: Monitor Performance
```bash
# Watch worker spawning
docker-compose logs -f workers | grep "Spawning"

# Check memory usage
docker stats siso-pipeline-workers
```

### Step 3: Adjust Configuration
Based on your workload:
- **CPU-bound:** Increase field workers
- **Memory-bound:** Decrease worker counts
- **API rate-limited:** Decrease field workers

### Step 4: Scale for Production
```bash
# For production with multiple concurrent projects
NUM_PROJECT_WORKERS=3
NUM_DOC_WORKERS_PER_PROJECT=2
NUM_FIELD_WORKERS_PER_DOC=5
```

## Comparison: Traditional vs Hierarchical

| Aspect | Traditional Parallel | Hierarchical |
|--------|---------------------|--------------|
| **Resource Allocation** | Fixed pools, shared | Dynamic, isolated |
| **Queue Structure** | 3 global queues | Project/document-specific queues |
| **Worker Spawning** | At startup | On-demand |
| **Isolation** | No isolation | Full isolation |
| **Scalability** | Limited by fixed pools | Scales per project |
| **Memory Usage** | Lower (fixed) | Higher (dynamic) |
| **Best For** | Single project, predictable load | Multiple projects, variable load |

## Best Practices

1. **Start with conservative settings:**
   ```bash
   NUM_DOC_WORKERS_PER_PROJECT=1
   NUM_FIELD_WORKERS_PER_DOC=3
   ```

2. **Monitor and adjust:** Use logs and metrics to tune configuration

3. **Consider your API limits:** Don't spawn more field workers than your API can handle

4. **Plan for memory:** Calculate expected memory usage before scaling

5. **Use traditional mode for single projects:** If you only process one project at a time, traditional mode is more efficient

## Files Modified

- **`app/api/worker_parallel.py`**: Added hierarchical queue support and worker spawning
- **`app/utils/worker_launcher_parallel.py`**: Added hierarchical mode detection and configuration
- **`app/utils/worker_manager.py`**: New utility for spawning and managing child workers
- **`.env.example`**: Added hierarchical configuration options
- **`docker-compose.yml`**: Added hierarchical environment variables

## Testing

### Test Hierarchical Mode
```bash
# Set environment
export USE_HIERARCHICAL_WORKERS=true
export NUM_DOC_WORKERS_PER_PROJECT=2
export NUM_FIELD_WORKERS_PER_DOC=5

# Submit a test project
curl -X POST http://localhost:8001/api/project/submit \
  -F "project_name=test-hierarchical" \
  -F "field_names=[\"field1\",\"field2\"]" \
  -F "template_name=spa_fields" \
  -F "files=@document.pdf"

# Monitor worker spawning
docker-compose logs -f workers | grep "Spawning"
```

### Verify Worker Isolation
```bash
# Check that workers only process their assigned tasks
docker-compose logs workers | grep "Worker.*Using hierarchical"
```

## Summary

The hierarchical worker architecture provides:
- ✅ **Dedicated resources per project**
- ✅ **Isolated worker pools**
- ✅ **Predictable scaling** (1 project → 2 doc workers → 5 field workers each)
- ✅ **No cross-project interference**
- ✅ **Dynamic resource allocation**

Enable it with `USE_HIERARCHICAL_WORKERS=true` and configure worker counts per hierarchy level.
