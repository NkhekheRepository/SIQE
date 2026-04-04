"""
Bounded retry with exponential backoff.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


async def with_retry(coro_fn, max_retries=3, base_delay=0.1, name="operation"):
    for attempt in range(max_retries + 1):
        try:
            return await coro_fn()
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"{name} failed after {max_retries} retries: {e}")
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(f"{name} attempt {attempt + 1} failed, retrying in {delay:.2f}s: {e}")
            await asyncio.sleep(delay)
