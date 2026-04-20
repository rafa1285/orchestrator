# mcp/

This folder contains configuration and definitions for Model Context Protocol (MCP) tools and servers.

MCP tools are exposed to the n8n orchestrator so that AI agents can invoke them as part of automated flows.
Place tool manifests, server configurations, and related specifications here.

## n8n MCP Server

This repository now includes an MCP server for a Render-hosted n8n instance:

- [orchestrator/mcp/n8n_mcp_server.py](orchestrator/mcp/n8n_mcp_server.py)

It provides tools for observability and controlled operations via the n8n HTTP API.

### Filesystem sandbox MCP server

This folder also includes a dedicated filesystem MCP server with per-project sandboxing:

- [orchestrator/mcp/filesystem_mcp_server.py](orchestrator/mcp/filesystem_mcp_server.py)

Required env var:

- `ALLOWED_PROJECTS`: semicolon-separated `name=absolute_path` pairs.

Example:

```text
ALLOWED_PROJECTS=orchestrator=C:/multiagent-system-suite/orchestrator;n8n=C:/multiagent-system-suite/n8n
```

Exposed tools:

- `fs_list_projects`
- `fs_list_dir`
- `fs_read_text`
- `fs_write_text`

### Git minimal-permissions MCP server

Dedicated Git MCP server with explicit command allowlist and read-only mode by default:

- [orchestrator/mcp/git_mcp_server.py](orchestrator/mcp/git_mcp_server.py)

Required env vars:

- `GIT_REPO_ROOT`: absolute path to the git repository.
- `GIT_ALLOWED_COMMANDS`: comma-separated allowlist of git subcommands.
- `GIT_READ_ONLY`: `true` by default, blocks mutating commands.

Exposed tools:

- `git_status_short`
- `git_log_oneline`
- `git_diff`
- `git_show`

### Exec whitelist MCP server

Isolated command execution server with explicit command allowlist and shell token blocking:

- [orchestrator/mcp/exec_mcp_server.py](orchestrator/mcp/exec_mcp_server.py)

Required env vars:

- `EXEC_WORKDIR`: absolute working directory.
- `EXEC_ALLOWED_COMMANDS`: comma-separated command whitelist.

Exposed tools:

- `exec_allowed_commands`
- `exec_run`

### HTTP whitelist MCP server

Domain-restricted HTTP MCP server with strict method allowlist:

- [orchestrator/mcp/http_mcp_server.py](orchestrator/mcp/http_mcp_server.py)

Required env vars:

- `HTTP_ALLOWED_DOMAINS`: comma-separated allowlist of hostnames.
- `HTTP_ALLOWED_METHODS`: comma-separated allowed methods (`GET,POST` recommended).
- `HTTP_TIMEOUT_SECONDS`: bounded request timeout.

Exposed tools:

- `http_allowed_config`
- `http_request`

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
- `jira_health_check`
- `jira_create_issue` (write-protected)
- `jira_list_issues`
- `jira_add_comment` (write-protected)
- `jira_transition_issue` (write-protected)
- `jira_link_run` (write-protected)
- `pm_sync_backlog` (write-protected)
- `pm_plan_backlog`
- `pm_execute_backlog` (write-protected)
- `pm_find_backlog_duplicates`
- `pm_cleanup_backlog_duplicates` (write-protected when apply_changes=true)

### Security model

- Read-only by default (`N8N_MCP_ENABLE_WRITE=false`)
- Write tools are disabled unless explicitly enabled
- n8n API key is loaded from environment variables only
- Multiagent tools require `MULTIAGENT_API_BASE_URL`
- Jira write tools require `JIRA_MCP_ENABLE_WRITE=true`

### Jira setup

Set these environment variables in your local env file:

- `JIRA_BASE_URL` (for example `https://your-company.atlassian.net`)
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`
- `JIRA_PROJECT_KEY` (default project when creating/listing issues)
- `JIRA_MCP_ENABLE_WRITE` (`true` to allow create/transition/comment/link)

### PM agent workflow

The MCP server includes a project-manager agent layer for Jira backlog control:

- `pm_sync_backlog`: creates missing epics/tasks from the technical catalog
- `pm_plan_backlog`: returns next executable tasks by priority/dependencies
- `pm_execute_backlog`: runs PM cycle (`En curso` -> evidence/tests -> `Listo`)

Recommended sequence:

1. `pm_sync_backlog`
2. `pm_plan_backlog`
3. `pm_execute_backlog` (start with `dry_run=true`)

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

Create Jira task + run full pipeline + auto-link `run_id` in one command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File orchestrator/mcp/run-full-pipeline-with-jira.ps1 -Task "Build booking CRUD API"
```

### MCP client example

Use this sample to register the server in an MCP-capable client:

- [orchestrator/mcp/n8n-mcp.client.example.json](orchestrator/mcp/n8n-mcp.client.example.json)

Replace placeholder values before use.
