# Estado de backlog en Jira (SCRUM)

## 1. Estado actual validado

- Consulta Jira `project=SCRUM AND labels=mas-backlog-v2 AND statusCategory!=Done`: `count=0`
- `pm_plan_backlog(limit=20)`: `pending_total=0`, `ready_total=0`
- El backlog v2 queda cerrado de extremo a extremo en Jira, en el planner PM y en los repositorios empujados

## 2. Ultimo cierre consolidado

Durante el cierre final se completaron y validaron los bloques siguientes:
- WhatsApp: plantillas Meta, flujo Whisper y respuesta estructurada
- MCP especializado: filesystem, git, exec y http
- CI/CD y mapa de proyectos: project map central y creacion de repos GitHub
- agent-tools: logging y validators compartidos
- seguridad operativa: auth por API key en backend multiagent y propagacion de `X-API-Key` desde n8n/orchestrator

## 3. Como refrescar el estado live

```powershell
$envFile='c:\multiagent-system-suite\orchestrator\config\n8n-mcp.env'
Get-Content $envFile | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object {
  $k,$v = $_ -split '=',2
  [System.Environment]::SetEnvironmentVariable($k,$v,'Process')
}

$pair = '{0}:{1}' -f $env:JIRA_EMAIL, $env:JIRA_API_TOKEN
$auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))
$headers = @{ Authorization = "Basic $auth"; Accept = 'application/json' }
$jql = 'project=SCRUM AND labels=mas-backlog-v2 AND statusCategory!=Done ORDER BY created ASC'
$query = [uri]::EscapeDataString($jql)
$url = "$($env:JIRA_BASE_URL.TrimEnd('/'))/rest/api/3/search/jql?jql=$query&maxResults=200&fields=summary,status,labels"
Invoke-RestMethod -Uri $url -Headers $headers -Method GET -TimeoutSec 60
```

## 4. Politica para trabajo futuro

Si aparece trabajo nuevo:
- crear nuevas issues en Jira en lugar de reabrir el backlog cerrado sin criterio
- volver a ejecutar `pm_sync_backlog` y `pm_plan_backlog` solo sobre el nuevo catalogo
- actualizar `jira-backlog-live-status.json` con un nuevo snapshot despues del alta
