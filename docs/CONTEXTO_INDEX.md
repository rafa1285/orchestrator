# Indice de contexto del workspace — Sistema Multiagente

> Actualizado a 2026-04-20.
> Punto de entrada recomendado para revisar estado tecnico y operativo.

---

## 1. Documentos de arquitectura y estado

| Documento | Contenido |
|---|---|
| `ARQUITECTURA_DEFINITIVA_v2.md` | Arquitectura vigente y flujo operativo real |
| `WORKSPACE_CONTEXTO_ACTUAL.md` | Estado resumido por repositorio |
| `JIRA_BACKLOG_ESTADO.md` | Resumen actual del backlog y del planner PM |
| `jira-backlog-live-status.json` | Snapshot validado del estado Jira/PM |
| `PM_AGENT_RUNBOOK.md` | Ejecucion operativa del agente PM autonomo |

---

## 2. Mapa de repositorios

| Repo | Ruta local | Hosting | Estado |
|---|---|---|---|
| multiagent-system | `multiagent-system-suite\multiagent-system` | https://multiagent-system-4eze.onrender.com | Operativo con auth por API key y provider Ollama-compatible |
| orchestrator | `multiagent-system-suite\orchestrator` | local (control) | Operativo con scripts PM, Jira y validacion E2E |
| n8n workflows | `multiagent-system-suite\n8n` | sincronizados a n8n | Activos con Jira manager y forwarding de `X-API-Key` |
| agent-tools | `multiagent-system-suite\agent-tools` | libreria | Logging y validators implementados |
| backend-template | `multiagent-system-suite\backend-template` | referencia | Plantilla base |

---

## 3. Componentes tecnicos clave

### multiagent-system
- FastAPI Python 3.12 en Render
- Endpoints de agentes y de run-state protegidos por `MULTIAGENT_API_KEY` cuando se configura
- Provider open-source ya integrado contra API Ollama-compatible
- Shim local para pruebas en `dev/fake_ollama_server.py`

### orchestrator/mcp/n8n_mcp_server.py
- Servidor MCP FastMCP con tools para n8n, multiagent, Jira y PM backlog
- Validadores de cierre implementados para el backlog ampliado ya ejecutado
- `pm_autonomous_loop.py` y scripts operativos listos para nuevas tandas de trabajo

### n8n workflows activos
- `whatsapp.json`: pipeline principal con respuesta estructurada y soporte Jira
- `mcp.json`: bridge MCP con forwarding de contexto Jira
- `jira-task-manager.json`: create/list/comment/transition/link_run
- `whatsapp-message-templates.json` y `whisper-transcription.json`: soporte WhatsApp completado

### infra-n8n-render
- Dockerfile + render.yaml para n8n en Render Starter
- Auto-deploy en push a main
- N8N_BASIC_AUTH activo

---

## 4. Estado Jira y PM

- Consulta Jira `mas-backlog-v2` sin issues abiertas: `count=0`
- `pm_plan_backlog(limit=20)` devuelve `pending_total=0` y `ready_total=0`
- El backlog ampliado ya fue ejecutado, validado, cerrado y empujado a los repositorios principales

---

## 6. Variables de entorno por servicio

### multiagent-system (Render)
```
LLM_PROVIDER=open_source
LLM_MODEL=mistral
LLM_BASE_URL=http://localhost:11434
DATABASE_URL=<postgresql connection string>
RUN_STAGE_MAX_ATTEMPTS=3
MULTIAGENT_API_KEY=<shared-api-key>
```

### n8n (Render)
```
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=<generado>
N8N_HOST=<render host>
N8N_PORT=5678
N8N_PROTOCOL=https
```

### orchestrator MCP (local — config/n8n-mcp.env — NO commitear)
```
N8N_BASE_URL=
N8N_API_KEY=
MULTIAGENT_API_BASE_URL=
MULTIAGENT_API_KEY=
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=
JIRA_PROJECT_KEY=SCRUM
N8N_MCP_ENABLE_WRITE=true
JIRA_MCP_ENABLE_WRITE=true
```

---

## 7. Comandos operativos rapidos

```powershell
# Setup de entorno
$envFile='c:\multiagent-system-suite\orchestrator\config\n8n-mcp.env'
Get-Content $envFile | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } |
  ForEach-Object { $k,$v = $_ -split '=',2; [System.Environment]::SetEnvironmentVariable($k,$v,'Process') }

# Loop PM autonomo
[System.Environment]::SetEnvironmentVariable('JIRA_MCP_ENABLE_WRITE','true','Process')
c:/multiagent-system-suite/orchestrator/.venv/Scripts/python.exe `
  'c:\multiagent-system-suite\orchestrator\mcp\pm_autonomous_loop.py'

# Sync workflows
.\mcp\sync-n8n-workflows.ps1

# Pipeline + Jira one-command
.\mcp\run-full-pipeline-with-jira.ps1

# Diagnostico
.\mcp\diagnose-multiagent-api.ps1
```

---

## 8. Riesgos a seguir vigilando

- rotacion de credenciales usadas en pruebas
- reduccion adicional de credenciales Jira en payloads
- suite de tests y regresion mas completa
- observabilidad y resiliencia por etapa
