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

$base = $env:N8N_BASE_URL.TrimEnd('/')
$headers = @{
    'X-N8N-API-KEY' = $env:N8N_API_KEY
    'Accept' = 'application/json'
}

$result = [ordered]@{}

try {
    $health = Invoke-WebRequest -Uri "$base/healthz" -Method GET -TimeoutSec 30
    $result.healthz_status = $health.StatusCode
} catch {
    $result.healthz_error = $_.Exception.Message
}

try {
    $wf = Invoke-WebRequest -Uri "$base/api/v1/workflows?limit=3" -Method GET -Headers $headers -TimeoutSec 30
    $wfJson = $wf.Content | ConvertFrom-Json
    $result.workflows_status = $wf.StatusCode
    if ($wfJson.data) {
        $result.workflows_count = @($wfJson.data).Count
        $result.workflows_sample = @($wfJson.data | Select-Object -First 3 -Property id, name, active)
    }
} catch {
    $result.workflows_error = $_.Exception.Message
}

try {
    $exec = Invoke-WebRequest -Uri "$base/api/v1/executions?limit=3" -Method GET -Headers $headers -TimeoutSec 30
    $execJson = $exec.Content | ConvertFrom-Json
    $result.executions_status = $exec.StatusCode
    if ($execJson.data) {
        $result.executions_count = @($execJson.data).Count
    }
} catch {
    $result.executions_error = $_.Exception.Message
}

$result | ConvertTo-Json -Depth 6
