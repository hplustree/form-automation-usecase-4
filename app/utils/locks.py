import fcntl, os, time
from contextlib import contextmanager

LOCK_PATH = "/tmp/libreoffice_convert.lock"
SLEEP_STEP_S = 5.0
# None => wait forever; or set e.g. "600" to give up after 10 min
LOCK_TIMEOUT_S = 120
LOCK_TIMEOUT_S = None if LOCK_TIMEOUT_S in (None, "", "None") else float(LOCK_TIMEOUT_S)

@contextmanager
def libreoffice_global_lock():
    """
    Blocks until the LibreOffice lock is available, then runs the critical section.
    Works across threads and processes on the same host/container.
    Lock is auto-released if the holding process dies.
    """
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    with open(LOCK_PATH, "w") as fh:
        waited = 0.0
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if LOCK_TIMEOUT_S is not None and waited >= LOCK_TIMEOUT_S:
                    raise TimeoutError(f"Timed out waiting for LibreOffice lock after {LOCK_TIMEOUT_S}s")
                time.sleep(SLEEP_STEP_S)
                waited += SLEEP_STEP_S
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
