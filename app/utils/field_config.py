import json
import os
from typing import Dict, List, Optional
from pathlib import Path

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')

def load_field_configs(template_name: str, field_names: List[str]) -> List[Dict]:
    """
    Load field configurations from a template file.
    
    Args:
        template_name: Name of the template file (without .json extension)
        field_names: List of field names to include from the template
        
    Returns:
        List of field configurations in the format expected by the API
        
    Raises:
        FileNotFoundError: If the template file doesn't exist
        KeyError: If a requested field is not found in the template
    """
    template_path = os.path.join(TEMPLATES_DIR, f"{template_name}.json")
    
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template '{template_name}' not found in {TEMPLATES_DIR}")
    
    with open(template_path, 'r') as f:
        template = json.load(f)
    
    result = []
    for field_name in field_names:
        if field_name not in template:
            raise KeyError(f"Field '{field_name}' not found in template '{template_name}'")
        
        field_config = template[field_name].copy()
        field_config['field_name'] = field_name
        result.append(field_config)
    
    return result

def list_available_templates() -> List[str]:
    """List all available template files (without .json extension)"""
    try:
        return [f.stem for f in Path(TEMPLATES_DIR).glob('*.json')]
    except Exception as e:
        return []
