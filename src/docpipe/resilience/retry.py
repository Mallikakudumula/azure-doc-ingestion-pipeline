"""Retry with exponential backoff + jitter, only for TRANSIENT errors."""
import functools
import logging
import random
import time

from ..models import TransientError

log = logging.getLogger(__name__)


def retry(max_attempts: int = 3, base_delay: float = 1.0, sleep=time.sleep):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except TransientError as exc:
                    if attempt == max_attempts:
                        raise
                    delay = base_delay * 2 ** (attempt - 1) + random.uniform(0, 0.3)
                    log.warning("Transient error (%s). Attempt %d/%d, retrying in %.1fs",
                                exc, attempt, max_attempts, delay)
                    sleep(delay)
        return wrapper
    return decorator
