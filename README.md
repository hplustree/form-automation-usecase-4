# SISO Document Processing Pipeline

A robust FastAPI-based document processing pipeline for intelligent field extraction using AI, vector embeddings, and parallel processing. Supports PDF, DOCX, PPTX, and TXT files with PostgreSQL persistence, Redis queuing, and Weaviate vector search.

## Features

- **Multi-Document Upload:** Process multiple documents (PDF, DOCX, PPTX, TXT) simultaneously with parallel processing
- **AI-Powered Field Extraction:** Extract custom fields using LLMs with configurable prompts and models
- **Parallel Processing Architecture:** Three-tier queue system for projects, documents, and fields
- **Vector Search:** Semantic search using Weaviate for accurate context retrieval
- **Database Persistence:** PostgreSQL with Alembic migrations for data persistence and history
- **Real-time Status Tracking:** Monitor processing progress with detailed status updates
- **Template Support:** Pre-configured field templates for SPA and CIM documents
- **Confidence Scoring:** Automated validation and confidence scoring for extracted fields
- **Modern UI:** React-based frontend with real-time updates and progress tracking
- **Export Capabilities:** Download results as JSON with source page references

## Requirements

- Docker & Docker Compose
- OpenAI API key(s)
- 8GB+ RAM recommended
- Python 3.8+ (for local development)

## Quick Start (Docker Compose)

Run the entire application stack (API, Frontend, PostgreSQL, Weaviate, Redis, LiteLLM) with Docker Compose:

```bash
# 1. Clone the repository
git clone <repository-url>
cd siso-pipeline

# 2. Prepare environment variables
cp .env.example .env
# Edit .env and add your OpenAI API keys and other settings

# 3. Start all services
docker compose up --build

# The services will be available at:
# Frontend:              http://localhost:5173
# API/Swagger Docs:      http://localhost:8001/docs
# LiteLLM Proxy:         http://localhost:4000
# PostgreSQL:            localhost:5433
# Redis:                 localhost:6380
# Weaviate:              http://localhost:8085
```

**Tip:**
- Stop the stack with `docker compose down`
- Data is persisted in Docker volumes for PostgreSQL, Weaviate, and Redis
- The API automatically connects to all services using Docker networking

## Environment Variables

Key environment variables (see `.env.example` for full template):

```env
# Required
LITELLM_MASTER_KEY=your_master_key_here
OPENAI_API_KEY=your_openai_api_key
OPENAI_API_KEY_2=your_second_api_key  # Optional for load balancing
OPENAI_API_KEY_3=your_third_api_key   # Optional
OPENAI_API_KEY_4=your_fourth_api_key  # Optional

# Database
DATABASE_URL=postgresql://postgres:1234@postgres:5432/siso_pipeline

# Worker Configuration
NUM_DOC_WORKERS=3        # Document processing workers
NUM_FIELD_WORKERS=5      # Field extraction workers  
NUM_PROJECT_WORKERS=1    # Project coordination workers

# Processing Configuration
MAX_CONCURRENT_FIELDS=5  # Fields processed in parallel per document
CHUNK_SIZE=1000         # Document chunk size for embeddings
MAX_RETRIES=3           # Retry attempts for failed extractions
```

## API Endpoints

All endpoints are under `/api`. See `/docs` for interactive Swagger documentation.

### Project Management
- `POST /api/project/submit` — Submit new project with documents and field configuration
- `GET /api/project/{id}` — Get project status and metadata
- `GET /api/project/{id}/results` — Get all extraction results for a project
- `GET /api/project/{id}/document/{doc_id}/results` — Get results for specific document
- `GET /api/projects` — List all projects with pagination
- `DELETE /api/project/{id}` — Delete project and all associated data

### Status & Monitoring
- `GET /api/status/track/{tracking_id}` — Track async processing status
- `GET /api/queue/status` — Get queue statistics and worker status
- `GET /health` — Health check endpoint

### Templates
- `GET /api/templates` — List available field templates (SPA, CIM)
- `GET /api/templates/{template_name}` — Get specific template configuration

## Usage & Documentation

- **Interactive API docs:** [http://localhost:8001/docs](http://localhost:8001/docs)
- **ReDoc API docs:** [http://localhost:8001/redoc](http://localhost:8001/redoc)
- **Frontend UI:** [http://localhost:5173](http://localhost:5173)
- **Database docs:** See `DATABASE_INTEGRATION.md`
- **Parallel processing:** See `PARALLEL_PROCESSING.md`
- **Deployment guide:** See `DEPLOYMENT_GUIDE.md`

## Project Structure

```
siso-pipeline/
├── app/
│   ├── api/              # API endpoints (project, status, worker)
│   ├── core/             # Core logic (weaviate, embeddings, LLM, validation)
│   ├── db/               # Database models and operations
│   ├── utils/            # Utilities (file handler, worker launcher, logger)
│   └── main.py           # FastAPI application entry point
├── frontend/             # React frontend application
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── services/     # API service layer
│   │   └── App.jsx       # Main application component
│   └── package.json      # Frontend dependencies
├── templates/            # Field extraction templates
│   ├── spa_fields.json   # SPA document template
│   └── cim_fields.json   # CIM document template
├── alembic/              # Database migrations
├── postgres-init/        # PostgreSQL initialization scripts
├── docker-compose.yml    # Docker services configuration
└── requirements.txt      # Python dependencies
```

## Architecture

### Processing Pipeline

```
┌──────────────┐
│   Frontend   │
└──────┬───────┘
       │ POST /api/project/submit
       ▼
┌──────────────────────────────┐
│  FastAPI (Port 8001)         │
│  - Project submission        │
│  - Status tracking           │
│  - Results retrieval         │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  PostgreSQL Database         │
│  - Projects, Documents       │
│  - Field Results             │
│  - Queue Management          │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Redis Queue System          │
│  - Projects Queue            │
│  - Documents Queue           │
│  - Fields Queue              │
└──────┬───────────────────────┘
       │
       ├─────────┬──────────────┐
       ▼         ▼              ▼
   Doc Worker  Field Worker  Project Worker
   (3 workers) (5 workers)   (1 worker)
       │         │              │
       ▼         ▼              ▼
┌──────────────────────────────┐
│  Weaviate Vector DB          │
│  - Document Chunks           │
│  - Semantic Search           │
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  LiteLLM Proxy (Port 4000)   │
│  - Load Balancing            │
│  - Multiple API Keys         │
│  - Model Management          │
└──────────────────────────────┘
```

## Supported File Formats

- PDF (`.pdf`) - Including scanned documents with OCR
- Word (`.docx`, `.doc`)
- PowerPoint (`.pptx`, `.ppt`)
- Text (`.txt`)

## Testing

### Method 1: Frontend UI
Navigate to http://localhost:5173 and use the intuitive interface to:
- Upload documents
- Configure fields or use templates
- Monitor processing progress
- Download results

### Method 2: Swagger UI
Use the interactive documentation at http://localhost:8001/docs

## Monitoring & Debugging

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker logs siso-pipeline-api -f
docker logs siso-pipeline-workers -f

# Check queue status
curl http://localhost:8001/api/queue/status

# Database queries
docker exec -it siso-pipeline-postgres psql -U postgres -d siso_pipeline

# Redis monitoring
docker exec -it siso-pipeline-redis redis-cli
> LLEN rq:queue:projects
> LLEN rq:queue:documents
> LLEN rq:queue:fields
```

## Common Issues & Solutions

### Port conflicts
```bash
# Change ports in docker-compose.yml if needed
ports:
  - "8002:8001"  # Use different host port
```

### Worker not processing
```bash
# Check worker logs
docker logs siso-pipeline-workers

# Restart workers
docker-compose restart workers
```

### Database connection issues
```bash
# Run migrations manually
docker exec siso-pipeline-api alembic upgrade head

# Initialize database
docker exec siso-pipeline-api python init_db.py

# Check database status
docker exec siso-pipeline-postgres pg_isready
```

### LiteLLM connection issues
```bash
# Check LiteLLM logs
docker logs siso-pipeline-litellm

# Verify API key
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" http://localhost:4000/health
```

## Advanced Features

- **PostgreSQL Integration:** Full CRUD operations with migration history
- **Alembic Migrations:** Version-controlled database schema
- **Template System:** Pre-configured field extraction templates for SPA and CIM documents
- **Confidence Scoring:** Automatic validation of extracted data with confidence levels
- **Source Tracking:** Page-level source references for all extractions
- **Error Recovery:** Automatic retry with exponential backoff
- **Load Balancing:** Multiple OpenAI API keys for rate limit management via LiteLLM
- **Image Detection:** Automatic detection and processing of images in documents
- **Parallel Queue System:** Separate queues for projects, documents, and fields
- **Real-time Updates:** WebSocket support for live status updates (coming soon)

## Development


### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request
