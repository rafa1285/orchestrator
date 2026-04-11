# orchestrator

An n8n-based orchestrator for coordinating AI agents and MCP (Model Context Protocol) flows.
It provides a structured workspace to define, configure, and document automation workflows
that connect AI tools with external services.

## Folder Structure

| Folder    | Purpose |
|-----------|---------|
| `flows/`  | n8n workflow definitions (JSON) that can be imported into an n8n instance. |
| `mcp/`    | MCP tool manifests and server configurations exposed to the orchestrator. |
| `docs/`   | Project documentation: architecture, setup guides, and usage examples. |
| `config/` | Environment and runtime configuration templates (no secrets). |
