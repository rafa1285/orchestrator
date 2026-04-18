# config/

This folder contains environment and runtime configuration files.

Store non-sensitive defaults, environment variable templates (e.g. `.env.example`),
and any settings required to run the n8n orchestrator and its connected services.
Do NOT commit secrets or credentials here.

## Included templates

- [orchestrator/config/n8n-mcp.env.example](orchestrator/config/n8n-mcp.env.example):
	environment variables for the MCP server that connects to Render-hosted n8n.
