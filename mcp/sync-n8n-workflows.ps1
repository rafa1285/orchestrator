$ErrorActionPreference = 'Stop'

$envFile = Join-Path $PSScriptRoot '..\config\n8n-mcp.env'
$workflowsDir = Join-Path $PSScriptRoot '..\..\n8n\workflows'

if (-not (Test-Path $envFile)) {
    throw "Missing env file: $envFile"
}

if (-not (Test-Path $workflowsDir)) {
    throw "Missing workflows directory: $workflowsDir"
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
    'Content-Type' = 'application/json'
}

$targetFiles = @(
    'whatsapp.json',
    'planner.json',
    'developer.json',
    'mcp.json',
    'jira-task-manager.json'
)

$listResp = Invoke-RestMethod -Uri "$base/api/v1/workflows?limit=250" -Method GET -Headers $headers
$existing = @{}
if ($listResp.data) {
    foreach ($wf in $listResp.data) {
        $existing[$wf.name] = $wf
    }
}

$result = @()

foreach ($fileName in $targetFiles) {
    $path = Join-Path $workflowsDir $fileName
    if (-not (Test-Path $path)) {
        $result += [pscustomobject]@{
            file = $fileName
            status = 'missing_file'
            workflowId = $null
            active = $false
        }
        continue
    }

    $wf = Get-Content -Raw $path | ConvertFrom-Json
    $name = [string]$wf.name

    if (-not $name) {
        $result += [pscustomobject]@{
            file = $fileName
            status = 'invalid_workflow_name'
            workflowId = $null
            active = $false
        }
        continue
    }

    $workflowId = $null
    $status = 'created'

    $upsertPayload = @{
        name = $wf.name
        nodes = $wf.nodes
        connections = $wf.connections
        settings = $wf.settings
    } | ConvertTo-Json -Depth 100

    if ($existing.ContainsKey($name)) {
        $workflowId = $existing[$name].id
        Invoke-RestMethod -Uri "$base/api/v1/workflows/$workflowId" -Method PUT -Headers $headers -Body $upsertPayload | Out-Null
        $status = 'updated'
    }
    else {
        $created = Invoke-RestMethod -Uri "$base/api/v1/workflows" -Method POST -Headers $headers -Body $upsertPayload
        $workflowId = $created.id
        $existing[$name] = [pscustomobject]@{ id = $workflowId; name = $name; active = $false }
    }

    $active = $false
    try {
        Invoke-RestMethod -Uri "$base/api/v1/workflows/$workflowId/activate" -Method POST -Headers $headers | Out-Null
        $active = $true
    }
    catch {
        $status = "$status;activate_failed"
    }

    $result += [pscustomobject]@{
        file = $fileName
        status = $status
        workflowId = $workflowId
        active = $active
    }
}

$result | ConvertTo-Json -Depth 6
