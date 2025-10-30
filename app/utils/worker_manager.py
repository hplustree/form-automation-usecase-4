"""
Worker manager for hierarchical worker spawning.
This module provides utilities for spawning and managing child workers.
"""

import os
import subprocess
import signal
import time
from typing import List, Dict
from app.logging_config import logger


class WorkerManager:
    """Manages child worker processes in a hierarchical system."""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.child_processes: List[subprocess.Popen] = []
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._terminate_children)
        signal.signal(signal.SIGINT, self._terminate_children)
    
    def _terminate_children(self, signum=None, frame=None):
        """Terminate all child worker processes."""
        logger.info(f"Terminating {len(self.child_processes)} child workers...")
        for p in self.child_processes:
            try:
                if p.poll() is None:
                    p.terminate()
            except Exception as e:
                logger.error(f"Error terminating child process: {e}")
        
        # Give them time to exit cleanly
        time.sleep(2)
        
        # Force kill if still alive
        for p in self.child_processes:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception as e:
                logger.error(f"Error killing child process: {e}")
        
        self.child_processes.clear()
    
    def spawn_document_workers(
        self, 
        project_id: str, 
        num_workers: int,
        worker_id_prefix: str = ""
    ) -> List[subprocess.Popen]:
        """
        Spawn document workers for a specific project.
        
        Args:
            project_id: The project ID these workers will process
            num_workers: Number of document workers to spawn
            worker_id_prefix: Prefix for worker IDs (e.g., "p1" for project 1)
        
        Returns:
            List of spawned process objects
        """
        logger.info(f"Spawning {num_workers} document workers for project {project_id}")
        
        queue_name = f"documents:{project_id}"
        spawned = []
        
        for i in range(1, num_workers + 1):
            worker_name = f"{worker_id_prefix}-doc-worker-{i}"
            logger.info(f"Launching document worker: {worker_name} on queue {queue_name}")
            
            # Get field workers per doc from environment
            num_field_workers = int(os.getenv("NUM_FIELD_WORKERS_PER_DOC", "5"))
            
            p = subprocess.Popen([
                "rq", "worker", queue_name,
                "--url", self.redis_url,
                "--name", worker_name
            ], env={
                **os.environ,
                "WORKER_TYPE": "document",
                "WORKER_ID": worker_name,
                "PROJECT_ID": project_id,
                "NUM_FIELD_WORKERS_PER_DOC": str(num_field_workers)
            })
            spawned.append(p)
            self.child_processes.append(p)
        
        return spawned
    
    def spawn_field_workers(
        self,
        project_id: str,
        document_id: str,
        num_workers: int,
        worker_id_prefix: str = ""
    ) -> List[subprocess.Popen]:
        """
        Spawn field workers for a specific document.
        
        Args:
            project_id: The project ID
            document_id: The document ID these workers will process
            num_workers: Number of field workers to spawn
            worker_id_prefix: Prefix for worker IDs
        
        Returns:
            List of spawned process objects
        """
        logger.info(f"Spawning {num_workers} field workers for document {document_id}")
        
        queue_name = f"fields:{project_id}:{document_id}"
        spawned = []
        
        for i in range(1, num_workers + 1):
            worker_name = f"{worker_id_prefix}-field-worker-{i}"
            logger.info(f"Launching field worker: {worker_name} on queue {queue_name}")
            
            p = subprocess.Popen([
                "rq", "worker", queue_name,
                "--url", self.redis_url,
                "--name", worker_name
            ], env={
                **os.environ,
                "WORKER_TYPE": "field",
                "WORKER_ID": worker_name,
                "PROJECT_ID": project_id,
                "DOCUMENT_ID": document_id
            })
            spawned.append(p)
            self.child_processes.append(p)
        
        return spawned
    
    def wait_for_workers(self, workers: List[subprocess.Popen], timeout: int = None):
        """
        Wait for a list of workers to complete.
        
        Args:
            workers: List of worker processes to wait for
            timeout: Optional timeout in seconds
        """
        start_time = time.time()
        
        while True:
            all_done = True
            for p in workers:
                if p.poll() is None:
                    all_done = False
                    break
            
            if all_done:
                logger.info("All workers completed")
                break
            
            if timeout and (time.time() - start_time) > timeout:
                logger.warning(f"Timeout waiting for workers after {timeout}s")
                break
            
            time.sleep(1)
    
    def cleanup(self):
        """Clean up all child processes."""
        self._terminate_children()
