import os
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from app.core.weaviate_client import WeaviateClient
from app.core.embedding import EmbeddingService
from app.core.llm import LLMService
from app.core.validate_agents import ValidationSystem
from app.utils.file_handler import DocumentLoader
from app.api.project import project_router
from app.api.status import status_router
from app.logging_config import logger
import redis as rqredis
import spacy
from app.db.database import init_db

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
sync_redis = rqredis.from_url(REDIS_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Initializing siso-pipeline application services")
        
        # Initialize database tables
        logger.info("Initializing database...")
        init_db()
        
        document_loader = DocumentLoader()
        weaviate_client = WeaviateClient(
            url=os.getenv("WEAVIATE_URL", "http://localhost:8080"),
            document_loader=document_loader
        )
        embedding_service = EmbeddingService(
            api_key=os.getenv("LITELLM_MASTER_KEY"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
            min_chunk_size=int(os.getenv("MIN_CHUNK_SIZE", "100")),
            llm_model=os.getenv("LLM_MODEL_GPT_5", "gpt-5"),
            chunk_size=int(os.getenv("CHUNK_SIZE", 1000)),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", 200))
        )
        llm_service = LLMService(
            model=os.getenv("LLM_MODEL_GPT_5", "gpt-5"),
            fallback_model=os.getenv("LLM_MODEL_GPT_5_MINI", "gpt-4.1-mini"),
            page_model=os.getenv("LLM_MODEL_GPT_4_MINI", "gpt-4.1-mini"),
            reasoning_effort=os.getenv("REASONING_EFFORT", "low"),
            api_key=os.getenv("LITELLM_MASTER_KEY")
        )
        validation_system = ValidationSystem(
            llm_model=os.getenv("LLM_MODEL_GPT_5", "gpt-5"),
            reasoning_effort=os.getenv("REASONING_EFFORT", "low"),
            max_iterations=int(os.getenv("VALIDATION_MAX_ITERATIONS", 3)),
            max_completion_tokens=int(os.getenv("MAX_RESPONSE_TOKENS", 1000))
        )
        
        # Store in app.state
        app.state.weaviate_client = weaviate_client
        app.state.embedding_service = embedding_service
        app.state.llm_service = llm_service
        app.state.document_loader = document_loader
        app.state.validation_system = validation_system
        
        logger.info("Services initialized successfully")
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {str(e)}")
        raise
    finally:
        if hasattr(app.state, 'weaviate_client'):
            logger.info("Closing Weaviate client")
            app.state.weaviate_client.close()


app = FastAPI(
    title="SISO Pipeline API",
    description="API for document processing pipeline with field extraction",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with prefixes
app.include_router(project_router, prefix="/project", tags=["projects"])
app.include_router(status_router, tags=["status"])


@app.get("/health")
def health_check(request: Request):
    health = {}

    # Check Redis
    redis_client = None
    try:
        redis_client = rqredis.from_url(REDIS_URL, socket_connect_timeout=2)
        if redis_client.ping():
            health["redis"] = "healthy"
        else:
            health["redis"] = "unhealthy"
    except Exception as e:
        health["redis"] = f"unhealthy: {str(e)}"
    finally:
        if redis_client:
            redis_client.close()

    # Check Weaviate
    try:
        if hasattr(request.app.state, 'weaviate_client'):
            if request.app.state.weaviate_client.client.is_ready():
                health["weaviate"] = "healthy"
            else:
                health["weaviate"] = "unhealthy"
        else:
            health["weaviate"] = "not initialized"
    except Exception as e:
        health["weaviate"] = f"unhealthy: {str(e)}"

    # Check spaCy model
    try:
        spacy.load("en_core_web_sm")
        health["spacy"] = "healthy"
    except OSError:
        health["spacy"] = "unhealthy: model not found"
    except Exception as e:
        health["spacy"] = f"unhealthy: {str(e)}"

    all_healthy = all(status == "healthy" for status in health.values())
    if not all_healthy:
        raise HTTPException(
            status_code=503, 
            detail={"status": "unhealthy", "components": health}
        )
    
    return {"status": "healthy", "components": health}


@app.get("/")
def root():
    return {
        "service": "SISO Pipeline API",
        "version": "1.0.0",
        "status": "running"
    }
