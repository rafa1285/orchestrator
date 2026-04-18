$ErrorActionPreference = 'Stop'

$envFile = Join-Path $PSScriptRoot '..\config\n8n-mcp.env'
$pythonExe = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'

if (-not (Test-Path $envFile)) {
    throw "Missing env file: $envFile"
}

if (-not (Test-Path $pythonExe)) {
    throw "Missing Python executable: $pythonExe"
}

Get-Content $envFile |
    Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } |
    ForEach-Object {
        $k, $v = $_ -split '=', 2
        [System.Environment]::SetEnvironmentVariable($k, $v, 'Process')
    }

# Controlled write enable only for this process.
$env:N8N_MCP_ENABLE_WRITE = 'true'

$pyCode = @"
import asyncio
import json
import sys

sys.path.insert(0, r'c:/multiagent-system-suite/orchestrator/mcp')
import n8n_mcp_server as srv

async def main():
    result = await srv.n8n_trigger_webhook(
        webhook_path='planner-entry',
        payload={'task': 'MCP write smoke test'},
        method='POST',
    )
    print(json.dumps(result, ensure_ascii=False))

asyncio.run(main())
"@

& $pythonExe -c $pyCode
