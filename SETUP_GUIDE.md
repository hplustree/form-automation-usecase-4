# SISO Pipeline - Complete Setup Guide

## Project Successfully Created! ✓

All files have been generated for the **siso-pipeline** project.

## What Was Built

### Core Features
- ✅ Multi-document processing pipeline
- ✅ Field extraction with custom prompts
- ✅ Sequential document processing with concurrent field extraction (5 fields at a time)
- ✅ 2 RQ workers for parallel project processing
- ✅ Vector search with Weaviate
- ✅ Validation & confidence scoring
- ✅ Page reference tracking
- ✅ Retry logic with exponential backoff

### Architecture
```
Client → FastAPI (8001) → Redis Queue → Workers (2) → Weaviate
                              ↓
                         Project Queue (FIFO)
                              ↓
                    Worker picks project
                              ↓
                    Process docs sequentially
                              ↓
                    Extract fields concurrently (5 at a time)
```

## Files Created

### Application Files
- ✅ `app/main.py` - FastAPI application
- ✅ `app/logging_config.py` - Logging configuration
- ✅ `app/api/project.py` - Project submission & management
- ✅ `app/api/status.py` - Status tracking endpoints
- ✅ `app/api/worker.py` - Background worker implementation
- ✅ `app/core/weaviate_client.py` - Vector DB client (adapted for pipeline)
- ✅ `app/core/embedding.py` - Document chunking & embeddings (copied from siso-daex)
- ✅ `app/core/llm.py` - LLM service (copied from siso-daex)
- ✅ `app/core/validate_agents.py` - Validation system (copied from siso-daex)
- ✅ `app/utils/file_handler.py` - Document loader
- ✅ `app/utils/locks.py` - LibreOffice locking

### Configuration Files
- ✅ `requirements.txt` - Python dependencies
- ✅ `Dockerfile` - Docker image
- ✅ `docker-compose.yml` - Multi-container setup (API + 2 workers + Redis + Weaviate)
- ✅ `.env.example` - Environment variables template
- ✅ `.gitignore` - Git ignore rules

### Documentation & Scripts
- ✅ `README.md` - Complete documentation
- ✅ `SETUP_GUIDE.md` - This file
- ✅ `start.sh` - Quick start script
- ✅ `verify_setup.sh` - Setup verification
- ✅ `test_api.py` - API testing script

## Quick Start (3 Steps)

### Step 1: Configure Environment
```bash
cd /home/akash/Documents/siso/siso-pipeline
cp .env.example .env
nano .env  # Add your LITELLM_MASTER_KEY
```

### Step 2: Verify Setup
```bash
./verify_setup.sh
```

### Step 3: Start Services
```bash
./start.sh
```

Access the API at: **http://localhost:8001/docs**

## How to Use

### 1. Submit a Project (cURL)
```bash
curl -X POST "http://localhost:8001/api/project/submit" \
  -F "project_name=My Project" \
  -F 'fields_config=[
    {
      "field_name": "company_name",
      "prompt": "Extract the company name",
      "model": "gpt-5",
      "mode": "low",
      "type": "verbatim"
    }
  ]' \
  -F "files=@document1.pdf" \
  -F "files=@document2.pdf"
```

### 2. Check Status
```bash
curl http://localhost:8001/api/project/{project_id}
```

### 3. Get Results
```bash
curl http://localhost:8001/api/project/{project_id}/results
```

## Key Differences from siso-daex

| Feature | siso-daex | siso-pipeline |
|---------|-----------|---------------|
| **Input** | S3 paths | Direct file upload |
| **Processing** | All docs → All prompts | Per doc → All fields |
| **Results** | Aggregated across docs | Per document |
| **Storage** | Collection per job | One collection (DataPipeline) |
| **Workers** | General purpose | Project-specific queue |
| **Port** | 8000 | 8001 |

## Project Structure
```
siso-pipeline/
├── app/
│   ├── api/          # API endpoints
│   ├── core/         # Core services
│   ├── utils/        # Utilities
│   └── main.py       # FastAPI app
├── temp_files/       # Temporary storage
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Environment Variables (Required)

**Minimum Required:**
```env
LITELLM_MASTER_KEY=your_key_here
LLM_BASE_URL=http://localhost:4000
```

**All Variables:** See `.env.example`

## Monitoring

### View Logs
```bash
# API logs
docker logs siso-pipeline-api -f

# Worker logs
docker logs siso-pipeline-worker-1 -f
docker logs siso-pipeline-worker-2 -f

# All logs
docker-compose logs -f
```

### Check Redis Queue
```bash
docker exec -it siso-pipeline-redis redis-cli
> LLEN rq:queue:projects
> KEYS project:*
```

## Troubleshooting

### Services won't start
```bash
# Check Docker
docker ps

# Check logs
docker-compose logs

# Restart
docker-compose down
docker-compose up --build
```

### Worker not processing
```bash
# Check worker logs
docker logs siso-pipeline-worker-1

# Check queue
docker exec -it siso-pipeline-redis redis-cli LLEN rq:queue:projects

# Restart workers
docker-compose restart worker1 worker2
```

### Port conflicts
If port 8001 is in use, edit `docker-compose.yml`:
```yaml
api:
  ports:
    - "8002:8001"  # Change 8001 to 8002
```

## Next Steps

1. ✅ **Verify setup**: Run `./verify_setup.sh`
2. ✅ **Configure .env**: Add your LiteLLM credentials
3. ✅ **Start services**: Run `./start.sh`
4. ✅ **Test API**: Visit http://localhost:8001/docs
5. ✅ **Submit test project**: Use the Swagger UI or `test_api.py`

## Testing

### Using Swagger UI
1. Go to http://localhost:8001/docs
2. Click on `POST /api/project/submit`
3. Click "Try it out"
4. Fill in the form
5. Upload files
6. Execute

### Using Python Script
```bash
# Edit test_api.py with your file paths
nano test_api.py

# Run test
python test_api.py
```

## Production Considerations

- [ ] Add authentication/authorization
- [ ] Configure rate limiting
- [ ] Set up monitoring (Prometheus/Grafana)
- [ ] Configure backup for Redis/Weaviate
- [ ] Add SSL/TLS certificates
- [ ] Scale workers based on load
- [ ] Add comprehensive test suite
- [ ] Set up CI/CD pipeline

## Support

For issues or questions:
1. Check logs: `docker-compose logs`
2. Review README.md
3. Contact development team

---

**Project Status**: ✅ Ready to use!

**Created**: 2025-10-09
**Version**: 1.0.0
