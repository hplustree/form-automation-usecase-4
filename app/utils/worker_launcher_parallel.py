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
from app.logging_config import logger


def main():
    # New parallel processing architecture with ThreadPoolExecutor
    try:
        num_project_workers = int(os.getenv("NUM_PROJECT_WORKERS", "1"))
        max_concurrent_docs = int(os.getenv("MAX_CONCURRENT_DOCS", "2"))
        max_concurrent_fields = int(os.getenv("MAX_CONCURRENT_FIELDS", "5"))
    except ValueError:
        num_project_workers = 1
        max_concurrent_docs = 2
        max_concurrent_fields = 5
    
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
    
    # Launch project workers that handle ThreadPoolExecutor internally
    for i in range(1, num_project_workers + 1):
        start_msg = f"Launching project worker {i} (parallel processing mode)"
        print(start_msg, flush=True)
        logger.info(start_msg)
        
        # Each project worker will handle projects sequentially,
        # but process documents and fields in parallel using ThreadPoolExecutor
        p = subprocess.Popen([
            "rq", "worker", "projects",
            "--url", redis_url,
            "--name", f"project-worker-{i}",
            "--with-scheduler"
        ], env={
            **os.environ,
            "MAX_CONCURRENT_DOCS": str(max_concurrent_docs),
            "MAX_CONCURRENT_FIELDS": str(max_concurrent_fields),
            "WORKER_TYPE": "project",
            "WORKER_ID": str(i)
        })
        procs.append(p)
    
    # Also launch document workers for individual document processing
    # (used by regeneration and add documents endpoints)
    num_doc_workers = int(os.getenv("NUM_DOCUMENT_WORKERS", "2"))
    for i in range(1, num_doc_workers + 1):
        start_msg = f"Launching document worker {i} (for regeneration/add docs)"
        print(start_msg, flush=True)
        logger.info(start_msg)
        
        p = subprocess.Popen([
            "rq", "worker", "documents",
            "--url", redis_url,
            "--name", f"document-worker-{i}"
        ], env={
            **os.environ,
            "MAX_CONCURRENT_FIELDS": str(max_concurrent_fields),
            "WORKER_TYPE": "document",
            "WORKER_ID": f"doc-{i}"
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
