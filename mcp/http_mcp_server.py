"""HTTP MCP server with domain allowlist and method restrictions."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("http-whitelist-mcp")


def _allowed_domains() -> List[str]:
    raw = os.getenv("HTTP_ALLOWED_DOMAINS", "api.render.com,api.github.com").strip()
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _allowed_methods() -> List[str]:
    raw = os.getenv("HTTP_ALLOWED_METHODS", "GET,POST").strip()
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _timeout_seconds() -> float:
    raw = os.getenv("HTTP_TIMEOUT_SECONDS", "20").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid HTTP_TIMEOUT_SECONDS: {raw}") from exc
    return max(1.0, min(value, 120.0))


def _validate_url(target_url: str) -> str:
    parsed = urlparse(target_url)
    if parsed.scheme not in {"https"}:
        raise RuntimeError("Only https URLs are allowed")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise RuntimeError("URL must include a hostname")

    if hostname not in _allowed_domains():
        raise RuntimeError(f"Domain not in whitelist: {hostname}")

    return target_url


def _validate_method(method: str) -> str:
    normalized = str(method or "").upper().strip()
    if normalized not in _allowed_methods():
        raise RuntimeError(f"Method not allowed: {normalized}")
    return normalized


@mcp.tool()
def http_allowed_config() -> Dict[str, Any]:
    return {
        "allowed_domains": _allowed_domains(),
        "allowed_methods": _allowed_methods(),
        "timeout_seconds": _timeout_seconds(),
    }


@mcp.tool()
def http_request(
    method: str,
    target_url: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    safe_method = _validate_method(method)
    safe_url = _validate_url(target_url)
    timeout = _timeout_seconds()

    req_headers = {str(k): str(v) for k, v in (headers or {}).items()}

    with httpx.Client(timeout=timeout) as client:
        response = client.request(
            safe_method,
            safe_url,
            headers=req_headers,
            json=json_body,
        )

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        parsed_body: Any = response.json()
    else:
        parsed_body = response.text

    return {
        "ok": 200 <= response.status_code < 300,
        "status_code": response.status_code,
        "url": str(response.url),
        "method": safe_method,
        "body": parsed_body,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
