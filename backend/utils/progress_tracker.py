import threading
import uuid

_jobs: dict = {}
_lock = threading.Lock()


def create_job(job_id: str, **kwargs) -> None:
    with _lock:
        _jobs[job_id] = dict(kwargs)


def update_job(job_id: str, **kwargs) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def get_job(job_id: str) -> dict:
    with _lock:
        return dict(_jobs.get(job_id) or {})


def generate_job_id() -> str:
    return str(uuid.uuid4())
