"""
Hierarchical worker launcher for document and field processing.
This launcher implements a hierarchical worker allocation system where:
- Each project worker spawns dedicated document workers
- Each document worker spawns dedicated field workers
- Workers only process tasks assigned to their parent

Configuration:
- NUM_DOC_WORKERS_PER_PROJECT: Number of document workers per project worker (default: 2)
- NUM_FIELD_WORKERS_PER_DOC: Number of field workers per document worker (default: 5)
- NUM_PROJECT_WORKERS: Number of project workers (default: 1)
"""

import os
import sys
import time
import signal
import subprocess
from app.logging_config import logger


def main():
    try:
        # Configuration for hierarchical worker allocation
        num_project_workers = int(os.getenv("NUM_PROJECT_WORKERS", "1"))
        num_doc_workers_per_project = int(os.getenv("NUM_DOC_WORKERS_PER_PROJECT", "2"))
        num_field_workers_per_doc = int(os.getenv("NUM_FIELD_WORKERS_PER_DOC", "2"))
    except ValueError:
        num_project_workers = 1
        num_doc_workers_per_project = 2
        num_field_workers_per_doc = 2
    
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    msg = (f"Starting hierarchical workers: {num_project_workers} project workers, "
           f"{num_doc_workers_per_project} doc workers per project, "
           f"{num_field_workers_per_doc} field workers per doc")
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
    
    # Launch project coordination workers
    # These workers will spawn their own document workers dynamically
    for i in range(1, num_project_workers + 1):
        start_msg = f"Launching project worker {i}"
        print(start_msg, flush=True)
        logger.info(start_msg)
        p = subprocess.Popen([
            "rq", "worker", "projects",
            "--url", redis_url,
            "--name", f"project-worker-{i}",
            "--with-scheduler"
        ], env={
            **os.environ,
            "NUM_DOC_WORKERS_PER_PROJECT": str(num_doc_workers_per_project),
            "NUM_FIELD_WORKERS_PER_DOC": str(num_field_workers_per_doc),
            "WORKER_TYPE": "project",
            "WORKER_ID": str(i)
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
