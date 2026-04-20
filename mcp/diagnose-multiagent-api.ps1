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

$base = [string]$env:MULTIAGENT_API_BASE_URL
$base = $base.TrimEnd('/')
$headers = @{}
if (-not [string]::IsNullOrWhiteSpace($env:MULTIAGENT_API_KEY)) {
    $headers['X-API-Key'] = $env:MULTIAGENT_API_KEY
}
if ([string]::IsNullOrWhiteSpace($base)) {
    [pscustomobject]@{
        ok = $false
        reason = 'MULTIAGENT_API_BASE_URL is not set in n8n-mcp.env'
    } | ConvertTo-Json -Depth 6
    exit 0
}

$tests = @(
    @{ name = 'health'; method = 'GET';  path = '/'; body = $null },
    @{ name = 'planner'; method = 'POST'; path = '/agents/planner'; body = @{ task = 'diag task from script' } },
    @{ name = 'developer'; method = 'POST'; path = '/agents/developer'; body = @{ plan = 'diag plan from script' } },
    @{ name = 'reviewer'; method = 'POST'; path = '/agents/reviewer'; body = @{ code = 'diag code from script' } },
    @{ name = 'deployer'; method = 'POST'; path = '/agents/deployer'; body = @{ review = 'diag review from script' } }
)

$result = [ordered]@{
    baseUrl = $base
    checks = @()
}

foreach ($t in $tests) {
    $url = "$base$($t.path)"
    try {
        if ($t.method -eq 'GET') {
            $resp = Invoke-WebRequest -Uri $url -Method GET -Headers $headers -TimeoutSec 40
        }
        else {
            $resp = Invoke-WebRequest -Uri $url -Method POST -Headers $headers -ContentType 'application/json' -Body ($t.body | ConvertTo-Json -Depth 20) -TimeoutSec 40
        }

        $sample = $resp.Content
        if ($sample.Length -gt 300) {
            $sample = $sample.Substring(0, 300) + '...'
        }

        $result.checks += [pscustomobject]@{
            name = $t.name
            url = $url
            ok = $true
            statusCode = $resp.StatusCode
            responseSample = $sample
        }
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }

        $result.checks += [pscustomobject]@{
            name = $t.name
            url = $url
            ok = $false
            statusCode = $statusCode
            error = $_.Exception.Message
        }
    }
}

$result | ConvertTo-Json -Depth 8
