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
    try:
        # Configuration for different worker types
        num_doc_workers = int(os.getenv("NUM_DOC_WORKERS", "3"))
        num_field_workers = int(os.getenv("NUM_FIELD_WORKERS", "5"))
        num_project_workers = int(os.getenv("NUM_PROJECT_WORKERS", "1"))
    except ValueError:
        num_doc_workers = 3
        num_field_workers = 5
        num_project_workers = 1
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    msg = f"Starting parallel workers: {num_doc_workers} document, {num_field_workers} field, {num_project_workers} project workers"
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
    
    # Launch document processing workers
    for i in range(1, num_doc_workers + 1):
        start_msg = f"Launching document worker {i}"
        print(start_msg, flush=True)
        logger.info(start_msg)
        p = subprocess.Popen([
            "rq", "worker", "documents",
            "--url", redis_url,
            "--name", f"doc-worker-{i}"
        ])
        procs.append(p)
    
    # Launch field extraction workers
    for i in range(1, num_field_workers + 1):
        start_msg = f"Launching field worker {i}"
        print(start_msg, flush=True)
        logger.info(start_msg)
        p = subprocess.Popen([
            "rq", "worker", "fields",
            "--url", redis_url,
            "--name", f"field-worker-{i}"
        ])
        procs.append(p)
    
    # Launch project coordination workers
    for i in range(1, num_project_workers + 1):
        start_msg = f"Launching project worker {i}"
        print(start_msg, flush=True)
        logger.info(start_msg)
        p = subprocess.Popen([
            "rq", "worker", "projects",
            "--url", redis_url,
            "--name", f"project-worker-{i}",
            "--with-scheduler"
        ])
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
