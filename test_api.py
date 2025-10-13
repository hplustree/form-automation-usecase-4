#!/usr/bin/env python3
"""
Sample script to test SISO Pipeline API
"""

import requests
import json
import time
from pathlib import Path

API_BASE_URL = "http://localhost:8001/api"

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    response = requests.get("http://localhost:8001/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    print()

def submit_project(project_name, fields_config, file_paths):
    """Submit a new project"""
    print(f"Submitting project: {project_name}")
    
    # Prepare files
    files = []
    for file_path in file_paths:
        if Path(file_path).exists():
            files.append(('files', open(file_path, 'rb')))
        else:
            print(f"Warning: File not found: {file_path}")
    
    if not files:
        print("Error: No valid files to upload")
        return None
    
    # Prepare form data
    data = {
        'project_name': project_name,
        'fields_config': json.dumps(fields_config)
    }
    
    # Submit
    response = requests.post(f"{API_BASE_URL}/project/submit", data=data, files=files)
    
    # Close file handles
    for _, file_handle in files:
        file_handle.close()
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Project submitted successfully")
        print(f"  Project ID: {result['project_id']}")
        print(f"  Status: {result['status']}")
        print()
        return result['project_id']
    else:
        print(f"✗ Error: {response.status_code}")
        print(f"  {response.text}")
        print()
        return None

def get_project_status(project_id):
    """Get project status"""
    print(f"Getting status for project: {project_id}")
    response = requests.get(f"{API_BASE_URL}/project/{project_id}")
    
    if response.status_code == 200:
        status = response.json()
        print(f"  Status: {status['status']}")
        print(f"  Documents: {status['processed_documents']}/{status['total_documents']}")
        print(f"  Failed: {status['failed_documents']}")
        print()
        return status
    else:
        print(f"✗ Error: {response.status_code}")
        print()
        return None

def get_project_results(project_id):
    """Get project results"""
    print(f"Getting results for project: {project_id}")
    response = requests.get(f"{API_BASE_URL}/project/{project_id}/results")
    
    if response.status_code == 200:
        results = response.json()
        print(f"  Status: {results['status']}")
        print(f"  Results:")
        
        for doc_id, doc_results in results['results'].items():
            print(f"\n  Document: {doc_id}")
            for field_name, field_data in doc_results.items():
                print(f"    {field_name}:")
                print(f"      Value: {field_data['value']}")
                print(f"      Confidence: {field_data['confidence']:.2f}")
                print(f"      Pages: {field_data['source_pages']}")
        print()
        return results
    else:
        print(f"✗ Error: {response.status_code}")
        print()
        return None

def list_projects():
    """List all projects"""
    print("Listing all projects...")
    response = requests.get(f"{API_BASE_URL}/projects")
    
    if response.status_code == 200:
        projects = response.json()
        print(f"  Found {len(projects)} projects:")
        for project in projects:
            print(f"    - {project['project_name']} ({project['project_id'][:8]}...)")
            print(f"      Status: {project['status']}")
            print(f"      Documents: {project['processed_documents']}/{project['total_documents']}")
        print()
        return projects
    else:
        print(f"✗ Error: {response.status_code}")
        print()
        return None

def wait_for_completion(project_id, max_wait=600, check_interval=10):
    """Wait for project to complete"""
    print(f"Waiting for project completion (max {max_wait}s)...")
    
    start_time = time.time()
    while time.time() - start_time < max_wait:
        status = get_project_status(project_id)
        
        if status and status['status'] in ['completed', 'completed_with_errors', 'failed']:
            print(f"✓ Project {status['status']}")
            return status
        
        print(f"  Still processing... (waiting {check_interval}s)")
        time.sleep(check_interval)
    
    print("✗ Timeout waiting for completion")
    return None

def main():
    """Main test function"""
    print("=" * 60)
    print("SISO Pipeline API Test")
    print("=" * 60)
    print()
    
    # Test health
    test_health()
    
    # Example: Submit a project
    # NOTE: Replace these with your actual file paths
    fields_config = [
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
            "mode": "low",
            "type": "verbatim"
        }
    ]
    
    # Example file paths - UPDATE THESE
    file_paths = [
        # "path/to/your/document1.pdf",
        # "path/to/your/document2.pdf",
    ]
    
    if not file_paths:
        print("⚠ No file paths configured in test_api.py")
        print("  Update the file_paths list with your document paths")
        print()
        print("Example usage:")
        print("  file_paths = ['contract1.pdf', 'contract2.pdf']")
        print()
        
        # Just list existing projects
        list_projects()
        return
    
    # Submit project
    project_id = submit_project("Test Project", fields_config, file_paths)
    
    if not project_id:
        print("Failed to submit project")
        return
    
    # Wait for completion
    final_status = wait_for_completion(project_id)
    
    if final_status:
        # Get results
        get_project_results(project_id)
    
    # List all projects
    list_projects()

if __name__ == "__main__":
    main()
