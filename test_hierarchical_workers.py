#!/usr/bin/env python3
"""
Test script for hierarchical worker system.
This script verifies that workers are spawned correctly and process tasks in isolation.
"""

import os
import sys
import time
import redis
from rq import Queue
from typing import Dict, List

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def get_redis_connection():
    """Get Redis connection."""
    return redis.from_url(REDIS_URL)


def list_all_queues(r: redis.Redis) -> List[str]:
    """List all RQ queues in Redis."""
    queues = []
    for key in r.keys('rq:queue:*'):
        queue_name = key.decode('utf-8').replace('rq:queue:', '')
        queues.append(queue_name)
    return sorted(queues)


def get_queue_info(r: redis.Redis, queue_name: str) -> Dict:
    """Get information about a specific queue."""
    queue = Queue(queue_name, connection=r)
    return {
        "name": queue_name,
        "jobs": len(queue),
        "started_jobs": queue.started_job_registry.count,
        "finished_jobs": queue.finished_job_registry.count,
        "failed_jobs": queue.failed_job_registry.count,
    }


def check_hierarchical_queues(r: redis.Redis, project_id: str = None) -> Dict:
    """Check for hierarchical queue structure."""
    all_queues = list_all_queues(r)
    
    result = {
        "global_queues": [],
        "project_queues": [],
        "document_queues": [],
        "total_queues": len(all_queues)
    }
    
    for queue_name in all_queues:
        if ':' not in queue_name:
            # Global queue
            result["global_queues"].append(queue_name)
        elif queue_name.startswith('documents:'):
            # Project-specific document queue
            result["project_queues"].append(queue_name)
        elif queue_name.startswith('fields:'):
            # Document-specific field queue
            result["document_queues"].append(queue_name)
    
    return result


def print_queue_summary(r: redis.Redis):
    """Print a summary of all queues and their status."""
    print("\n" + "="*80)
    print("QUEUE SUMMARY")
    print("="*80)
    
    all_queues = list_all_queues(r)
    
    if not all_queues:
        print("No queues found.")
        return
    
    for queue_name in all_queues:
        info = get_queue_info(r, queue_name)
        print(f"\nQueue: {queue_name}")
        print(f"  Active jobs: {info['jobs']}")
        print(f"  Started: {info['started_jobs']}")
        print(f"  Finished: {info['finished_jobs']}")
        print(f"  Failed: {info['failed_jobs']}")


def check_worker_mode() -> str:
    """Check which worker mode is configured."""
    use_hierarchical = os.getenv("USE_HIERARCHICAL_WORKERS", "false").lower()
    return "hierarchical" if use_hierarchical == "true" else "traditional"


def print_worker_config():
    """Print current worker configuration."""
    mode = check_worker_mode()
    
    print("\n" + "="*80)
    print("WORKER CONFIGURATION")
    print("="*80)
    print(f"Mode: {mode.upper()}")
    
    if mode == "hierarchical":
        print(f"NUM_PROJECT_WORKERS: {os.getenv('NUM_PROJECT_WORKERS', '1')}")
        print(f"NUM_DOC_WORKERS_PER_PROJECT: {os.getenv('NUM_DOC_WORKERS_PER_PROJECT', '2')}")
        print(f"NUM_FIELD_WORKERS_PER_DOC: {os.getenv('NUM_FIELD_WORKERS_PER_DOC', '5')}")
    else:
        print(f"NUM_PROJECT_WORKERS: {os.getenv('NUM_PROJECT_WORKERS', '1')}")
        print(f"NUM_DOC_WORKERS: {os.getenv('NUM_DOC_WORKERS', '3')}")
        print(f"NUM_FIELD_WORKERS: {os.getenv('NUM_FIELD_WORKERS', '5')}")


def verify_hierarchical_structure(r: redis.Redis, project_id: str = None):
    """Verify that hierarchical queue structure exists."""
    print("\n" + "="*80)
    print("HIERARCHICAL STRUCTURE VERIFICATION")
    print("="*80)
    
    structure = check_hierarchical_queues(r, project_id)
    
    print(f"\nTotal queues: {structure['total_queues']}")
    
    print(f"\nGlobal queues ({len(structure['global_queues'])}):")
    for queue in structure['global_queues']:
        print(f"  - {queue}")
    
    print(f"\nProject-specific document queues ({len(structure['project_queues'])}):")
    for queue in structure['project_queues']:
        print(f"  - {queue}")
    
    print(f"\nDocument-specific field queues ({len(structure['document_queues'])}):")
    for queue in structure['document_queues']:
        print(f"  - {queue}")
    
    # Verify hierarchical structure
    mode = check_worker_mode()
    if mode == "hierarchical":
        if structure['project_queues'] or structure['document_queues']:
            print("\n✅ Hierarchical queue structure detected!")
        else:
            print("\n⚠️  No hierarchical queues found. Workers may not have spawned yet.")
    else:
        if structure['global_queues'] and not structure['project_queues']:
            print("\n✅ Traditional parallel structure detected!")
        else:
            print("\n⚠️  Unexpected queue structure for traditional mode.")


def monitor_queue_activity(r: redis.Redis, duration: int = 30):
    """Monitor queue activity for a specified duration."""
    print("\n" + "="*80)
    print(f"MONITORING QUEUE ACTIVITY FOR {duration} SECONDS")
    print("="*80)
    
    start_time = time.time()
    previous_queues = set()
    
    while time.time() - start_time < duration:
        current_queues = set(list_all_queues(r))
        
        # Check for new queues
        new_queues = current_queues - previous_queues
        if new_queues:
            print(f"\n[{time.strftime('%H:%M:%S')}] New queues detected:")
            for queue in new_queues:
                print(f"  + {queue}")
        
        # Check for removed queues
        removed_queues = previous_queues - current_queues
        if removed_queues:
            print(f"\n[{time.strftime('%H:%M:%S')}] Queues removed:")
            for queue in removed_queues:
                print(f"  - {queue}")
        
        previous_queues = current_queues
        time.sleep(2)
    
    print("\nMonitoring complete.")


def main():
    """Main test function."""
    print("="*80)
    print("HIERARCHICAL WORKER SYSTEM TEST")
    print("="*80)
    
    # Print configuration
    print_worker_config()
    
    # Connect to Redis
    try:
        r = get_redis_connection()
        r.ping()
        print("\n✅ Connected to Redis")
    except Exception as e:
        print(f"\n❌ Failed to connect to Redis: {e}")
        sys.exit(1)
    
    # Print queue summary
    print_queue_summary(r)
    
    # Verify hierarchical structure
    verify_hierarchical_structure(r)
    
    # Check if we should monitor
    if len(sys.argv) > 1 and sys.argv[1] == "--monitor":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        monitor_queue_activity(r, duration)
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
    print("\nTo enable hierarchical mode:")
    print("  1. Set USE_HIERARCHICAL_WORKERS=true in .env")
    print("  2. Configure NUM_DOC_WORKERS_PER_PROJECT and NUM_FIELD_WORKERS_PER_DOC")
    print("  3. Restart workers: docker-compose restart workers")
    print("\nTo monitor queue activity:")
    print("  python test_hierarchical_workers.py --monitor [duration_seconds]")
    print()


if __name__ == "__main__":
    main()
