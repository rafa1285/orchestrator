# Arquitectura Definitiva — Sistema Multiagente

> Version vigente. Actualizada a 2026-04-20.

## 1. Objetivo

Mantener una plataforma multiagente capaz de orquestar trabajo de desarrollo desde n8n,
ejecutar etapas Planner → Developer → Reviewer → Deployer, enlazar evidencia en Jira y
preservar trazabilidad end-to-end por `run_id`.

## 2. Arquitectura actual

### Entrada y orquestacion
- n8n desplegado en Render.
- Workflows principales: `whatsapp.json`, `planner.json`, `developer.json`, `mcp.json`, `jira-task-manager.json`, `mcp-ping.json`.
- El bridge `mcp.json` soporta `planner`, `full_pipeline` y `ping`.

### Backend de agentes
- `multiagent-system` expone endpoints FastAPI para planner, developer, reviewer, deployer y run-state.
- Los endpoints de agentes y de `runs` requieren `X-API-Key` cuando `MULTIAGENT_API_KEY` esta configurado.
- El estado de ejecucion se persiste con idempotencia por etapa y soporte de DB/fallback local.

### Jira y PM
- `orchestrator/mcp/n8n_mcp_server.py` centraliza herramientas n8n, multiagent, Jira y PM backlog.
- El backlog `mas-backlog-v2` esta completamente cerrado en Jira y el planner PM devuelve `pending_total=0`.
- Existe runbook operativo y loop autonomo para sync/plan/ejecucion cuando se abran nuevas tareas.

### Modelo LLM y desarrollo local
- `providers/open_source.py` ya llama a un endpoint Ollama-compatible real.
- Para pruebas locales existe un shim de desarrollo en `multiagent-system/dev/fake_ollama_server.py`.

## 3. Componentes activos

| Capa | Implementacion actual |
|---|---|
| Orquestacion | n8n en Render |
| Backend agentes | FastAPI en Render |
| Estado de ejecucion | DB + fallback local |
| Backlog y trazabilidad | Jira SCRUM + `run_id` |
| Herramientas | MCP centralizado + servidores especializados ya creados para filesystem, git, exec y http |
| Integracion WhatsApp | webhook tecnico + plantillas/flujo estructurado |

## 4. Estado funcional

### Resuelto
- pipeline end-to-end con propagacion de `run_id`
- Jira task manager y link automatico de ejecuciones
- plantillas Meta, flujo Whisper y respuestas estructuradas de WhatsApp
- project map central y creacion automatica de repos GitHub desde agentes
- logging y validators compartidos en `agent-tools`

### Abierto como trabajo futuro
- rotacion de credenciales de pruebas
- reduccion adicional de credenciales Jira en payloads
- suite de tests y regresion mas completa
- observabilidad y politicas de resiliencia avanzadas

## 5. Flujo operativo

1. n8n recibe una orden por webhook.
2. Se normaliza la entrada y se conserva o genera `run_id`.
3. n8n llama al backend multiagent con `X-API-Key` cuando aplica.
4. El backend persiste el estado por etapa.
5. El resultado se enlaza a Jira y se devuelve al origen del flujo.

## 6. Fuente de verdad

- `WORKSPACE_CONTEXTO_ACTUAL.md` para el estado por repositorio.
- `JIRA_BACKLOG_ESTADO.md` para el resumen operativo del backlog.
- `jira-backlog-live-status.json` para el ultimo snapshot validado.
8. Render: construye y levanta el servicio
9. n8n actualiza Jira: link run_id al issue
10. n8n → respuesta WhatsApp: PR URL, deploy URL, estado
```

**Entornos:**
- Staging: automatico en merge a main, sin aprobacion
- Production: requiere confirmacion explicita del usuario por WhatsApp: "si, desplegar"

---

## 6. Seguridad (requerimientos antes de produccion real)

1. API key obligatoria en todos los endpoints del backend (pendiente)
2. Credenciales nunca en payloads de llamadas — usar referencias de entorno
3. Rotacion de tokens de desarrollo/prueba usados hasta ahora
4. MCP exec: whitelist de comandos; blacklist absoluta: `rm -rf /`, `sudo`, `curl`, `wget`, `ssh`, `docker`, `systemctl`
5. MCP filesystem: solo `/projects/<proyecto-activo>`, prohibido `/`, `/home`, `/etc`, `/var`
6. MCP http: solo `api.render.com/*`, `api.github.com/*`, dominios internos autorizados
7. Despliegue a produccion nunca sin confirmacion humana explicita
8. Ningun agente puede modificar repos no autorizados

---

## 7. Estructura de repositorios del sistema

```
multiagent-system-suite/
├── multiagent-system/     -- API FastAPI: agentes + run state + providers
│   ├── main.py
│   ├── agents/            -- planner / developer / reviewer / deployer
│   ├── core/              -- config, run_state
│   ├── providers/         -- BaseLLMProvider, OpenSourceLLMProvider
│   ├── mcp/               -- config MCP del servicio
│   └── render.yaml
├── orchestrator/          -- MCP server, scripts de control, documentacion
│   ├── mcp/               -- n8n_mcp_server.py, pm_autonomous_loop.py
│   ├── config/            -- n8n-mcp.env
│   ├── docs/              -- documentacion de arquitectura y contexto
│   └── flows/             -- definiciones de flujos
├── infra-n8n-render/      -- Dockerfile + render.yaml para n8n en Render
│   ├── Dockerfile
│   └── render.yaml
├── n8n/                   -- definicion de workflows n8n
│   └── workflows/         -- whatsapp.json, mcp.json, jira-task-manager.json ...
├── agent-tools/           -- utilidades compartidas entre agentes
│   ├── logging/
│   ├── utils/
│   └── validators/
└── backend-template/      -- plantilla base para proyectos generados
    ├── src/
    ├── tests/
    ├── routes/
    └── services/
```

---

## 8. Roadmap de fases

### Fase A — Blindar productivo actual (PRIORIDAD MAXIMA)
- [ ] API key auth en todos los endpoints del backend multiagent
- [ ] Rotacion de credenciales usadas en desarrollo/pruebas
- [ ] Reducir exposicion de credenciales Jira en payloads de n8n
- [ ] Suite de tests: backend unit + integracion critica
- [ ] Tests de regresion basicos en workflows n8n
- [ ] Alertas minimas: errores por etapa, latencia, retries

### Fase B — Resiliencia operativa
- [ ] Reintentos con backoff por etapa en n8n
- [ ] Reanudar pipeline desde etapa fallida
- [ ] Comandos MCP para retry de stage run
- [ ] Politicas dead-letter en fallos repetidos
- [ ] DB dedicada para multiagent-system (migracion sin downtime)

### Fase C — Agentes con razonamiento real
- [ ] Integrar Ollama + Llama 3 8B en OpenSourceLLMProvider (reemplazar stub)
- [ ] Implementar logica real en PlannerAgent, DeveloperAgent, ReviewerAgent, DeployerAgent
- [ ] LLM parser de intencion estructurado en n8n
- [ ] Prompts de sistema completos por agente

### Fase D — Canal WhatsApp completo
- [ ] Verificacion de webhook Meta Cloud API
- [ ] Plantillas de mensajes aprobadas por Meta
- [ ] Deteccion y transcripcion de audio (Whisper)
- [ ] Respuesta conversacional estructurada al usuario
- [ ] Manejo de sesiones de conversacion

### Fase E — MCP especializado y generacion de proyectos
- [ ] MCP filesystem server con sandbox por proyecto
- [ ] MCP git server con token de permisos minimos
- [ ] MCP exec server con whitelist de comandos y contenedor aislado
- [ ] MCP http server con whitelist de dominios
- [ ] Plantilla CI/CD completa para proyectos generados
- [ ] Creacion automatica de repos GitHub desde agentes
- [ ] Mapa central de proyectos consultable por Planner Agent

---

## 9. Documentos relacionados

| Documento | Contenido |
|---|---|
| `CONTEXTO_INDEX.md` | Indice tecnico de todos los componentes del workspace |
| `WORKSPACE_CONTEXTO_ACTUAL.md` | Estado por repositorio y deuda tecnica |
| `JIRA_BACKLOG_ESTADO.md` | Estado del backlog en Jira con tareas pendientes |
| `jira-backlog-live-status.json` | Snapshot live del backlog de Jira |
| `PM_AGENT_RUNBOOK.md` | Como ejecutar el agente PM autonomo |
