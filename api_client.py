import logging
import httpx
from typing import Optional

from config import config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = float(config.get("api_timeout_sec", 5))
DEFAULT_RETRIES = int(config.get("api_retries", 3))
DEFAULT_BACKOFF = float(config.get("api_backoff_sec", 0.6))

# Global async client (singleton pattern for connection pooling)
_CLIENT: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    """Get or create the global async HTTP client."""
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        transport = httpx.AsyncHTTPTransport(
            retries=DEFAULT_RETRIES,
        )
        _CLIENT = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(DEFAULT_TIMEOUT),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=20),
            http2=True,  # Enable HTTP/2 for better performance
        )
    return _CLIENT


async def request(method: str, url: str, **kwargs):
    """
    Async HTTP request with automatic retries.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL
        **kwargs: Additional arguments passed to httpx
        
    Returns:
        httpx.Response object
    """
    client = _get_client()
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    
    # Retry logic with exponential backoff
    last_exception = None
    for attempt in range(DEFAULT_RETRIES):
        try:
            response = await client.request(
                method,
                url,
                timeout=timeout,
                **kwargs
            )
            # Retry on specific status codes
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt < DEFAULT_RETRIES - 1:
                    import asyncio
                    await asyncio.sleep(DEFAULT_BACKOFF * (2 ** attempt))
                    continue
            return response
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as e:
            last_exception = e
            if attempt < DEFAULT_RETRIES - 1:
                import asyncio
                await asyncio.sleep(DEFAULT_BACKOFF * (2 ** attempt))
                logger.warning(f"Request failed (attempt {attempt + 1}/{DEFAULT_RETRIES}): {e}")
            else:
                logger.error(f"Request failed after {DEFAULT_RETRIES} attempts: {e}")
                raise
    
    if last_exception:
        raise last_exception


async def get(url: str, **kwargs):
    """Async GET request."""
    return await request("GET", url, **kwargs)


async def post(url: str, **kwargs):
    """Async POST request."""
    return await request("POST", url, **kwargs)


async def close_client():
    """Close the global HTTP client. Call this on shutdown."""
    global _CLIENT
    if _CLIENT is not None and not _CLIENT.is_closed:
        await _CLIENT.aclose()
        _CLIENT = None
