param(
    [Parameter(Mandatory = $true)]
    [string]$TaskText,

    [string]$Summary = "",
    [string]$Description = ""
)

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

$requiredVars = @(
    'N8N_BASE_URL',
    'JIRA_BASE_URL',
    'JIRA_EMAIL',
    'JIRA_API_TOKEN',
    'JIRA_PROJECT_KEY'
)

foreach ($name in $requiredVars) {
    $value = [System.Environment]::GetEnvironmentVariable($name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Missing required environment variable in n8n-mcp.env: $name"
    }
}

if ([string]::IsNullOrWhiteSpace($Summary)) {
    if ($TaskText.Length -gt 80) {
        $Summary = $TaskText.Substring(0, 80)
    }
    else {
        $Summary = $TaskText
    }
}

if ([string]::IsNullOrWhiteSpace($Description)) {
    $Description = "Created from one-command pipeline launcher. Task: $TaskText"
}

function Convert-ToJiraDoc {
    param([string]$Text)

    return @{
        type = 'doc'
        version = 1
        content = @(
            @{
                type = 'paragraph'
                content = @(
                    @{
                        type = 'text'
                        text = $Text
                    }
                )
            }
        )
    }
}

$jiraPair = "$($env:JIRA_EMAIL):$($env:JIRA_API_TOKEN)"
$jiraAuth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($jiraPair))
$jiraHeaders = @{
    Authorization = "Basic $jiraAuth"
    Accept = 'application/json'
    'Content-Type' = 'application/json'
}

$createIssueBody = @{
    fields = @{
        project = @{ key = $env:JIRA_PROJECT_KEY }
        summary = $Summary
        description = Convert-ToJiraDoc -Text $Description
        issuetype = @{ name = 'Task' }
    }
} | ConvertTo-Json -Depth 20

$jiraIssueUrl = "$($env:JIRA_BASE_URL.TrimEnd('/'))/rest/api/3/issue"
$issueResp = Invoke-RestMethod -Uri $jiraIssueUrl -Method POST -Headers $jiraHeaders -Body $createIssueBody
$issueKey = [string]$issueResp.key

if ([string]::IsNullOrWhiteSpace($issueKey)) {
    throw 'Jira issue creation succeeded but no issue key was returned.'
}

$n8nWebhookUrl = "$($env:N8N_BASE_URL.TrimEnd('/'))/webhook/whatsapp-intake"
$pipelineBody = @{
    text = $TaskText
    jira_issue_key = $issueKey
    jira_base_url = $env:JIRA_BASE_URL
    jira_email = $env:JIRA_EMAIL
    jira_api_token = $env:JIRA_API_TOKEN
} | ConvertTo-Json -Depth 20

$pipelineRaw = Invoke-WebRequest -Uri $n8nWebhookUrl -Method POST -ContentType 'application/json' -Body $pipelineBody -UseBasicParsing -TimeoutSec 300
$pipelineJson = $null
if (-not [string]::IsNullOrWhiteSpace($pipelineRaw.Content)) {
    $pipelineJson = $pipelineRaw.Content | ConvertFrom-Json
}

$result = [pscustomobject]@{
    ok = $true
    issue_key = $issueKey
    jira_issue_url = "$($env:JIRA_BASE_URL.TrimEnd('/'))/browse/$issueKey"
    pipeline_status_code = [int]$pipelineRaw.StatusCode
    run_id = if ($pipelineJson) { $pipelineJson.run_id } else { $null }
    pipeline_status = if ($pipelineJson) { $pipelineJson.status } else { $null }
    jira_link_status = if ($pipelineJson -and $pipelineJson.jira_link) { $pipelineJson.jira_link.status } else { $null }
    raw_pipeline_response = if ($pipelineJson) { $pipelineJson } else { $pipelineRaw.Content }
}

$result | ConvertTo-Json -Depth 30
