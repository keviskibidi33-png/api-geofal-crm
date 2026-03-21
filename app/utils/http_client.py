from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

logger = logging.getLogger(__name__)

DEFAULT_HTTP_TIMEOUT = 20


def _sanitize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def http_request(
    method: str,
    url: str,
    *,
    timeout: int | float = DEFAULT_HTTP_TIMEOUT,
    request_name: str | None = None,
    **kwargs: Any,
) -> requests.Response:
    started_at = time.perf_counter()
    safe_url = _sanitize_url(url)
    label = request_name or safe_url

    try:
        response = requests.request(method, url, timeout=timeout, **kwargs)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "HTTP %s %s -> %s in %.1fms",
            method.upper(),
            label,
            response.status_code,
            elapsed_ms,
        )
        return response
    except requests.RequestException:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        logger.exception(
            "HTTP %s %s failed in %.1fms",
            method.upper(),
            label,
            elapsed_ms,
        )
        raise


def http_get(url: str, **kwargs: Any) -> requests.Response:
    return http_request("GET", url, **kwargs)


def http_post(url: str, **kwargs: Any) -> requests.Response:
    return http_request("POST", url, **kwargs)


def http_patch(url: str, **kwargs: Any) -> requests.Response:
    return http_request("PATCH", url, **kwargs)


def http_delete(url: str, **kwargs: Any) -> requests.Response:
    return http_request("DELETE", url, **kwargs)
