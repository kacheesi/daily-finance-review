"""重试装饰器：网络错误 / HTTP 5xx / 超时 指数退避重试"""
import functools
import logging
import time

logger = logging.getLogger("daily_review.retry")


def retry(retries: int = 3, backoff: tuple = (1, 2, 4), exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_err = e
                    if attempt < retries:
                        wait = backoff[min(attempt - 1, len(backoff) - 1)]
                        logger.warning("%s 第%d次失败(%s)，%.1fs后重试", func.__name__, attempt, e, wait)
                        time.sleep(wait)
            raise last_err
        return wrapper
    return decorator
