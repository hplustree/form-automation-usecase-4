"""
Parallel worker launcher for document and field processing.
This launcher starts separate workers for:
1. Document processing queue
2. Field extraction queue
3. Project coordination queue
"""

import os
import sys
import time
import signal
import subprocess
import uuid
from app.logging_config import logger


def main():
    # New parallel processing architecture with ThreadPoolExecutor
    try:
        num_project_workers = int(os.getenv("NUM_PROJECT_WORKERS", "1"))
        max_concurrent_docs = int(os.getenv("MAX_CONCURRENT_DOCS", "2"))
        max_concurrent_fields = int(os.getenv("MAX_CONCURRENT_FIELDS", "5"))
        num_document_workers = int(os.getenv("NUM_DOCUMENT_WORKERS", str(max_concurrent_docs)))
    except ValueError:
        num_project_workers = 1
        max_concurrent_docs = 2
        max_concurrent_fields = 5
        num_document_workers = 2
    
    msg = (f"Starting PARALLEL PROCESSING workers: {num_project_workers} project workers\n"
           f"  Each project worker will process up to {max_concurrent_docs} documents concurrently\n"
           f"  Each document will process up to {max_concurrent_fields} fields concurrently")
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    print(msg, flush=True)
    logger.info(msg)
    
    procs = []
    
    def terminate_all(signum=None, frame=None):
        logger.info("Received shutdown signal. Terminating all RQ workers...")
        for p in procs:
            try:
                if p.poll() is None:
                    p.terminate()
            except Exception:
                pass
        # Give them a moment to exit cleanly
        time.sleep(2)
        for p in procs:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass
    
    signal.signal(signal.SIGTERM, terminate_all)
    signal.signal(signal.SIGINT, terminate_all)
    
    # Each worker will process MAX_CONCURRENT_DOCS documents in parallel
    # Total documents in parallel = NUM_PROJECT_WORKERS * MAX_CONCURRENT_DOCS
    worker_max_docs = max_concurrent_docs  # Each worker processes this many documents in parallel
    
    # Launch project workers
    for i in range(num_project_workers):
        worker_id = f"project-{i+1}-{int(time.time())}"
        start_msg = f"Launching project worker {i+1} (max {max_concurrent_docs} concurrent docs)"
        print(start_msg, flush=True)
        logger.info(start_msg)
        
        p = subprocess.Popen([
            "rq", "worker", "projects",
            "--url", redis_url,
            "--job-class", "rq.job.Job",
            "--worker-ttl", "10800",  # 3 hour worker TTL
            "--max-jobs", "1000",     # Keep worker running for many jobs
            "--with-scheduler",        # Enable job requeue on failure
            "--name", f"project-worker-{worker_id}"
        ], env={
            **os.environ,
            "MAX_CONCURRENT_DOCS": str(max_concurrent_docs),
            "MAX_CONCURRENT_FIELDS": str(max_concurrent_fields),
            "WORKER_TYPE": "project",
            "WORKER_ID": f"project-{i+1}",
            "RQ_WORKER_MAX_JOBS": "1000",  # Keep worker running
            "RQ_WORKER_GRACEFUL_SHUTDOWN_TIMEOUT": "300"  # 5 minutes to finish
        })
        procs.append(p)
    
    # Launch document workers (2 per project worker by default)
    total_doc_workers = num_project_workers * num_document_workers
    logger.info(f"Launching {total_doc_workers} document workers ({num_document_workers} per project worker)")
    for i in range(1, total_doc_workers + 1):
        start_msg = f"Launching document worker {i} (for regeneration/add docs)"
        print(start_msg, flush=True)
        logger.info(start_msg)
        
        # Create a unique worker name with timestamp and UUID
        worker_id = f"doc-{i}-{int(time.time())}-{str(uuid.uuid4())[:8]}"
        p = subprocess.Popen([
            "rq", "worker", "documents",
            "--url", redis_url,
            "--job-class", "rq.job.Job",
            "--worker-ttl", "10800",  # 3 hour worker TTL
            "--max-jobs", "1000",     # Keep worker running for many jobs
            "--with-scheduler",        # Enable job requeue on failure
            "--name", f"doc-worker-{worker_id}"
        ], env={
            **os.environ,
            "MAX_CONCURRENT_FIELDS": str(max_concurrent_fields),
            "WORKER_TYPE": "document",
            "WORKER_ID": f"doc-{i}",
            "RQ_WORKER_MAX_JOBS": "10",  # Restart worker after 10 jobs
            "RQ_WORKER_GRACEFUL_SHUTDOWN_TIMEOUT": "60"  # Give worker 60s to finish current job
        })
        procs.append(p)
    
    # Wait for any to exit; if one exits, keep waiting for the rest
    exit_code = 0
    try:
        while True:
            alive = False
            for p in procs:
                rc = p.poll()
                if rc is None:
                    alive = True
                elif rc != 0:
                    exit_code = rc
            if not alive:
                break
            time.sleep(1)
    finally:
        terminate_all()
    
    logger.info(f"All RQ workers exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
