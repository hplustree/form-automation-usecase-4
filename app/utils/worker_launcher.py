import os
import sys
import time
import signal
import subprocess
from app.logging_config import logger


def main():
    try:
        num_workers = int(os.getenv("NUM_WORKERS", "2"))
    except ValueError:
        num_workers = 2
    queue_name = os.getenv("QUEUE_NAME", "projects")
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

    msg = f"Starting {num_workers} RQ workers for queue {queue_name} (REDIS_URL={redis_url})"
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

    # Launch N workers
    for i in range(1, num_workers + 1):
        start_msg = f"Launching worker {i} (queue={queue_name})"
        print(start_msg, flush=True)
        logger.info(start_msg)
        p = subprocess.Popen([
            "rq", "worker", queue_name,
            "--url", redis_url,
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
