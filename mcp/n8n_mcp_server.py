"""MCP server for operating a remote n8n instance via API.

This server is designed for Render-hosted n8n and exposes a small set of
safe, auditable tools for workflow operations and observability.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("n8n-render-mcp")


def _base_url() -> str:
    base = os.getenv("N8N_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("N8N_BASE_URL is required")
    return base


def _api_key() -> str:
    key = os.getenv("N8N_API_KEY", "").strip()
    if not key:
        raise RuntimeError("N8N_API_KEY is required")
    return key


def _timeout_seconds() -> float:
    raw = os.getenv("N8N_HTTP_TIMEOUT", "30").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 30.0
    return max(3.0, value)


def _multiagent_base_url() -> str:
    base = os.getenv("MULTIAGENT_API_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("MULTIAGENT_API_BASE_URL is required for multiagent tools")
    return base


def _write_enabled() -> bool:
    return os.getenv("N8N_MCP_ENABLE_WRITE", "false").lower() == "true"


def _headers() -> Dict[str, str]:
    return {
        "X-N8N-API-KEY": _api_key(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _response_payload(resp: httpx.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    return {
        "ok": resp.is_success,
        "status_code": resp.status_code,
        "data": data,
    }


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    use_api_key: bool = True,
) -> Dict[str, Any]:
    url = f"{_base_url()}/{path.lstrip('/')}"
    headers = _headers() if use_api_key else {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            resp = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
            )
        return _response_payload(resp)
    except Exception as exc:  # broad by design to return structured MCP errors
        return {
            "ok": False,
            "status_code": 0,
            "error": str(exc),
            "path": path,
        }


async def _request_multiagent(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = f"{_multiagent_base_url()}/{path.lstrip('/')}"

    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            resp = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
        return _response_payload(resp)
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "error": str(exc),
            "path": path,
        }


@mcp.tool()
async def n8n_health_check() -> Dict[str, Any]:
    """Check if n8n responds on the health endpoint."""
    return await _request("GET", "/healthz", use_api_key=False)


@mcp.tool()
async def n8n_list_workflows(limit: int = 50, active: Optional[bool] = None) -> Dict[str, Any]:
    """List workflows from n8n."""
    params: Dict[str, Any] = {"limit": max(1, min(limit, 250))}
    result = await _request("GET", "/api/v1/workflows", params=params)

    if result.get("ok") and active is not None:
        data = result.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            data["data"] = [w for w in data["data"] if w.get("active") is active]
    return result


@mcp.tool()
async def n8n_get_workflow(workflow_id: str) -> Dict[str, Any]:
    """Get one workflow by id."""
    return await _request("GET", f"/api/v1/workflows/{workflow_id}")


@mcp.tool()
async def n8n_list_executions(
    limit: int = 20,
    workflow_id: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List workflow executions with optional filters."""
    params: Dict[str, Any] = {"limit": max(1, min(limit, 250))}
    if workflow_id:
        params["workflowId"] = workflow_id
    if status:
        params["status"] = status

    return await _request("GET", "/api/v1/executions", params=params)


@mcp.tool()
async def n8n_get_execution(execution_id: str, include_data: bool = False) -> Dict[str, Any]:
    """Get details of one execution."""
    params = {"includeData": str(include_data).lower()}
    return await _request("GET", f"/api/v1/executions/{execution_id}", params=params)


@mcp.tool()
async def n8n_set_workflow_active(workflow_id: str, active: bool) -> Dict[str, Any]:
    """Activate or deactivate a workflow.

    Requires N8N_MCP_ENABLE_WRITE=true.
    """
    if not _write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Write operations are disabled. Set N8N_MCP_ENABLE_WRITE=true",
        }

    state_path = "activate" if active else "deactivate"
    return await _request(
        "POST",
        f"/api/v1/workflows/{workflow_id}/{state_path}",
    )


@mcp.tool()
async def n8n_trigger_webhook(
    webhook_path: str,
    payload: Optional[Dict[str, Any]] = None,
    method: str = "POST",
) -> Dict[str, Any]:
    """Trigger a public n8n webhook path, e.g. 'planner-entry'.

    This calls /webhook/<path> on N8N_BASE_URL.
    """
    if not _write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Write operations are disabled. Set N8N_MCP_ENABLE_WRITE=true",
        }

    safe_method = method.upper().strip()
    if safe_method not in {"POST", "GET"}:
        return {
            "ok": False,
            "status_code": 0,
            "error": "Unsupported method. Use GET or POST",
        }

    path = f"/webhook/{webhook_path.lstrip('/')}"
    return await _request(
        safe_method,
        path,
        json_body=payload or {},
        use_api_key=False,
    )


@mcp.tool()
async def multiagent_create_run() -> Dict[str, Any]:
    """Create a new run_id in the multiagent backend."""
    return await _request_multiagent("POST", "/runs")


@mcp.tool()
async def multiagent_get_run(run_id: str) -> Dict[str, Any]:
    """Get one run status from multiagent backend."""
    return await _request_multiagent("GET", f"/runs/{run_id}")


@mcp.tool()
async def multiagent_list_runs(limit: int = 20) -> Dict[str, Any]:
    """List recent runs from multiagent backend."""
    return await _request_multiagent("GET", "/runs", params={"limit": max(1, min(limit, 200))})


if __name__ == "__main__":
    mcp.run()
