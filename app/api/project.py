import os
import json
import hashlib
import shutil
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Path as FastAPIPath, Query, Body
from pydantic import BaseModel, Field, field_validator, ConfigDict
import redis as rqredis
from rq import Queue, get_current_job
from datetime import datetime
import logging
from fastapi import status
from sqlalchemy.orm import Session
from sqlalchemy import text, and_
from app.logging_config import logger
from app.db.database import get_db
from app.db.operations import ProjectOperations, DocumentOperations, FieldResultOperations, QueueOperations, DocumentQueueOperations, FieldQueueOperations
from app.api.worker_parallel import process_document
from app.db.models import Project, Document, DocumentQueue, FieldQueue, FieldResult

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "projects")
REDIS_TTL_SECONDS = int(os.getenv("REDIS_TTL_SECONDS", 86400 * 7))  # 7 days for projects

sync_redis = rqredis.from_url(REDIS_URL)
project_queue = Queue(QUEUE_NAME, connection=sync_redis)
document_queue = Queue("documents", connection=sync_redis)
field_queue = Queue("fields", connection=sync_redis)

# Create the router
project_router = APIRouter()

@project_router.get("/get-templates", response_model=List[Dict[str, Any]])
async def get_templates() -> List[Dict[str, Any]]:
    """
    List all JSON template files in the templates directory and return their code and name.
    Returns a list of objects, each with 'code' and 'name'.
    """
    templates_dir = Path("templates").resolve()
    if not templates_dir.exists():
        templates_dir = Path(__file__).parent.parent.parent / "templates"
    
    templates_list = []

    try:
        if not templates_dir.exists():
            logger.warning(f"Templates directory not found: {templates_dir}")
            return []

        json_files = list(templates_dir.glob("*.json"))

        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                    if "code" in template_data and "name" in template_data:
                        templates_list.append({
                            "code": template_data["code"],
                            "name": template_data["name"]
                        })
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Error reading template file {json_file}: {str(e)}")
                continue

        return templates_list

    except Exception as e:
        logger.error(f"Error listing templates: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error listing templates: {str(e)}")

# Path to the templates directory
TEMPLATES_DIR = Path("/app/templates")
# For local development, fall back to the local path
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Create templates directory if it doesn't exist
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

def load_template(template_name: str) -> Dict[str, Any]:
    """Load template configuration from JSON file."""
    template_path = os.path.join("templates", f"{template_name}.json")
    try:
        with open(template_path, 'r') as f:
            template = json.load(f)
            # Log the loaded template for debugging
            logger.info(f"Loaded template from {template_path}:")
            logger.info(json.dumps(template, indent=2))
            
            # Verify fields structure
            if 'fields' in template and isinstance(template['fields'], list):
                logger.info(f"Template contains {len(template['fields'])} fields")
                for field in template['fields']:
                    logger.info(f"Field: {field.get('code')} - Model: {field.get('model')}")
            
            return template
    except FileNotFoundError:
        error_msg = f"Template file not found: {template_path}"
        logger.error(error_msg)
        raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in template file {template_path}: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Error loading template {template_path}: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


# def get_model_config(field_config: Dict[str, Any], template_config: Dict[str, Any]) -> Dict[str, str]:
#     """
#     Get model configuration with fallback mechanism.
#     Order of precedence:
#     1. Field-specific config (if model is specified)
#     2. Template defaults (defaultModel and defaultMode)
#     3. System defaults
#     """
#     logger.info(f"Getting model config for field: {field_config}")
#     logger.info(f"Template config: {template_config}")
    
#     # System defaults (lowest priority)
#     defaults = {
#         "model": "gpt-5",
#         "mode": "low",
#         "type": "verbatim"
#     }
    
#     # Template defaults (medium priority)
#     template_defaults = {
#         "model": template_config.get("defaultModel", defaults["model"]),
#         "mode": template_config.get("defaultMode", defaults["mode"]),
#         "type": field_config.get("typeOfPrompt", defaults["type"])
#     }
    
#     # Field-specific config (highest priority)
#     field_specific = {
#         "model": field_config.get("model"),
#         "mode": field_config.get("mode"),
#         "type": field_config.get("typeOfPrompt")
#     }
    
#     # Log the configuration sources
#     logger.info(f"System defaults: {defaults}")
#     logger.info(f"Template defaults: {template_defaults}")
#     logger.info(f"Field specific config: {field_specific}")
    
#     # Build the final config with fallbacks
#     final_config = {}
#     for key in ["model", "mode", "type"]:
#         # Use field-specific value if it exists and is not empty, otherwise fall back to template defaults, then system defaults
#         final_config[key] = (
#             field_specific.get(key) or 
#             template_defaults.get(key) or 
#             defaults.get(key)
#         )
    
#     logger.info(f"Final model config: {final_config}")
#     return final_config
    
#     # Merge with order of precedence
#     config = {}
#     for key in ["model", "mode", "type"]:
#         field_val = field_specific.get(key)
#         template_val = template_defaults.get(key)
#         default_val = defaults[key]
        
#         logger.info(f"\nKey: {key}")
#         logger.info(f"Field value: {field_val}")
#         logger.info(f"Template value: {template_val}")
#         logger.info(f"Default value: {default_val}")
        
#         config[key] = field_val or template_val or default_val
#         logger.info(f"Selected value: {config[key]}")
    
#     # Ensure model is valid
#     valid_models = {
#         "gpt-5", "claude", "llama", "gemini",
#         "gpt-4", "gpt-3.5-turbo", "gpt-4.1-mini" , "gpt-5-mini"
#     }
#     if config["model"].lower() not in valid_models:
#         logging.warning(f"Model '{config['model']}' not in valid models, using default 'gpt-5'")
#         config["model"] = "gpt-5"
    
#     # Ensure mode is valid
#     valid_modes = {"low", "medium", "high"}
#     if config["mode"].lower() not in valid_modes:
#         logging.warning(f"Mode '{config['mode']}' not valid, using default 'low'")
#         config["mode"] = "low"
    
#     # Ensure type is valid
#     valid_types = {"verbatim", "summarize"}
#     if config["type"].lower() not in valid_types:
#         logging.warning(f"Type '{config['type']}' not valid, using default 'verbatim'")
#         config["type"] = "verbatim"
    
#     return {
#         "model": str(config["model"]).strip().lower(),
#         "mode": str(config["mode"]).strip().lower(),
#         "type": str(config["type"]).strip().lower()
#     }
#     logger.info(f"Getting model config for field: {field_config}")
#     logger.info(f"Template config: {template_config}")
    
#     # System defaults (lowest priority)
#     defaults = {
#         "model": "gpt-5",
#         "mode": "low",
#         "type": "verbatim"
#     }
#     logger.info(f"System defaults: {defaults}")
    
#     # Template defaults (medium priority) - match the exact JSON field names
#     template_defaults = {
#         "model": template_config.get("defaultModel"),  # Matches JSON's defaultModel
#         "mode": template_config.get("defaultMode"),    # Matches JSON's defaultMode
#         "type": "verbatim"  # No template-level default for type
#     }
    
#     logger.info(f"Template defaults: {template_defaults}")
    
#     # Field-specific config (highest priority) - match the exact JSON field names
#     field_specific = {
#         "model": field_config.get("model"),
#         "mode": field_config.get("mode"),
#         "type": field_config.get("typeOfPrompt")  # Matches JSON's typeOfPrompt
#     }
#     logger.info(f"Field specific config: {field_specific}")
    
#     # Merge with order of precedence
#     config = {}
#     for key in ["model", "mode", "type"]:
#         field_val = field_specific.get(key)
#         template_val = template_defaults.get(key)
#         default_val = defaults[key]
        
#         logger.info(f"\nKey: {key}")
#         logger.info(f"Field value: {field_val}")
#         logger.info(f"Template value: {template_val}")
#         logger.info(f"Default value: {default_val}")
        
#         config[key] = field_val or template_val or default_val
#         logger.info(f"Selected value: {config[key]}")
    
#     # Ensure model is valid
#     valid_models = {
#         "gpt-5", "claude", "llama", "gemini",
#         "gpt-4", "gpt-3.5-turbo", "gpt-4.1-mini"
#     }
#     if config["model"].lower() not in valid_models:
#         logging.warning(f"Model '{config['model']}' not in valid models, using default 'gpt-5'")
#         config["model"] = "gpt-5"
    
#     # Ensure mode is valid
#     valid_modes = {"low", "medium", "high"}
#     if config["mode"].lower() not in valid_modes:
#         logging.warning(f"Mode '{config['mode']}' not valid, using default 'low'")
#         config["mode"] = "low"
    
#     # Ensure type is valid
#     valid_types = {"verbatim", "summarize"}
#     if config["type"].lower() not in valid_types:
#         logging.warning(f"Type '{config['type']}' not valid, using default 'verbatim'")
#         config["type"] = "verbatim"
    
#     return {
#         "model": str(config["model"]).strip().lower(),
#         "mode": str(config["mode"]).strip().lower(),
#         "type": str(config["type"]).strip().lower()
#     }

def get_available_models() -> set[str]:
    """Load and parse the LiteLLM config to get available models."""
    import yaml
    from pathlib import Path
    
    try:
        # Get the absolute path to the config file
        config_path = Path(__file__).resolve().parent.parent.parent / "litellm" / "config.yaml"
        logger.info(f"Looking for config file at: {config_path}")
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found at {config_path}")
            
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            if not config:
                raise ValueError("Config file is empty")
        
        # Log the loaded config (redact sensitive info)
        config_log = {k: v for k, v in config.items() if k != 'model_list'}
        logger.info(f"Loaded config (model_list excluded): {config_log}")
        
        # Extract unique model names from the config
        models = set()
        model_list = config.get('model_list', [])
        logger.info(f"Found {len(model_list)} model configurations")
        
        for i, model_config in enumerate(model_list, 1):
            try:
                logger.debug(f"Processing model config {i}: {model_config}")
                if 'model_name' in model_config:
                    model_name = str(model_config['model_name']).strip().lower()
                    models.add(model_name)
                    logger.debug(f"Added model_name: {model_name}")
                
                if 'litellm_params' in model_config and 'model' in model_config['litellm_params']:
                    model = str(model_config['litellm_params']['model']).strip().lower()
                    models.add(model)
                    logger.debug(f"Added model from litellm_params: {model}")
            except Exception as e:
                logger.warning(f"Error processing model config {i}: {str(e)}")
                continue
        
        if not models:
            raise ValueError("No valid models found in config")
            
        return models
        
    except Exception as e:
        logger.error(f"Error loading LiteLLM config: {str(e)}. Using default models.")
        # Return default models including gpt-5-mini
        default_models = {"gpt-5", "gpt-4", "gpt-3.5-turbo", "claude", "llama", "gemini", "gpt-4.1-mini", "gpt-5-mini"}
        logger.info(f"Using default models: {default_models}")
        return default_models

def get_model_config(field_config: Dict[str, Any], template_config: Dict[str, Any]) -> Dict[str, str]:
    """
    Get model configuration with fallback mechanism.
    Order of precedence:
    1. Field-specific config (if model is specified)
    2. Template defaults (defaultModel and defaultMode)
    3. System defaults
    
    Args:
        field_config: Configuration specific to the field being processed
        template_config: Template-level configuration with defaults
        
    Returns:
        Dictionary with model, mode, and type configurations
    """
    logger.info(f"Getting model config for field: {field_config}")
    logger.info(f"Template config: {template_config}")
    
    # Get available models from LiteLLM config
    valid_models = get_available_models()
    logger.info(f"Available models from config: {valid_models}")
    
    # System defaults (lowest priority)
    defaults = {
        "model": "gpt-5",
        "mode": "low",
        "type": "verbatim"
    }
    
    # Template defaults (medium priority)
    template_defaults = {
        "model": template_config.get("defaultModel", defaults["model"]),
        "mode": template_config.get("defaultMode", defaults["mode"]),
        "type": field_config.get("typeOfPrompt", defaults["type"])
    }
    
    # Field-specific config (highest priority)
    field_specific = {
        "model": field_config.get("model"),
        "mode": field_config.get("mode"),
        "type": field_config.get("typeOfPrompt")
    }
    
    # Log the configuration sources
    logger.info(f"System defaults: {defaults}")
    logger.info(f"Template defaults: {template_defaults}")
    logger.info(f"Field specific config: {field_specific}")
    
    # Build the final config with fallbacks
    config = {}
    for key in ["model", "mode", "type"]:
        # Use field-specific value if it exists and is not empty, otherwise fall back to template defaults, then system defaults
        config[key] = (
            field_specific.get(key) or 
            template_defaults.get(key) or 
            defaults.get(key)
        )
    
    # Clean and validate the configuration
    config = {
        "model": str(config["model"]).strip().lower(),
        "mode": str(config["mode"]).strip().lower(),
        "type": str(config["type"]).strip().lower()
    }
    
    # Debug: Print detailed information about the models
    
    logger.info("\nAvailable models:")
    for i, model in enumerate(sorted(valid_models), 1):
        logger.info(f"{i}. '{model}' (type: {type(model).__name__}, length: {len(model)})")
        logger.info(f"   Bytes: {list(model.encode('utf-8'))}")
    
    logger.info("\nChecking for exact match...")
    if config["model"] in valid_models:
        logger.info(f"Found exact match for '{config['model']}' in valid_models")
    else:
        logger.warning(f"No exact match found for '{config['model']}' in valid_models")
    
    logger.info("\nChecking for case-insensitive match...")
    model_lower = config['model'].lower()
    matching_models = [m for m in valid_models if m.lower() == model_lower]
    if matching_models:
        logger.info(f"Found case-insensitive match(es): {matching_models}")
    else:
        logger.warning("No case-insensitive matches found")
    
    logger.info("=== END DEBUG ===\n")
    logger.info(f"Model type: {type(config['model'])}, valid_models type: {type(valid_models)}")
    logger.info(f"Model repr: {repr(config['model'])}, valid_models: {[repr(m) for m in valid_models]}")
    
    # Check if model is in valid_models with different comparison methods
    model_found = False
    model_lower = config['model'].lower()
    
    # Method 1: Direct comparison
    if config["model"] in valid_models:
        model_found = True
        logger.info(f"Found model using direct comparison: {config['model']}")
    # Method 2: Case-insensitive comparison
    elif any(m.lower() == model_lower for m in valid_models):
        matching_models = [m for m in valid_models if m.lower() == model_lower]
        config["model"] = matching_models[0]
        model_found = True
        logger.info(f"Found model using case-insensitive comparison: {matching_models[0]}")
    # Method 3: Check for any substring match
    elif any(model_lower in m.lower() or m.lower() in model_lower for m in valid_models):
        matching_models = [m for m in valid_models if model_lower in m.lower() or m.lower() in model_lower]
        config["model"] = matching_models[0]
        model_found = True
        logger.info(f"Found model using substring match: {matching_models[0]}")
    
    if not model_found:
        logger.warning(f"Model '{config['model']}' not in valid models, using default 'gpt-5'")
        logger.warning(f"Available models are: {valid_models}")
        # Log the type of valid_models and config['model'] for debugging
        logger.warning(f"valid_models type: {type(valid_models)}, model type: {type(config['model'])}")
        # Try case-insensitive match as a fallback
        model_lower = config['model'].lower()
        matching_models = [m for m in valid_models if m.lower() == model_lower]
        if matching_models:
            logger.info(f"Found case-insensitive match for {config['model']}: {matching_models[0]}")
            config["model"] = matching_models[0]
        else:
            logger.warning(f"No case-insensitive match found for {config['model']}, using default 'gpt-5'")
            config["model"] = "gpt-5"
    
    # Ensure mode is valid
    valid_modes = {"low", "medium", "high"}
    if config["mode"] not in valid_modes:
        logger.warning(f"Mode '{config['mode']}' not valid, using default 'low'")
        config["mode"] = "low"
    
    # Ensure type is valid
    valid_types = {"verbatim", "summarize"}
    if config["type"] not in valid_types:
        logger.warning(f"Type '{config['type']}' not valid, using default 'verbatim'")
        config["type"] = "verbatim"
    
    logger.info(f"Final model config: {config}")
    return config

class FieldConfig(BaseModel):
    field_name: str = Field(..., description="Name of the field to extract")
    prompt: str = Field(..., description="Prompt to extract the field value")
    model: str = Field(default="gpt-5", description="LLM model to use")
    mode: str = Field(default="low", description="Reasoning effort mode")
    type: str = Field(default="verbatim", description="Prompt type: verbatim or summarize")
    
    @field_validator('model', mode='before')
    @classmethod
    def validate_model(cls, v):
        if not v:
            logger.warning("Model not specified, using default 'gpt-5'")
            return "gpt-5"
            
        try:
            # Get available models from the LiteLLM config
            valid_models = get_available_models()
            logger.info(f"Available models in FieldConfig: {valid_models}")
            
            # Convert to lowercase for case-insensitive comparison
            v_lower = v.lower()
            
            # Check if the model is in the valid models (case-insensitive)
            if v_lower not in valid_models:
                # Try case-insensitive match
                matching_models = [m for m in valid_models if m.lower() == v_lower]
                if matching_models:
                    logger.info(f"Found case-insensitive match for '{v}': {matching_models[0]}")
                    return matching_models[0]
                
                logger.warning(f"Model '{v}' not in valid models, using default 'gpt-5'")
                logger.warning(f"Valid models are: {valid_models}")
                return "gpt-5"
                
            logger.info(f"Using model: {v_lower}")
            return v_lower
            
        except Exception as e:
            logger.error(f"Error validating model '{v}': {str(e)}")
            logger.warning(f"Falling back to default model 'gpt-5'")
            return "gpt-5"
    
    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v: str) -> str:
        valid_modes = {"low", "medium", "high"}
        if v.lower() not in valid_modes:
            logging.warning(f"Mode '{v}' not valid, using default 'low'")
            return "low"
        return v.lower()
    
    @field_validator('type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = {"verbatim", "summarize"}
        if v.lower() not in valid_types:
            logging.warning(f"Type '{v}' not valid, using default 'verbatim'")
            return "verbatim"
        return v.lower()


class ProjectSubmitRequest(BaseModel):
    project_name: str = Field(..., description="Name of the project")
    field_names: List[str] = Field(..., description="List of field names to extract from the template")
    template_name: str = Field(default="spa_fields", description="Name of the template to use")


class ProjectSubmitResponse(BaseModel):
    project_id: str
    status: str
    message: str


class ProjectStatusResponse(BaseModel):
    project_id: str
    project_name: str
    status: str
    total_documents: int
    processed_documents: int
    failed_documents: int
    created_at: str
    updated_at: str
    documents: List[dict]

class TemplateProcessResponse(BaseModel):
    success: bool
    message: str
    fields: Dict[str, str]  # key = code, value = label
    total_fields: int
    suggestion: Optional[str] = None  



class DocumentResult(BaseModel):
    document_name: str
    field_results: List[Dict[str, Any]]

class ProjectResultsResponse(BaseModel):
    project_id: str
    project_name: str
    status: str
    documents: Dict[str, DocumentResult]  # doc_id -> document result


@project_router.post("/submit", response_model=ProjectSubmitResponse)
async def submit_project(
    project_name: str = Form(...),
    field_names: str = Form(...),  # JSON array of field names
    template_name: str = Form("spa_fields"),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    Submit a new project with documents and field extraction configuration.
    
    Args:
        project_name: Name of the project
        field_names: JSON array of field names to extract (e.g., ["effective_date", "escrow_account_details"])
        template_name: Name of the template to use (default: "spa_fields")
        files: List of document files to process
    
    Returns:
        ProjectSubmitResponse with project_id and status
    """
    try:
        # Generate project ID
        project_id = str(uuid.uuid4())
        
        # Load template and get field configurations
        try:
            # Parse field names
            requested_fields = json.loads(field_names)
            if not isinstance(requested_fields, list):
                raise ValueError("field_names must be a JSON array of strings")
                
            # Load template
            template = load_template(template_name)
            
            # Get configurations for requested fields
            fields = []
            
            # Check if template has a 'fields' array
            if 'fields' not in template or not isinstance(template['fields'], list):
                raise ValueError("Template must contain a 'fields' array")
                
            # Create a mapping of field codes to their configs
            field_map = {field['code']: field for field in template['fields']}
            
            # Print the template fields for debugging
            logger.debug(f"Template fields: {field_map}")
            
            for field_name in requested_fields:
                if field_name not in field_map:
                    raise ValueError(f"Field '{field_name}' not found in template")
                        
                field_config = field_map[field_name].copy()
                logger.info(f"Processing field: {field_name}")
                logger.info(f"Field config before get_model_config: {field_config}")
                
                # Get model configuration with fallback
                model_config = get_model_config(field_config, template)
                logger.info(f"Final model_config for {field_name}: {model_config}")
                
                # Debug: Print the raw field config and template
                logger.debug(f"Raw field config: {field_config}")
                logger.debug(f"Template config: {template}")
                
                # Print to console for immediate visibility
                print(f"\n=== DEBUG: Field {field_name} ===")
                print(f"Field config: {field_config}")
                print(f"Template default model: {template.get('defaultModel')}")
                print(f"Final model_config: {model_config}\n")
                
                # Map the template fields to the expected FieldConfig format
                config = {
                    "field_name": field_name,
                    "prompt": field_config.get("prompt", ""),
                    **model_config  # This includes model, mode, and type
                }
                fields.append(FieldConfig(**config))
                
            if not fields:
                raise ValueError("No valid field names provided")
                
        except Exception as e:
            logger.error(f"Error processing field configurations: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Error processing field configurations: {str(e)}")
            
        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="At least one document file is required")
    
        # Store uploaded files temporarily and create document metadata
        documents = []
        temp_dir = f"temp_files/{project_id}"
        os.makedirs(temp_dir, exist_ok=True)
        
        for idx, file in enumerate(files):
            # Generate doc_id
            doc_id = f"{project_id}_doc_{idx+1}"
            
            # Read file content
            file_content = await file.read()
            file_hash = hashlib.sha256(file_content).hexdigest()
            
            # Save file temporarily
            file_path = f"{temp_dir}/{file.filename}"
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            documents.append({
                "doc_id": doc_id,
                "doc_name": file.filename,
                "file_path": file_path,
                "file_hash": file_hash,
                "file_size": len(file_content),
                "status": "pending"
            })
            
            logger.info(f"Saved file {file.filename} for project {project_id}")
        
        # Create project in PostgreSQL
        fields_config = [field.model_dump() for field in fields]
        
        # Prepare documents for PostgreSQL (without doc_id as it will be generated)
        pg_documents = [
            {
                "doc_name": doc["doc_name"],
                "file_path": doc["file_path"]
            }
            for doc in documents
        ]
        
        # Create project in database with requested fields in metadata
        project_metadata = {
            "requested_fields": requested_fields,
            "template_name": template_name
        }
        
        db_project = ProjectOperations.create_project(
            db=db,
            project_name=project_name,
            fields_config=fields_config,
            documents=pg_documents
        )
        
        # Update project_id to use the database-generated ID
        project_id = db_project.id
        
        # Update document IDs from database
        for idx, db_doc in enumerate(db_project.documents):
            documents[idx]["doc_id"] = db_doc.id
        
        # Create project metadata for Redis (backward compatibility)
        project_data = {
            "project_id": project_id,
            "project_name": project_name,
            "status": "queued",
            "total_documents": len(documents),
            "processed_documents": 0,
            "failed_documents": 0,
            "created_at": db_project.created_at.isoformat(),
            "updated_at": datetime.now().isoformat(),
            "documents": documents,
            "fields_config": fields_config,
            "temp_dir": temp_dir
        }
        
        # Store in Redis for backward compatibility
        sync_redis.set(
            f"project:{project_id}",
            json.dumps(project_data),
            ex=REDIS_TTL_SECONDS
        )
        
        # Initialize results storage
        sync_redis.set(
            f"project:{project_id}:results",
            json.dumps({}),
            ex=REDIS_TTL_SECONDS
        )
        
        # Enqueue project for parallel processing
        job = project_queue.enqueue(
            'app.api.worker_parallel.process_project_parallel',
            args=(project_id,),
            job_id=project_id,
            job_timeout=7200,  # 2 hours
            result_ttl=REDIS_TTL_SECONDS
        )
        
        logger.info(f"Project {project_id} queued for parallel processing with {len(documents)} documents")
        
        return ProjectSubmitResponse(
            project_id=project_id,
            status="queued",
            message=f"Project submitted successfully with {len(documents)} documents"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to submit project: {str(e)}")


@project_router.get("/{project_id}", response_model=ProjectStatusResponse)
async def get_project_status(project_id: str, db: Session = Depends(get_db)):
    """Get the status of a project"""
    try:
        # logger.info(f"🔍 [Project {project_id}] Checking PostgreSQL for project data...")
        db_project = ProjectOperations.get_project(db, project_id)
        
        if db_project:
            # logger.info(f"✅ [Project {project_id}] Found in PostgreSQL")
            # Get documents from database
            db_documents = DocumentOperations.get_project_documents(db, project_id)
            documents = [
                {
                    "doc_id": doc.id,
                    "doc_name": doc.doc_name,
                    "file_path": doc.file_path,
                    "status": doc.status
                }
                for doc in db_documents
            ]
            
            project_data = {
                "project_id": db_project.id,
                "project_name": db_project.project_name,
                "status": db_project.status,
                "total_documents": db_project.total_documents,
                "processed_documents": db_project.processed_documents or 0,
                "failed_documents": db_project.failed_documents or 0,
                "created_at": db_project.created_at.isoformat(),
                "updated_at": db_project.updated_at.isoformat() if db_project.updated_at else db_project.created_at.isoformat(),
                "documents": documents
            }
            logger.debug(f"📊 [Project {project_id}] PostgreSQL data: {json.dumps(project_data, default=str, indent=2)}")
        else:
            logger.warning(f"⚠️  [Project {project_id}] Not found in PostgreSQL, checking Redis...")
            # Fallback to Redis for backward compatibility
            project_data_json = sync_redis.get(f"project:{project_id}")
            if not project_data_json:
                logger.error(f"❌ [Project {project_id}] Not found in PostgreSQL or Redis")
                raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
            
            logger.info(f"✅ [Project {project_id}] Found in Redis")
            project_data = json.loads(project_data_json)
            logger.debug(f"📊 [Project {project_id}] Redis data: {json.dumps(project_data, default=str, indent=2)}")
        
        return ProjectStatusResponse(
            project_id=project_data["project_id"],
            project_name=project_data["project_name"],
            status=project_data["status"],
            total_documents=project_data["total_documents"],
            processed_documents=project_data["processed_documents"],
            failed_documents=project_data["failed_documents"],
            created_at=project_data["created_at"],
            updated_at=project_data["updated_at"],
            documents=project_data["documents"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get project status: {str(e)}")


@project_router.get("/{project_id}/results", response_model=ProjectResultsResponse)
async def get_project_results(project_id: str, db: Session = Depends(get_db)):
    """Get the extraction results for a project"""
    try:
        # logger.info(f"🔍 [Results {project_id}] Checking PostgreSQL for project results...")
        
        # Get project from PostgreSQL
        db_project = ProjectOperations.get_project(db, project_id)
        if db_project:
            # logger.info(f"✅ [Results {project_id}] Found project in PostgreSQL")
            project_data = {
                "project_id": db_project.id,
                "project_name": db_project.project_name,
                "status": db_project.status
            }
            
            # Get all documents for the project
            db_documents = DocumentOperations.get_project_documents(db, project_id)
            document_map = {str(doc.id): doc.doc_name for doc in db_documents}
            
            # Get results from PostgreSQL
            results = FieldResultOperations.get_project_results(db, project_id)
            
            # Format results with document names
            documents = {}
            for doc_id, field_results in results.items():
                documents[doc_id] = {
                    "document_name": document_map.get(doc_id, "Unknown Document"),
                    "field_results": field_results
                }
                
        else:
            logger.warning(f"⚠️  [Results {project_id}] Project not found in PostgreSQL, checking Redis...")
            
            # Fallback to Redis
            project_data_json = sync_redis.get(f"project:{project_id}")
            if not project_data_json:
                logger.error(f"❌ [Results {project_id}] Project not found in Redis")
                raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
            
            logger.info(f"✅ [Results {project_id}] Found project in Redis")
            project_data = json.loads(project_data_json)
            
            # Get results from Redis
            logger.info(f"📊 [Results {project_id}] Fetching results from Redis...")
            results_json = sync_redis.get(f"project:{project_id}:results")
            results = json.loads(results_json) if results_json else {}
            
            # For Redis, we don't have document names, so we'll use the document ID as the name
            documents = {
                doc_id: {
                    "document_name": f"Document {i+1}",  # Fallback name
                    "field_results": field_results
                }
                for i, (doc_id, field_results) in enumerate(results.items())
            }
            logger.info(f"✅ [Results {project_id}] Retrieved {sum(len(doc['field_results']) for doc in documents.values())} field results from Redis")
        
        response = ProjectResultsResponse(
            project_id=project_data["project_id"],
            project_name=project_data["project_name"],
            status=project_data["status"],
            documents=documents
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get project results: {str(e)}")


@project_router.delete("/{project_id}")
async def delete_project(project_id: str, db: Session = Depends(get_db)):
    """Delete a project and its data"""
    try:
        # Try to get from PostgreSQL first
        db_project = ProjectOperations.get_project(db, project_id)
        
        if db_project:
            temp_dir = db_project.temp_dir
            # Delete from PostgreSQL (cascades to documents and field_results)
            ProjectOperations.delete_project(db, project_id)
        else:
            # Fallback to Redis
            project_data_json = sync_redis.get(f"project:{project_id}")
            if not project_data_json:
                raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
            project_data = json.loads(project_data_json)
            temp_dir = project_data.get("temp_dir")
        
        # Delete temporary files
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir)
            logger.info(f"Deleted temp directory: {temp_dir}")
        
        # Delete from Redis
        sync_redis.delete(f"project:{project_id}")
        sync_redis.delete(f"project:{project_id}:results")
        
        # Delete from Weaviate (will be done by worker if needed)
        
        logger.info(f"Deleted project {project_id}")
        
        return {"status": "success", "message": f"Project {project_id} deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


# Add this new endpoint after the delete_project endpoint

@project_router.post("/{project_id}/documents", response_model=Dict[str, Any])
async def add_documents_to_project(
    project_id: str = FastAPIPath(..., description="ID of the project"),
    files: List[UploadFile] = File(...),
    field_names: str = Form("[]"),  # JSON array string of field names
    template_name: str = Form("spa_fields"),
    db: Session = Depends(get_db)
):
    """
    Add new documents to an existing project.
    """
    try:
        # Get project
        project = ProjectOperations.get_project(db, project_id)
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        # Parse field names from JSON string
        try:
            fields_to_extract = json.loads(field_names)
            if not isinstance(fields_to_extract, list):
                raise ValueError("field_names must be a JSON array")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid field_names format. Must be a JSON array")
        
        # Process each file
        results = []
        for file in files:
            try:
                # Use the existing temp_files directory
                upload_dir = "/app/temp_files"
                os.makedirs(upload_dir, exist_ok=True)
                
                # Save the file to the temp_files directory with a unique name
                file_ext = os.path.splitext(file.filename)[1]
                unique_filename = f"{uuid.uuid4()}{file_ext}"
                file_path = os.path.join(upload_dir, unique_filename)
                logger.info(f"Saving uploaded file to: {file_path}")
                with open(file_path, "wb") as f:
                    f.write(await file.read())
                
                # Create document record
                document = Document(
                    project_id=project_id,
                    doc_name=file.filename,
                    file_path=file_path,
                    status="pending"
                )
                db.add(document)
                db.commit()
                db.refresh(document)
                
                # Enqueue for processing with field names in metadata
                # Enqueue for processing with field names in metadata
                job = document_queue.enqueue(
                    process_document,
                    args=(project_id, document.id),  # Correct order: (project_id, document_id)
                    kwargs={
                        'field_names': fields_to_extract,  # Pass the field names to filter
                        'is_regeneration': False
                    },
                    job_id=f"doc_{document.id}_{int(datetime.utcnow().timestamp())}",
                    result_ttl=REDIS_TTL_SECONDS,
                    failure_ttl=REDIS_TTL_SECONDS,
                    timeout="30m"
                )
                
                results.append({
                    "filename": file.filename,
                    "document_id": document.id,
                    "status": "queued",
                    "job_id": job.id
                })
                
            except Exception as e:
                logger.error(f"Error processing {file.filename}: {str(e)}")
                results.append({
                    "filename": file.filename,
                    "error": str(e),
                    "status": "failed"
                })
        
        return {
            "project_id": project_id,
            "template_name": template_name,
            "documents_added": len([r for r in results if r.get("status") == "queued"]),
            "documents_failed": len([r for r in results if r.get("status") == "failed"]),
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding documents to project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to add documents: {str(e)}")


@project_router.post("/{project_id}/documents/{document_id}/regenerate", response_model=Dict[str, Any])
async def regenerate_document(
    project_id: str = FastAPIPath(..., description="ID of the project"),
    document_id: str = FastAPIPath(..., description="ID of the document to regenerate"),
    field_names: str = Query("", description="Comma-separated list of field names to regenerate (leave empty for all fields)"),
    db: Session = Depends(get_db)
):
    """
    Regenerate a specific document in a project.
    This will clear existing field extractions and reprocess the document.
    If field_names is provided, only those fields will be regenerated.
    """
    # Get the project and document
    project = ProjectOperations.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.project_id == project_id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found in project {project_id}")
    
    # Parse field names if provided
    fields_to_regenerate = []
    if field_names:
        fields_to_regenerate = [f.strip() for f in field_names.split(",") if f.strip()]
    
    # Clear existing field results (filtered if field names provided)
    field_result_query = db.query(FieldResult).filter(FieldResult.document_id == document_id)
    if fields_to_regenerate:
        field_result_query = field_result_query.filter(FieldResult.field_name.in_(fields_to_regenerate))
    field_result_query.delete()
    
    # Clear any existing queue entries for this document
    db.query(DocumentQueue).filter(DocumentQueue.document_id == document_id).delete()
    
    field_queue_query = db.query(FieldQueue).filter(FieldQueue.document_id == document_id)
    if fields_to_regenerate:
        field_queue_query = field_queue_query.filter(FieldQueue.field_name.in_(fields_to_regenerate))
    field_queue_query.delete()
    
    # Reset document status
    document.status = "pending"
    document.completed_at = None
    document.error_message = None
    document.processing_time = None
    db.commit()
    
    try:
        # Prepare job arguments
        job_kwargs = {
            "document_id": document_id,
            "project_id": project_id,
            "is_regeneration": True,
            "job_id": f"doc_{document_id}_{int(datetime.utcnow().timestamp())}",
            "result_ttl": REDIS_TTL_SECONDS,
            "failure_ttl": REDIS_TTL_SECONDS,
            "timeout": "30m"
        }
        
        # Add field_names to job kwargs if specified
        if fields_to_regenerate:
            job_kwargs["field_names"] = fields_to_regenerate
        
        # Enqueue for reprocessing
        job = document_queue.enqueue(process_document, **job_kwargs)
        
        return {
            "status": "queued",
            "message": f"Document {document_id} has been queued for reprocessing",
            "job_id": job.id,
            "document_id": document_id,
            "project_id": project_id,
            "fields_to_regenerate": fields_to_regenerate if fields_to_regenerate else "all"
        }
    except Exception as e:
        document.status = "failed"
        document.error_message = str(e)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue document for reprocessing: {str(e)}"
        )


@project_router.get("", response_model=List[ProjectStatusResponse], summary="List all projects")
async def list_all_projects(
    skip: int = 0, 
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    List all projects with their basic information.
    
    Args:
        skip: Number of projects to skip (for pagination)
        limit: Maximum number of projects to return (for pagination)
        
    Returns:
        List of ProjectStatusResponse objects with project details
    """
    try:
        # Test database connection first
        try:
            db.execute(text("SELECT 1"))
        except Exception as db_error:
            logger.error(f"Database connection error: {str(db_error)}")
            raise HTTPException(
                status_code=503,
                detail="Unable to connect to the database. Please try again later."
            )
            
        # Get projects using ProjectOperations for consistency
        projects = db.query(Project).order_by(Project.created_at.desc()).offset(skip).limit(limit).all()
        
        if not projects:
            logger.info("No projects found in the database")
            return []
            
        # Convert to response model
        result = []
        for project in projects:
            # Get document count for the project
            document_count = len(project.documents) if hasattr(project, 'documents') else 0
            
            # Format timestamps, ensuring they're never None
            created_at = project.created_at.isoformat() if project.created_at else datetime.utcnow().isoformat()
            updated_at = project.updated_at.isoformat() if project.updated_at else created_at
            
            result.append(ProjectStatusResponse(
                project_id=project.id,
                project_name=project.project_name or "Unnamed Project",
                status=project.status or "unknown",
                total_documents=document_count,
                processed_documents=project.processed_documents or 0,
                failed_documents=project.failed_documents or 0,
                created_at=created_at,
                updated_at=updated_at,
                documents=[]  # Not including documents in list view for performance
            ))
            
        logger.info(f"Successfully retrieved {len(result)} projects")
        return result
        
    except Exception as e:
        logger.error(f"Error listing projects: {str(e)}", exc_info=True)
        # For other errors, return a generic error message
        raise HTTPException(
            status_code=500, 
            detail=f"An error occurred while fetching projects: {str(e)}"
        )


@project_router.post("/process-template", response_model=TemplateProcessResponse)
async def process_template(template_name: str = Body(..., embed=True, description="Name of the template file (without .json extension)")):
    """
    Process a JSON template file from the templates directory and return all active fields with their configurations.
    
    Args:
        template_name: Name of the template file (without .json extension)
        
    Returns:
        TemplateProcessResponse with processing results
    """
    logger.info(f"Processing template: {template_name}")
    logger.info(f"TEMPLATES_DIR: {TEMPLATES_DIR}")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    try:
        # Construct the template path
        template_path = TEMPLATES_DIR / f"{template_name}"
        logger.info(f"Initial template path: {template_path}")
        
        # Check if file exists
        if not template_path.exists():
            # Try with .json extension if not already present
            if not template_path.suffix:
                template_path = template_path.with_suffix('.json')
                logger.info(f"Trying with .json extension: {template_path}")
            
            if not template_path.exists():
                available_templates = [f.stem for f in TEMPLATES_DIR.glob('*.json')]
                logger.error(f"Template not found. Available templates: {available_templates}")
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": f"Template '{template_name}' not found in {TEMPLATES_DIR}",
                        "available_templates": available_templates
                    }
                )
        
        logger.info(f"Found template at: {template_path}")
        
        # Read and parse the JSON file
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            logger.info(f"Successfully loaded template data. Fields found: {len(template_data.get('fields', []))}")
        except Exception as e:
            logger.error(f"Error reading/parsing template file: {str(e)}", exc_info=True)
            raise
        
        # Extract active fields as code->label mapping
        active_fields = {}
        if 'fields' in template_data:
            for field in template_data['fields']:
                if field.get('isActive', True):  # Default to True if not specified
                    code = field.get('code', '')
                    label = field.get('label', '')
                    if code:
                        active_fields[code] = label
        
        response = {
            'success': True,
            'message': f"Successfully processed template: {template_data.get('name', 'Unnamed Template')}",
            'fields': active_fields,  # key = code, value = label
            'total_fields': len(active_fields),
            'suggestion': template_data.get('suggestion', '')  # ✅ Added this line
        }
        logger.info(response)
        
        logger.info(f"Successfully processed template. Found {len(active_fields)} active fields.")
        return response
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in template {template_path}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=400, detail=error_msg)
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error processing template {template_path}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=error_msg)



@project_router.put("/field-result/{document_id}/{field_name}")
async def update_field_result(
    document_id: str,
    field_name: str,
    updates: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db)
):
    """
    Update field result value and source pages in the database.
    
    Args:
        document_id: ID of the document
        field_name: Name of the field to update
        updates: Dictionary with fields to update (e.g., {"value": "new value", "source_pages": [1, 2, 3]})
    
    Returns:
        Updated field result information
    """
    try:
        # Get the field result
        field_result = FieldResultOperations.get_field_result(db, document_id, field_name)
        if not field_result:
            raise HTTPException(status_code=404, detail=f"Field result not found for document {document_id}, field {field_name}")
        
        # List of allowed fields to update
        allowed_fields = [
            "value", "answer_html", "explanation", "confidence",
            "source_pages", "chunks", "status", "error_message"
        ]
        
        # Filter and validate updates
        valid_updates = {}
        for field, value in updates.items():
            if field in allowed_fields:
                valid_updates[field] = value
            else:
                logger.warning(f"Attempted to update non-allowed field: {field}")
        
        if not valid_updates:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        # Update the field result
        updated_field = FieldResultOperations.update_field_result(
            db, document_id, field_name, valid_updates
        )
        
        if not updated_field:
            raise HTTPException(status_code=500, detail="Failed to update field result")
        
        logger.info(f"Updated field '{field_name}' for document {document_id} with fields: {list(valid_updates.keys())}")
        
        return {
            "document_id": document_id,
            "field_name": field_name,
            "value": updated_field.value,
            "source_pages": updated_field.source_pages,
            "confidence": updated_field.confidence,
            "status": updated_field.status,
            "updated_fields": list(valid_updates.keys()),
            "updated_at": updated_field.updated_at.isoformat() if updated_field.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating field result for document {document_id}, field {field_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update field result: {str(e)}")
