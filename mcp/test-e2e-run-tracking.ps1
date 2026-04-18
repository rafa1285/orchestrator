$ErrorActionPreference = 'Stop'

$envFile = Join-Path $PSScriptRoot '..\config\n8n-mcp.env'

if (-not (Test-Path $envFile)) {
    throw "Missing env file: $envFile"
}

Get-Content $envFile |
    Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } |
    ForEach-Object {
        $k, $v = $_ -split '=', 2
        [System.Environment]::SetEnvironmentVariable($k, $v, 'Process')
    }

$n8nBase = $env:N8N_BASE_URL.TrimEnd('/')
$multiagentBase = $env:MULTIAGENT_API_BASE_URL.TrimEnd('/')

if (-not $n8nBase) {
    throw 'N8N_BASE_URL is required in env file'
}

if (-not $multiagentBase) {
    throw 'MULTIAGENT_API_BASE_URL is required in env file'
}

Write-Output "n8n: $n8nBase"
Write-Output "multiagent: $multiagentBase"

try {
    $health = Invoke-RestMethod -Uri "$multiagentBase/" -Method GET -TimeoutSec 60
    Write-Output ("multiagent health: {0}" -f ($health | ConvertTo-Json -Compress))
}
catch {
    throw "Multiagent health check failed: $($_.Exception.Message)"
}

try {
    $created = Invoke-RestMethod -Uri "$multiagentBase/runs" -Method POST -ContentType 'application/json' -Body '{}' -TimeoutSec 60
}
catch {
    throw "Cannot create run. Is latest backend deployed? Error: $($_.Exception.Message)"
}

$runId = [string]$created.run_id
if (-not $runId) {
    throw 'Run creation succeeded but run_id is empty'
}

Write-Output "run_id: $runId"

$bridgePayload = @{
    action = 'full_pipeline'
    task = 'E2E run tracking validation'
    run_id = $runId
} | ConvertTo-Json -Compress

try {
    $bridgeResp = Invoke-RestMethod -Uri "$n8nBase/webhook/mcp-bridge" -Method POST -Body $bridgePayload -ContentType 'application/json' -TimeoutSec 180
    Write-Output ("bridge response: {0}" -f ($bridgeResp | ConvertTo-Json -Depth 12 -Compress))
}
catch {
    throw "n8n bridge call failed: $($_.Exception.Message)"
}

try {
    $run = Invoke-RestMethod -Uri "$multiagentBase/runs/$runId" -Method GET -TimeoutSec 60
}
catch {
    throw "Failed to read run status for ${runId}: $($_.Exception.Message)"
}

$summary = [pscustomobject]@{
    run_id = $run.run_id
    status = $run.status
    current_stage = $run.current_stage
    known_stages = @($run.stages.PSObject.Properties.Name)
    events = @($run.events).Count
}

Write-Output ("run summary: {0}" -f ($summary | ConvertTo-Json -Compress))

if (-not $run.stages.planner) {
    throw 'Planner stage not found in run state. Propagation is not working yet.'
}

Write-Output 'E2E run tracking validation passed.'
