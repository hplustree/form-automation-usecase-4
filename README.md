# SISO Pipeline - Document Field Extraction System

A robust document processing pipeline that extracts structured field values from multiple documents using AI-powered analysis. Built with FastAPI, Weaviate, Redis, and LiteLLM.

## Features

- **Multi-Document Processing**: Upload multiple documents (PDF, DOCX, PPTX, TXT) per project
- **Field Extraction**: Define custom fields with prompts to extract specific information
- **Parallel Processing**: Process multiple fields concurrently (5 by default)
- **Sequential Document Processing**: Documents processed one at a time to ensure quality
- **Vector Search**: Hybrid search using Weaviate for accurate context retrieval
- **Validation & Confidence**: Automated answer validation with confidence scoring
- **Worker Queue**: 2 RQ workers for parallel project processing
- **Page References**: Track source pages for each extracted field
- **Retry Logic**: Automatic retry on failures with exponential backoff

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│         FastAPI API (Port 8001)     │
│  - Project Submission               │
│  - Status Tracking                  │
│  - Results Retrieval                │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│         Redis Queue                 │
│  - Project Queue (FIFO)             │
│  - Status Storage                   │
│  - Results Storage                  │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│      RQ Workers (2 workers)         │
│  - Worker 1: Process Project 1      │
│  - Worker 2: Process Project 2      │
│                                     │
│  Per Project:                       │
│  1. Process Doc 1 → Extract Fields  │
│  2. Process Doc 2 → Extract Fields  │
│  3. Process Doc N → Extract Fields  │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│         Weaviate (Vector DB)        │
│  - Store document chunks            │
│  - Hybrid search (vector + BM25)    │
│  - Page-level tracking              │
└─────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- LiteLLM server running (for LLM access)
- OpenAI API key or compatible LLM endpoint

### Installation

1. **Clone and navigate to project**
```bash
cd /home/akash/Documents/siso/siso-pipeline
```

2. **Create .env file**
```bash
cp .env.example .env
# Edit .env and add your configuration
nano .env
```

Required environment variables:
```env
LITELLM_MASTER_KEY=your_litellm_master_key
LLM_BASE_URL=http://localhost:4000
```

3. **Start all services**
```bash
docker-compose up --build
```

Services will be available at:
- **API**: http://localhost:8001
- **API Docs**: http://localhost:8001/docs
- **Redis**: localhost:6380
- **Weaviate**: http://localhost:8081

## Usage

### 1. Submit a Project

**Endpoint**: `POST /api/project/submit`

**Form Data**:
- `project_name`: Name of your project
- `fields_config`: JSON string with field configurations
- `files`: Multiple document files

**Example using cURL**:
```bash
curl -X POST "http://localhost:8001/api/project/submit" \
  -F "project_name=Germany Analysis" \
  -F 'fields_config=[
    {
      "field_name": "company_name",
      "prompt": "Extract the company name from the document",
      "model": "gpt-5",
      "mode": "low",
      "type": "verbatim"
    },
    {
      "field_name": "contract_date",
      "prompt": "Find the contract execution date",
      "model": "gpt-4.1-mini",
      "mode": "medium",
      "type": "verbatim"
    }
  ]' \
  -F "files=@contract1.pdf" \
  -F "files=@contract2.pdf"
```

**Response**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Project submitted successfully with 2 documents"
}
```

### 2. Check Project Status

**Endpoint**: `GET /api/project/{project_id}`

```bash
curl http://localhost:8001/api/project/550e8400-e29b-41d4-a716-446655440000
```

**Response**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_name": "Germany Analysis",
  "status": "processing",
  "total_documents": 2,
  "processed_documents": 1,
  "failed_documents": 0,
  "created_at": "2025-10-09T15:00:00",
  "updated_at": "2025-10-09T15:05:00",
  "documents": [
    {
      "doc_id": "550e8400-e29b-41d4-a716-446655440000_doc_1",
      "doc_name": "contract1.pdf",
      "status": "completed"
    },
    {
      "doc_id": "550e8400-e29b-41d4-a716-446655440000_doc_2",
      "doc_name": "contract2.pdf",
      "status": "processing"
    }
  ]
}
```

### 3. Get Project Results

**Endpoint**: `GET /api/project/{project_id}/results`

```bash
curl http://localhost:8001/api/project/550e8400-e29b-41d4-a716-446655440000/results
```

**Response**:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "project_name": "Germany Analysis",
  "status": "completed",
  "results": {
    "550e8400-e29b-41d4-a716-446655440000_doc_1": {
      "company_name": {
        "field_name": "company_name",
        "value": "Acme Corporation GmbH",
        "confidence": 0.95,
        "source_pages": [1, 3],
        "chunks": [
          {
            "page": 1,
            "text": "...Acme Corporation GmbH...",
            "score": 0.92
          }
        ],
        "status": "completed"
      },
      "contract_date": {
        "field_name": "contract_date",
        "value": "January 15, 2025",
        "confidence": 0.88,
        "source_pages": [2],
        "chunks": [...],
        "status": "completed"
      }
    },
    "550e8400-e29b-41d4-a716-446655440000_doc_2": {
      ...
    }
  }
}
```

### 4. Get Document-Specific Results

**Endpoint**: `GET /api/project/{project_id}/document/{doc_id}/results`

```bash
curl http://localhost:8001/api/project/550e8400-e29b-41d4-a716-446655440000/document/550e8400-e29b-41d4-a716-446655440000_doc_1/results
```

### 5. List All Projects

**Endpoint**: `GET /api/projects`

```bash
curl http://localhost:8001/api/projects
```

### 6. Delete a Project

**Endpoint**: `DELETE /api/project/{project_id}`

```bash
curl -X DELETE http://localhost:8001/api/project/550e8400-e29b-41d4-a716-446655440000
```

## Field Configuration

Each field in `fields_config` supports:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `field_name` | string | Yes | Unique identifier for the field |
| `prompt` | string | Yes | Instruction for extracting the field value |
| `model` | string | No | LLM model to use (default: "gpt-5") |
| `mode` | string | No | Reasoning effort: "low", "medium", "high" (default: "low") |
| `type` | string | No | Prompt type: "verbatim" or "summarize" (default: "verbatim") |

**Example Fields Config**:
```json
[
  {
    "field_name": "company_name",
    "prompt": "Extract the full legal name of the company",
    "model": "gpt-5",
    "mode": "low",
    "type": "verbatim"
  },
  {
    "field_name": "key_terms",
    "prompt": "Summarize the key terms and conditions",
    "model": "gpt-5",
    "mode": "medium",
    "type": "summarize"
  },
  {
    "field_name": "payment_terms",
    "prompt": "Extract payment terms including amounts and due dates",
    "model": "gpt-4.1-mini",
    "mode": "low",
    "type": "verbatim"
  }
]
```

## Supported File Formats

- PDF (`.pdf`)
- Word (`.docx`, `.doc`)
- PowerPoint (`.pptx`, `.ppt`)
- Text (`.txt`)

## Project Structure

```
siso-pipeline/
├── app/
│   ├── api/
│   │   ├── project.py       # Project submission & management
│   │   ├── status.py        # Status tracking endpoints
│   │   └── worker.py        # Background worker logic
│   ├── core/
│   │   ├── weaviate_client.py   # Vector DB operations
│   │   ├── embedding.py         # Document chunking & embeddings
│   │   ├── llm.py              # LLM service
│   │   └── validate_agents.py  # Validation & confidence scoring
│   ├── utils/
│   │   ├── file_handler.py     # Document loading
│   │   └── locks.py            # LibreOffice locking
│   ├── main.py              # FastAPI application
│   └── logging_config.py    # Logging setup
├── temp_files/              # Temporary file storage
├── temp_image_summaries/    # Image processing temp files
├── requirements.txt         # Python dependencies
├── Dockerfile              # Docker image definition
├── docker-compose.yml      # Multi-container setup
├── .env.example           # Environment variables template
└── README.md              # This file
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LITELLM_MASTER_KEY` | - | LiteLLM API key (required) |
| `LLM_BASE_URL` | http://localhost:4000 | LiteLLM server URL |
| `LLM_MODEL_GPT_5` | gpt-5 | Primary LLM model |
| `LLM_MODEL_GPT_5_MINI` | gpt-4.1-mini | Fallback LLM model |
| `EMBEDDING_MODEL` | text-embedding-3-large | Embedding model |
| `WEAVIATE_URL` | http://weaviate:8080 | Weaviate server URL |
| `REDIS_URL` | redis://redis:6379/0 | Redis connection URL |
| `MAX_CONCURRENT_FIELDS` | 5 | Concurrent field processing |
| `MAX_RETRIES` | 3 | Retry attempts on failure |
| `CHUNK_SIZE` | 1000 | Document chunk size |
| `CHUNK_OVERLAP` | 200 | Chunk overlap size |
| `REDIS_TTL_SECONDS` | 604800 | Redis data TTL (7 days) |

## Monitoring

### Check Worker Status

```bash
# View worker logs
docker logs siso-pipeline-worker-1 -f
docker logs siso-pipeline-worker-2 -f

# View API logs
docker logs siso-pipeline-api -f
```

### Redis Queue Inspection

```bash
# Connect to Redis
docker exec -it siso-pipeline-redis redis-cli

# Check queue length
LLEN rq:queue:projects

# View project data
GET project:{project_id}

# View results
GET project:{project_id}:results
```

## Troubleshooting

### Worker Not Processing

1. Check worker logs: `docker logs siso-pipeline-worker-1`
2. Verify Redis connection: `docker exec -it siso-pipeline-redis redis-cli ping`
3. Check queue: `docker exec -it siso-pipeline-redis redis-cli LLEN rq:queue:projects`

### Low Confidence Scores

- Increase `CHUNK_SIZE` for more context
- Use higher `mode` (medium/high) for complex extractions
- Improve prompt specificity
- Check if relevant content exists in documents

### Rate Limiting

- Adjust `MAX_CONCURRENT_FIELDS` to lower value
- Increase retry delays in worker
- Check LiteLLM server rate limits

### Memory Issues

- Reduce `MAX_CONCURRENT_FIELDS`
- Process fewer documents per project
- Increase Docker memory allocation

## Development

### Run Locally (without Docker)

```bash
# Install dependencies
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm

# Start Redis (separate terminal)
redis-server

# Start Weaviate (separate terminal)
# Use docker or local installation

# Start API
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Start workers (separate terminals)
rq worker projects --url redis://localhost:6379/0
rq worker projects --url redis://localhost:6379/0
```

### Run Tests

```bash
# TODO: Add test suite
pytest tests/
```

## API Documentation

Interactive API documentation available at:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Performance

- **Throughput**: 2 projects in parallel (2 workers)
- **Field Processing**: 5 fields concurrently per document
- **Document Processing**: Sequential (ensures quality)
- **Typical Processing Time**: 
  - Small doc (10 pages): ~2-3 minutes for 5 fields
  - Large doc (100 pages): ~5-10 minutes for 5 fields

## License

Proprietary - SISO

## Support

For issues and questions, contact the development team.
