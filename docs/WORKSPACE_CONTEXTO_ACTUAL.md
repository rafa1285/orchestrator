# Contexto actual del workspace

## 1. Alcance analizado
Workspace multi-root:
- multiagent-system
- orchestrator
- n8n
- backend-template
- agent-tools

Este snapshot se centra en los componentes que hoy sostienen la arquitectura operativa: multiagent-system, orchestrator y n8n.

## 2. Estado por repositorio

### 2.1 multiagent-system
Estado: operativo, desplegado y endurecido.

Capacidades confirmadas:
- endpoints de agentes: planner, developer, reviewer, deployer
- endpoints de run state: create/get/list
- persistencia de run state en DB (con fallback local)
- idempotencia por etapa basada en hash de input
- control de intentos maximos por etapa
- auth por API key mediante `MULTIAGENT_API_KEY`
- provider open-source integrado contra endpoint Ollama-compatible

Archivos clave:
- main.py
- core/run_state.py
- core/config.py
- core/auth.py
- agents/*/router.py
- providers/open_source.py

### 2.2 orchestrator
Estado: operativo para control, validacion y cierre autonomo.

Capacidades confirmadas:
- servidor MCP con herramientas n8n, multiagent y Jira
- scripts de arranque, test y sync de workflows
- script one-command para crear issue Jira y ejecutar pipeline
- loop autonomo para PM backlog
- scripts E2E y diagnostico conscientes de `X-API-Key`

Archivos clave:
- mcp/n8n_mcp_server.py
- mcp/sync-n8n-workflows.ps1
- mcp/run-full-pipeline-with-jira.ps1
- config/n8n-mcp.env

### 2.3 n8n
Estado: workflows operativos, sincronizados y alineados con auth de backend.

Capacidades confirmadas:
- pipeline principal planner->developer->reviewer->deployer
- bridge mcp-bridge para acciones planner/full_pipeline/ping
- jira-task-manager con acciones create/list/comment/transition/link_run
- auto-link run_id a Jira en pipeline full
- forwarding de `X-API-Key` hacia el backend multiagent
- soporte de plantillas Meta y Whisper en workflows dedicados

Archivos clave:
- workflows/whatsapp.json
- workflows/mcp.json
- workflows/jira-task-manager.json
- workflows/planner.json
- workflows/developer.json

## 3. Lo que ya esta resuelto de negocio
- trazabilidad run_id de punta a punta
- persistencia de estado de ejecucion
- backlog tecnico reflejado en Jira con estados
- capacidad de lanzar pipeline desde una sola orden operativa (script)
- backlog `mas-backlog-v2` completamente cerrado

## 4. Riesgos y deuda tecnica abierta
- credenciales sensibles usadas durante pruebas deben rotarse
- falta suite de tests automatizada robusta
- falta observabilidad operativa formal (metricas/alertas)
- queda deuda de endurecimiento adicional sobre payloads con Jira

## 5. Relacion con arquitectura objetivo
El workspace actual representa una arquitectura operativa funcional:
- la base de orquestacion, estado y backlog esta cerrada
- el canal WhatsApp ya tiene piezas estructurales implementadas en workflows
- siguen abiertas mejoras de robustez, observabilidad y calidad automatizada

## 6. Documentos vinculados
- ARQUITECTURA_DEFINITIVA_v2.md
- JIRA_BACKLOG_ESTADO.md
- jira-backlog-live-status.json
