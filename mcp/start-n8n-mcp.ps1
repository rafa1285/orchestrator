$ErrorActionPreference = 'Stop'

$envFile = Join-Path $PSScriptRoot '..\config\n8n-mcp.env'
$pythonExe = Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'
$serverFile = Join-Path $PSScriptRoot 'n8n_mcp_server.py'

if (-not (Test-Path $envFile)) {
    throw "Missing env file: $envFile"
}

if (-not (Test-Path $pythonExe)) {
    throw "Missing Python executable: $pythonExe"
}

if (-not (Test-Path $serverFile)) {
    throw "Missing MCP server file: $serverFile"
}

Get-Content $envFile |
    Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } |
    ForEach-Object {
        $k, $v = $_ -split '=', 2
        [System.Environment]::SetEnvironmentVariable($k, $v, 'Process')
    }

Write-Host "Starting n8n MCP server..."
& $pythonExe $serverFile
