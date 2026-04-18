# mcp/

This folder contains configuration and definitions for Model Context Protocol (MCP) tools and servers.

MCP tools are exposed to the n8n orchestrator so that AI agents can invoke them as part of automated flows.
Place tool manifests, server configurations, and related specifications here.

## n8n MCP Server

This repository now includes an MCP server for a Render-hosted n8n instance:

- [orchestrator/mcp/n8n_mcp_server.py](orchestrator/mcp/n8n_mcp_server.py)

It provides tools for observability and controlled operations via the n8n HTTP API.

### Available tools

- `n8n_health_check`
- `n8n_list_workflows`
- `n8n_get_workflow`
- `n8n_list_executions`
- `n8n_get_execution`
- `n8n_set_workflow_active` (write-protected)
- `n8n_trigger_webhook` (write-protected)
- `multiagent_create_run`
- `multiagent_get_run`
- `multiagent_list_runs`

### Security model

- Read-only by default (`N8N_MCP_ENABLE_WRITE=false`)
- Write tools are disabled unless explicitly enabled
- n8n API key is loaded from environment variables only
- Multiagent tools require `MULTIAGENT_API_BASE_URL`

### Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r orchestrator/mcp/requirements.txt
```

3. Copy env template and set real values:

- [orchestrator/config/n8n-mcp.env.example](orchestrator/config/n8n-mcp.env.example)

4. Run server:

```bash
python orchestrator/mcp/n8n_mcp_server.py
```

### One-command scripts (PowerShell)

Start MCP server using local env file:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File orchestrator/mcp/start-n8n-mcp.ps1
```

Run connectivity smoke test against n8n:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File orchestrator/mcp/test-n8n-mcp-connection.ps1
```

Sync and activate all starter workflows from `n8n/workflows`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File orchestrator/mcp/sync-n8n-workflows.ps1
```

Diagnose multiagent API connectivity used by workflows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File orchestrator/mcp/diagnose-multiagent-api.ps1
```

Validate end-to-end run tracking (`run_id`) across n8n and multiagent API:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File orchestrator/mcp/test-e2e-run-tracking.ps1
```

### MCP client example

Use this sample to register the server in an MCP-capable client:

- [orchestrator/mcp/n8n-mcp.client.example.json](orchestrator/mcp/n8n-mcp.client.example.json)

Replace placeholder values before use.
