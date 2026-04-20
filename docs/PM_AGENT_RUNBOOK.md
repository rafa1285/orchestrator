# PM Agent runbook

## Ejecución autónoma sin intervención (loop completo)

El script `orchestrator/mcp/pm_autonomous_loop.py` ahora ejecuta el backlog completo con
orquestación autónoma real sobre subagentes:
- planner
- developer
- reviewer
- deployer

Cada tarea:
- se descompone en subtareas internas
- se ejecuta con `run_id` propio
- deja comentario de plan en Jira
- deja evidencia técnica en Jira
- solo se cierra si review, despliegue y checks técnicos pasan

Ejecución:

```powershell
$envFile='orchestrator\config\n8n-mcp.env'
Get-Content $envFile | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } |
  ForEach-Object { $k,$v = $_ -split '=',2; [System.Environment]::SetEnvironmentVariable($k,$v,'Process') }
[System.Environment]::SetEnvironmentVariable('JIRA_MCP_ENABLE_WRITE','true','Process')
python orchestrator/mcp/pm_autonomous_loop.py
```

Flujo:
- sync backlog
- plan por dependencias y prioridad
- descomposición por familia de tarea
- planner -> developer -> reviewer -> deployer
- validation suite
- cierre Jira solo con política de cierre satisfecha

Cierre seguro:
- review aprobado
- despliegue/validación en estado positivo
- checks Jira/n8n/multiagent OK
- evidencia comentada en el issue

---

## Objetivo
Automatizar la gestion de backlog Jira con un agente PM que:
- sincroniza tareas faltantes
- planifica por prioridad y dependencias
- ejecuta ciclo de trabajo con evidencia y validaciones

## Herramientas PM disponibles
En el servidor MCP:
- pm_sync_backlog
- pm_plan_backlog
- pm_execute_backlog
- pm_execute_backlog_autonomously
- pm_find_backlog_duplicates
- pm_cleanup_backlog_duplicates

## Flujo recomendado
1. Ejecutar pm_sync_backlog
2. Ejecutar pm_find_backlog_duplicates
3. Si hay duplicados, ejecutar pm_cleanup_backlog_duplicates con apply_changes=true
4. Ejecutar pm_plan_backlog
5. Ejecutar pm_execute_backlog_autonomously en lotes pequeños o usar el loop completo
6. Revisar excepciones solo cuando una tarea quede en curso con evidencia negativa

## Estado actual observado
- Catalogo Jira ya existente y sincronizado
- Se detectaron duplicados historicos por uso de endpoint Jira deprecado
- Duplicados marcados con labels:
  - duplicate
  - mas-backlog-v2-duplicate

## Recomendacion operativa
- Mantener SCRUM-3..SCRUM-42 como set canonico
- No usar issues duplicadas SCRUM-43..SCRUM-82 para planning
- Ejecutar pm_execute_backlog_autonomously con dry_run=true antes de cada lote si quieres inspeccionar el plan

## Nota
El cierre automatico de una tarea depende de validaciones tecnicas, review aprobatorio y evidencia positiva. Si fallan, el issue queda en curso con comentario de evidencia para revision.
