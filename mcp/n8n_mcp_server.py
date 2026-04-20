"""MCP server for operating a remote n8n instance via API.

This server is designed for Render-hosted n8n and exposes a small set of
safe, auditable tools for workflow operations and observability.
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("n8n-render-mcp")


def _base_url() -> str:
    base = os.getenv("N8N_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("N8N_BASE_URL is required")
    return base


def _api_key() -> str:
    key = os.getenv("N8N_API_KEY", "").strip()
    if not key:
        raise RuntimeError("N8N_API_KEY is required")
    return key


def _timeout_seconds() -> float:
    raw = os.getenv("N8N_HTTP_TIMEOUT", "30").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 30.0
    return max(3.0, value)


def _multiagent_base_url() -> str:
    base = os.getenv("MULTIAGENT_API_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("MULTIAGENT_API_BASE_URL is required for multiagent tools")
    return base


def _multiagent_headers() -> Dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    api_key = os.getenv("MULTIAGENT_API_KEY", "").strip()
    if api_key:
        headers["X-API-Key"] = api_key
    return headers


def _write_enabled() -> bool:
    return os.getenv("N8N_MCP_ENABLE_WRITE", "false").lower() == "true"


def _jira_write_enabled() -> bool:
    return os.getenv("JIRA_MCP_ENABLE_WRITE", "false").lower() == "true"


def _jira_base_url() -> str:
    base = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("JIRA_BASE_URL is required for Jira tools")
    return base


def _jira_email() -> str:
    email = os.getenv("JIRA_EMAIL", "").strip()
    if not email:
        raise RuntimeError("JIRA_EMAIL is required for Jira tools")
    return email


def _jira_api_token() -> str:
    token = os.getenv("JIRA_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("JIRA_API_TOKEN is required for Jira tools")
    return token


def _jira_project_key() -> str:
    return os.getenv("JIRA_PROJECT_KEY", "").strip()


def _jira_headers() -> Dict[str, str]:
    raw = f"{_jira_email()}:{_jira_api_token()}"
    encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _headers() -> Dict[str, str]:
    return {
        "X-N8N-API-KEY": _api_key(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _response_payload(resp: httpx.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    return {
        "ok": resp.is_success,
        "status_code": resp.status_code,
        "data": data,
    }


async def _request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    use_api_key: bool = True,
) -> Dict[str, Any]:
    url = f"{_base_url()}/{path.lstrip('/')}"
    headers = _headers() if use_api_key else {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            resp = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
            )
        return _response_payload(resp)
    except Exception as exc:  # broad by design to return structured MCP errors
        return {
            "ok": False,
            "status_code": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "path": path,
        }


async def _request_multiagent(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = f"{_multiagent_base_url()}/{path.lstrip('/')}"

    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            resp = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=_multiagent_headers(),
            )
        return _response_payload(resp)
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "path": path,
        }


async def _request_jira(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = f"{_jira_base_url()}/{path.lstrip('/')}"

    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
            resp = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=_jira_headers(),
            )
        return _response_payload(resp)
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "error": f"{type(exc).__name__}: {exc}",
            "path": path,
        }


def _jira_doc(text: str) -> Dict[str, Any]:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


PM_EPICS: List[Dict[str, str]] = [
    {"code": "EPIC-OPS-002", "name": "Operacion base n8n + multiagent", "priority": "High"},
    {"code": "EPIC-MCP-002", "name": "MCP de operacion y observabilidad", "priority": "High"},
    {"code": "EPIC-RUN-STATE-002", "name": "Run state persistente e idempotencia", "priority": "High"},
    {"code": "EPIC-DATA-002", "name": "Estrategia de datos y migracion DB", "priority": "Medium"},
    {"code": "EPIC-SEC-002", "name": "Seguridad y hardening de plataforma", "priority": "High"},
    {"code": "EPIC-QUALITY-002", "name": "Calidad, pruebas y observabilidad", "priority": "Medium"},
    {"code": "EPIC-ARCH-002", "name": "Arquitectura objetivo de pipeline", "priority": "High"},
    {"code": "EPIC-JIRA-002", "name": "Gestion de backlog en Jira y automatizacion", "priority": "High"},
    {"code": "EPIC-AGENTS", "name": "Motor LLM real en agentes", "priority": "High"},
    {"code": "EPIC-WHATSAPP", "name": "Canal WhatsApp oficial completo", "priority": "Medium"},
    {"code": "EPIC-MCP-TOOLS", "name": "MCP servers especializados por herramienta", "priority": "High"},
    {"code": "EPIC-CICD", "name": "CI/CD y generacion de proyectos automatizada", "priority": "Medium"},
]


PM_TASKS: List[Dict[str, Any]] = [
    {"id": "MAS-1", "summary": "n8n desplegado en Render con workflows activos", "epic": "EPIC-OPS-002", "priority": "High", "deps": []},
    {"id": "MAS-2", "summary": "multiagent-system desplegado y accesible publicamente", "epic": "EPIC-OPS-002", "priority": "High", "deps": []},
    {"id": "MAS-3", "summary": "integracion n8n a multiagent validada end-to-end", "epic": "EPIC-OPS-002", "priority": "High", "deps": ["MAS-1", "MAS-2"]},
    {"id": "MAS-4", "summary": "scripts de sync import activate de workflows operativos", "epic": "EPIC-OPS-002", "priority": "Medium", "deps": ["MAS-1"]},
    {"id": "MAS-5", "summary": "servidor MCP n8n con health workflows executions", "epic": "EPIC-MCP-002", "priority": "High", "deps": ["MAS-1"]},
    {"id": "MAS-6", "summary": "tools MCP para run tracking create get list", "epic": "EPIC-MCP-002", "priority": "High", "deps": ["MAS-2", "MAS-5"]},
    {"id": "MAS-7", "summary": "comandos MCP para retry operacional de stage run", "epic": "EPIC-MCP-002", "priority": "High", "deps": ["MAS-6"]},
    {"id": "MAS-8", "summary": "guardas de escritura por flags en n8n y Jira", "epic": "EPIC-MCP-002", "priority": "Medium", "deps": ["MAS-5"]},
    {"id": "MAS-9", "summary": "propagacion run_id en backend y workflows", "epic": "EPIC-RUN-STATE-002", "priority": "High", "deps": ["MAS-3"]},
    {"id": "MAS-10", "summary": "estado persistente de runs en DB", "epic": "EPIC-RUN-STATE-002", "priority": "High", "deps": ["MAS-9"]},
    {"id": "MAS-11", "summary": "idempotencia por hash de input y cache success", "epic": "EPIC-RUN-STATE-002", "priority": "High", "deps": ["MAS-10"]},
    {"id": "MAS-12", "summary": "limite de intentos por etapa en backend", "epic": "EPIC-RUN-STATE-002", "priority": "High", "deps": ["MAS-10"]},
    {"id": "MAS-13", "summary": "reintentos con backoff por etapa en n8n", "epic": "EPIC-RUN-STATE-002", "priority": "High", "deps": ["MAS-9"]},
    {"id": "MAS-14", "summary": "reanudar pipeline desde etapa fallida", "epic": "EPIC-RUN-STATE-002", "priority": "High", "deps": ["MAS-12", "MAS-13"]},
    {"id": "MAS-15", "summary": "uso temporal de DB compartida n8n-db para run state", "epic": "EPIC-DATA-002", "priority": "Medium", "deps": ["MAS-10"]},
    {"id": "MAS-16", "summary": "provisionar base dedicada para multiagent-system", "epic": "EPIC-DATA-002", "priority": "Medium", "deps": ["MAS-15"]},
    {"id": "MAS-17", "summary": "plan de migracion a DB dedicada sin downtime", "epic": "EPIC-DATA-002", "priority": "Medium", "deps": ["MAS-16"]},
    {"id": "MAS-18", "summary": "exclusion de archivos sensibles y locales en gitignore", "epic": "EPIC-SEC-002", "priority": "High", "deps": []},
    {"id": "MAS-19", "summary": "rotacion de credenciales usadas en pruebas", "epic": "EPIC-SEC-002", "priority": "High", "deps": ["MAS-18"]},
    {"id": "MAS-20", "summary": "autenticacion API key en endpoints multiagent", "epic": "EPIC-SEC-002", "priority": "High", "deps": ["MAS-18"]},
    {"id": "MAS-21", "summary": "reducir exposicion de credenciales Jira en payloads", "epic": "EPIC-SEC-002", "priority": "High", "deps": ["MAS-19"]},
    {"id": "MAS-22", "summary": "smoke tests operativos de webhooks y runs", "epic": "EPIC-QUALITY-002", "priority": "Medium", "deps": ["MAS-3", "MAS-9"]},
    {"id": "MAS-23", "summary": "suite de tests backend unit e integracion", "epic": "EPIC-QUALITY-002", "priority": "High", "deps": ["MAS-10", "MAS-11", "MAS-12"]},
    {"id": "MAS-24", "summary": "tests de regresion para workflows n8n", "epic": "EPIC-QUALITY-002", "priority": "Medium", "deps": ["MAS-13", "MAS-14"]},
    {"id": "MAS-25", "summary": "alertas y metricas por etapa latencia y retries", "epic": "EPIC-QUALITY-002", "priority": "Medium", "deps": ["MAS-22"]},
    {"id": "MAS-26", "summary": "pipeline planner developer reviewer deployer operativo", "epic": "EPIC-ARCH-002", "priority": "High", "deps": ["MAS-3"]},
    {"id": "MAS-27", "summary": "estados terminales completed changes_required error", "epic": "EPIC-ARCH-002", "priority": "High", "deps": ["MAS-26", "MAS-12"]},
    {"id": "MAS-28", "summary": "politicas de compensacion o dead-letter en fallos repetidos", "epic": "EPIC-ARCH-002", "priority": "Medium", "deps": ["MAS-14", "MAS-25"]},
    {"id": "MAS-29", "summary": "workflow jira-task-manager con create list comment transition link", "epic": "EPIC-JIRA-002", "priority": "High", "deps": ["MAS-5"]},
    {"id": "MAS-30", "summary": "auto-link run_id a Jira desde full pipeline", "epic": "EPIC-JIRA-002", "priority": "High", "deps": ["MAS-29", "MAS-9"]},
    {"id": "MAS-31", "summary": "script de un comando crear issue ejecutar pipeline enlazar run", "epic": "EPIC-JIRA-002", "priority": "Medium", "deps": ["MAS-30"]},
    {"id": "MAS-32", "summary": "sincronizar backlog tecnico completo en Jira", "epic": "EPIC-JIRA-002", "priority": "Medium", "deps": ["MAS-31"]},
    # EPIC-AGENTS — Motor LLM real en agentes
    {"id": "MAS-33", "summary": "Integrar Ollama en OpenSourceLLMProvider", "epic": "EPIC-AGENTS", "priority": "High", "deps": []},
    {"id": "MAS-34", "summary": "Implementar logica real en PlannerAgent con LLM", "epic": "EPIC-AGENTS", "priority": "High", "deps": ["MAS-33"]},
    {"id": "MAS-35", "summary": "Implementar logica real en DeveloperAgent con LLM", "epic": "EPIC-AGENTS", "priority": "High", "deps": ["MAS-33", "MAS-34"]},
    {"id": "MAS-36", "summary": "Implementar logica real en ReviewerAgent con LLM", "epic": "EPIC-AGENTS", "priority": "Medium", "deps": ["MAS-33", "MAS-35"]},
    {"id": "MAS-37", "summary": "Implementar logica real en DeployerAgent con LLM", "epic": "EPIC-AGENTS", "priority": "Medium", "deps": ["MAS-33", "MAS-36"]},
    {"id": "MAS-38", "summary": "Parser de intencion LLM estructurado en n8n", "epic": "EPIC-AGENTS", "priority": "High", "deps": ["MAS-1", "MAS-3"]},
    {"id": "MAS-39", "summary": "Prompts de sistema completos por agente", "epic": "EPIC-AGENTS", "priority": "Medium", "deps": ["MAS-34", "MAS-35", "MAS-36", "MAS-37"]},
    # EPIC-WHATSAPP — Canal WhatsApp oficial completo
    {"id": "MAS-40", "summary": "Verificacion webhook Meta Cloud API challenge", "epic": "EPIC-WHATSAPP", "priority": "High", "deps": ["MAS-1"]},
    {"id": "MAS-41", "summary": "Plantillas de mensajes WhatsApp aprobadas por Meta", "epic": "EPIC-WHATSAPP", "priority": "Medium", "deps": ["MAS-40"]},
    {"id": "MAS-42", "summary": "Transcripcion de audio con Whisper self-hosted en n8n", "epic": "EPIC-WHATSAPP", "priority": "Medium", "deps": ["MAS-40"]},
    {"id": "MAS-43", "summary": "Respuesta conversacional estructurada al usuario WhatsApp", "epic": "EPIC-WHATSAPP", "priority": "Medium", "deps": ["MAS-40", "MAS-41"]},
    # EPIC-MCP-TOOLS — MCP servers especializados por herramienta
    {"id": "MAS-44", "summary": "MCP filesystem server con sandbox por proyecto", "epic": "EPIC-MCP-TOOLS", "priority": "High", "deps": ["MAS-5"]},
    {"id": "MAS-45", "summary": "MCP git server con token de permisos minimos", "epic": "EPIC-MCP-TOOLS", "priority": "High", "deps": ["MAS-5"]},
    {"id": "MAS-46", "summary": "MCP exec server con whitelist de comandos aislado", "epic": "EPIC-MCP-TOOLS", "priority": "High", "deps": ["MAS-5"]},
    {"id": "MAS-47", "summary": "MCP http server con whitelist de dominios", "epic": "EPIC-MCP-TOOLS", "priority": "Medium", "deps": ["MAS-5"]},
    # EPIC-CICD — CI/CD y generacion de proyectos automatizada
    {"id": "MAS-48", "summary": "Plantilla CI/CD completa para proyectos generados", "epic": "EPIC-CICD", "priority": "High", "deps": ["MAS-35"]},
    {"id": "MAS-49", "summary": "Creacion automatica de repos GitHub desde agentes", "epic": "EPIC-CICD", "priority": "Medium", "deps": ["MAS-37", "MAS-45"]},
    {"id": "MAS-50", "summary": "Mapa central de proyectos consultable por Planner", "epic": "EPIC-CICD", "priority": "Medium", "deps": ["MAS-34"]},
    # EPIC-QUALITY-002 — agent-tools
    {"id": "MAS-51", "summary": "Completar agent-tools logging estandarizado", "epic": "EPIC-QUALITY-002", "priority": "Low", "deps": []},
    {"id": "MAS-52", "summary": "Completar agent-tools validators de entrada agentes", "epic": "EPIC-QUALITY-002", "priority": "Low", "deps": ["MAS-51"]},
]


def _priority_id(name: str) -> str:
    table = {
        "Highest": "1",
        "High": "2",
        "Medium": "3",
        "Low": "4",
        "Lowest": "5",
    }
    return table.get(name, "3")


def _issue_status_done(status_name: str) -> bool:
    lowered = status_name.strip().lower()
    return lowered in {"listo", "finalizada", "done", "cerrado", "closed"}


async def _jira_search(jql: str, limit: int = 200) -> List[Dict[str, Any]]:
    params = {
        "jql": jql,
        "maxResults": max(1, min(limit, 200)),
        "fields": "summary,status,issuetype,priority,parent,labels",
    }
    resp = await _request_jira("GET", "/rest/api/3/search/jql", params=params)
    if not resp.get("ok"):
        return []
    data = resp.get("data")
    if not isinstance(data, dict):
        return []
    items = data.get("issues")
    if not isinstance(items, list):
        return []
    return items


def _pm_catalog_task_ids() -> List[str]:
    return [item["id"] for item in PM_TASKS]


async def _pm_build_index() -> Dict[str, Dict[str, Any]]:
    issues = await _jira_search("project=" + _jira_project_key() + " AND labels=mas-backlog-v2 ORDER BY created ASC")
    by_mas_id: Dict[str, Dict[str, Any]] = {}
    by_epic_code: Dict[str, Dict[str, Any]] = {}

    for issue in issues:
        key = issue.get("key")
        fields = issue.get("fields") if isinstance(issue, dict) else None
        if not key or not isinstance(fields, dict):
            continue
        labels = fields.get("labels") or []
        if not isinstance(labels, list):
            labels = []
        for label in labels:
            if isinstance(label, str) and label.startswith("mas-") and label[4:].isdigit():
                logical_id = f"MAS-{label[4:]}"
                if logical_id not in by_mas_id:
                    by_mas_id[logical_id] = issue
            if isinstance(label, str) and label.startswith("epic-"):
                issue_type = ""
                if isinstance(fields.get("issuetype"), dict):
                    issue_type = str(fields["issuetype"].get("name", ""))
                logical_epic = label.replace("epic-", "EPIC-").upper()
                if issue_type.lower() == "epic" and logical_epic not in by_epic_code:
                    by_epic_code[logical_epic] = issue

    for task in PM_TASKS:
        task_id = task["id"]
        if task_id in by_mas_id:
            continue
        label = task_id.lower().replace("mas-", "mas-")
        fallback = await _jira_search(
            f"project={_jira_project_key()} AND labels=mas-backlog-v2 AND labels={label} ORDER BY created ASC",
            limit=5,
        )
        if fallback:
            by_mas_id[task_id] = fallback[0]

    for epic in PM_EPICS:
        code = epic["code"]
        if code in by_epic_code:
            continue
        label = code.lower()
        fallback = await _jira_search(
            f"project={_jira_project_key()} AND labels=mas-backlog-v2 AND labels={label} ORDER BY created ASC",
            limit=5,
        )
        if fallback:
            by_epic_code[code] = fallback[0]

    return {"mas": by_mas_id, "epic": by_epic_code}


async def _pm_validation_suite(task_id: str) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    n8n_workflows = await n8n_list_workflows(limit=1)
    checks.append(
        {
            "check": "n8n_api_workflows",
            "ok": bool(n8n_workflows.get("ok")),
            "status_code": n8n_workflows.get("status_code"),
        }
    )

    n8n_ping = await _request("POST", "/webhook/mcp-ping", json_body={"action": "ping"}, use_api_key=False)
    checks.append(
        {
            "check": "n8n_webhook_ping",
            "ok": bool(n8n_ping.get("ok")),
            "status_code": n8n_ping.get("status_code"),
        }
    )

    jira = await jira_health_check()
    checks.append({"check": "jira_health", "ok": bool(jira.get("ok")), "status_code": jira.get("status_code")})

    run_probe = await multiagent_list_runs(limit=1)
    if not run_probe.get("ok"):
        run_probe = await _request_multiagent("GET", "/")
        checks.append(
            {
                "check": "multiagent_health_fallback",
                "ok": bool(run_probe.get("ok")),
                "status_code": run_probe.get("status_code"),
            }
        )
    else:
        checks.append({"check": "multiagent_runs", "ok": True, "status_code": run_probe.get("status_code")})

    failed = [item for item in checks if not item["ok"]]
    return {"task_id": task_id, "ok": len(failed) == 0, "checks": checks}


def _pm_validate_task_33() -> Dict[str, Any]:
    sys_path = r"c:/multiagent-system-suite/multiagent-system"
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)

    provider_module = importlib.import_module("providers.open_source")
    config_module = importlib.import_module("core.config")
    provider_class = getattr(provider_module, "OpenSourceLLMProvider")

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/api/generate":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8"))
            response = {"response": f"ok::{payload['model']}::{payload['prompt']}"}
            encoded = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format, *args):
            return

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_base_url = getattr(config_module, "LLM_BASE_URL")
    original_model = getattr(config_module, "LLM_MODEL")
    try:
        config_module.LLM_BASE_URL = f"http://127.0.0.1:{port}"
        config_module.LLM_MODEL = "llama-test"
        provider = provider_class()
        result = provider.complete("ping prompt")
    finally:
        config_module.LLM_BASE_URL = original_base_url
        config_module.LLM_MODEL = original_model
        server.shutdown()
        thread.join(timeout=2)

    expected = "ok::llama-test::ping prompt"
    return {
        "task_id": "MAS-33",
        "ok": result == expected,
        "check": "provider_http_integration",
        "expected": expected,
        "actual": result,
    }


async def _pm_validate_task_20() -> Dict[str, Any]:
    base_url = os.getenv("MULTIAGENT_API_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("MULTIAGENT_API_KEY", "").strip()
    if not base_url or not api_key:
        return {
            "task_id": "MAS-20",
            "ok": False,
            "check": "multiagent_api_key_auth",
            "reason": "MULTIAGENT_API_BASE_URL and MULTIAGENT_API_KEY are required for MAS-20 validation",
        }

    async with httpx.AsyncClient(timeout=_timeout_seconds()) as client:
        unauthorized = await client.get(f"{base_url}/runs")
        authorized = await client.post(f"{base_url}/runs", headers={"X-API-Key": api_key})
        authorized_data = {}
        try:
            authorized_data = authorized.json()
        except Exception:
            authorized_data = {}
        result = {
            "unauthorized_status": unauthorized.status_code,
            "authorized_status": authorized.status_code,
            "authorized_ok": authorized.status_code == 200 and isinstance(authorized_data, dict),
        }

    return {
        "task_id": "MAS-20",
        "ok": result["unauthorized_status"] == 401 and result["authorized_ok"],
        "check": "multiagent_api_key_auth",
        "details": result,
    }


async def _pm_validate_task_34() -> Dict[str, Any]:
    run_resp = await multiagent_create_run()
    run_data = run_resp.get("data") if isinstance(run_resp, dict) else {}
    run_id = (run_data or {}).get("run_id") if isinstance(run_data, dict) else None
    if not run_resp.get("ok") or not run_id:
        return {
            "task_id": "MAS-34",
            "ok": False,
            "check": "planner_structured_output",
            "reason": "Could not create run_id for MAS-34 validator",
        }

    planner = await _pm_call_multiagent_stage(
        "planner",
        {
            "task": "MAS-34 validator: generate structured planning output",
            "run_id": run_id,
        },
    )
    planner_data = planner.get("data") if isinstance(planner, dict) else {}
    plan_payload = _pm_load_json((planner_data or {}).get("plan"))

    required_keys = {"objective", "family", "subtasks", "validation"}
    has_required = all(key in plan_payload for key in required_keys)
    subtasks = plan_payload.get("subtasks") if isinstance(plan_payload, dict) else None
    validation = plan_payload.get("validation") if isinstance(plan_payload, dict) else None
    structure_ok = isinstance(subtasks, list) and len(subtasks) > 0 and isinstance(validation, list) and len(validation) > 0

    return {
        "task_id": "MAS-34",
        "ok": bool(planner.get("ok")) and has_required and structure_ok,
        "check": "planner_structured_output",
        "details": {
            "planner_ok": bool(planner.get("ok")),
            "status_code": planner.get("status_code"),
            "has_required_keys": has_required,
            "structure_ok": structure_ok,
            "family": plan_payload.get("family") if isinstance(plan_payload, dict) else None,
        },
    }


async def _pm_validate_task_35() -> Dict[str, Any]:
    run_resp = await multiagent_create_run()
    run_data = run_resp.get("data") if isinstance(run_resp, dict) else {}
    run_id = (run_data or {}).get("run_id") if isinstance(run_data, dict) else None
    if not run_resp.get("ok") or not run_id:
        return {
            "task_id": "MAS-35",
            "ok": False,
            "check": "developer_structured_output",
            "reason": "Could not create run_id for MAS-35 validator",
        }

    planner = await _pm_call_multiagent_stage(
        "planner",
        {
            "task": "MAS-35 validator: produce plan for developer output validation",
            "run_id": run_id,
        },
    )
    planner_data = planner.get("data") if isinstance(planner, dict) else {}
    plan_payload = _pm_load_json((planner_data or {}).get("plan"))

    developer = await _pm_call_multiagent_stage(
        "developer",
        {
            "plan": plan_payload,
            "run_id": run_id,
        },
    )
    developer_data = developer.get("data") if isinstance(developer, dict) else {}
    code_payload = _pm_load_json((developer_data or {}).get("code"))

    required_keys = {"objective", "family", "completed_subtasks", "artifacts", "implementation_status"}
    has_required = all(key in code_payload for key in required_keys)
    artifacts = code_payload.get("artifacts") if isinstance(code_payload, dict) else None
    structure_ok = isinstance(artifacts, list) and len(artifacts) > 0 and code_payload.get("implementation_status") == "implemented"

    return {
        "task_id": "MAS-35",
        "ok": bool(developer.get("ok")) and has_required and structure_ok,
        "check": "developer_structured_output",
        "details": {
            "developer_ok": bool(developer.get("ok")),
            "status_code": developer.get("status_code"),
            "has_required_keys": has_required,
            "structure_ok": structure_ok,
            "artifacts_count": len(artifacts) if isinstance(artifacts, list) else 0,
        },
    }


async def _pm_validate_task_36() -> Dict[str, Any]:
    run_resp = await multiagent_create_run()
    run_data = run_resp.get("data") if isinstance(run_resp, dict) else {}
    run_id = (run_data or {}).get("run_id") if isinstance(run_data, dict) else None
    if not run_resp.get("ok") or not run_id:
        return {
            "task_id": "MAS-36",
            "ok": False,
            "check": "reviewer_structured_output",
            "reason": "Could not create run_id for MAS-36 validator",
        }

    planner = await _pm_call_multiagent_stage(
        "planner",
        {
            "task": "MAS-36 validator: produce plan for reviewer output validation",
            "run_id": run_id,
        },
    )
    plan_payload = _pm_load_json(((planner.get("data") or {}).get("plan")) if isinstance(planner, dict) else None)
    developer = await _pm_call_multiagent_stage("developer", {"plan": plan_payload, "run_id": run_id})
    code_payload = _pm_load_json(((developer.get("data") or {}).get("code")) if isinstance(developer, dict) else None)
    reviewer = await _pm_call_multiagent_stage("reviewer", {"code": code_payload, "run_id": run_id})
    reviewer_data = reviewer.get("data") if isinstance(reviewer, dict) else {}
    review_payload = _pm_load_json((reviewer_data or {}).get("review"))

    has_required = isinstance(review_payload, dict) and all(k in review_payload for k in ("approved", "findings", "summary"))
    structure_ok = isinstance(review_payload.get("findings") if isinstance(review_payload, dict) else None, list)

    return {
        "task_id": "MAS-36",
        "ok": bool(reviewer.get("ok")) and bool((reviewer_data or {}).get("approved")) and has_required and structure_ok,
        "check": "reviewer_structured_output",
        "details": {
            "reviewer_ok": bool(reviewer.get("ok")),
            "status_code": reviewer.get("status_code"),
            "approved": bool((reviewer_data or {}).get("approved")),
            "has_required_keys": has_required,
            "structure_ok": structure_ok,
        },
    }


async def _pm_validate_task_37() -> Dict[str, Any]:
    run_resp = await multiagent_create_run()
    run_data = run_resp.get("data") if isinstance(run_resp, dict) else {}
    run_id = (run_data or {}).get("run_id") if isinstance(run_data, dict) else None
    if not run_resp.get("ok") or not run_id:
        return {
            "task_id": "MAS-37",
            "ok": False,
            "check": "deployer_structured_output",
            "reason": "Could not create run_id for MAS-37 validator",
        }

    planner = await _pm_call_multiagent_stage(
        "planner",
        {
            "task": "MAS-37 validator: produce plan for deployer output validation",
            "run_id": run_id,
        },
    )
    plan_payload = _pm_load_json(((planner.get("data") or {}).get("plan")) if isinstance(planner, dict) else None)
    developer = await _pm_call_multiagent_stage("developer", {"plan": plan_payload, "run_id": run_id})
    code_payload = _pm_load_json(((developer.get("data") or {}).get("code")) if isinstance(developer, dict) else None)
    reviewer = await _pm_call_multiagent_stage("reviewer", {"code": code_payload, "run_id": run_id})
    reviewer_data = reviewer.get("data") if isinstance(reviewer, dict) else {}
    review_payload = _pm_load_json((reviewer_data or {}).get("review"))

    deployer = await _pm_call_multiagent_stage(
        "deployer",
        {
            "review": {
                "approved": bool((reviewer_data or {}).get("approved")),
                "review": review_payload,
                "code": code_payload,
                "task_id": "MAS-37",
            },
            "run_id": run_id,
        },
    )
    deployer_data = deployer.get("data") if isinstance(deployer, dict) else {}
    deployment_payload = _pm_load_json((deployer_data or {}).get("deployment"))
    status = str((deployer_data or {}).get("status", deployment_payload.get("status", "")))
    ready_for_close = bool(deployment_payload.get("ready_for_close"))

    return {
        "task_id": "MAS-37",
        "ok": bool(deployer.get("ok")) and status in {"validated", "completed", "success"} and ready_for_close,
        "check": "deployer_structured_output",
        "details": {
            "deployer_ok": bool(deployer.get("ok")),
            "status_code": deployer.get("status_code"),
            "status": status,
            "ready_for_close": ready_for_close,
        },
    }


async def _pm_validate_task_38() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    workflow_path = workspace_root / "n8n" / "workflows" / "whatsapp.json"
    exists = workflow_path.exists()
    if not exists:
        return {
            "task_id": "MAS-38",
            "ok": False,
            "check": "n8n_structured_intent_parser",
            "reason": f"Workflow not found: {workflow_path}",
        }

    text = workflow_path.read_text(encoding="utf-8")
    required_tokens = [
        '"name": "Normalize Input"',
        "function inferIntent(text)",
        "intent:",
        "confidence",
        "structuredTask",
    ]
    missing = [token for token in required_tokens if token not in text]

    return {
        "task_id": "MAS-38",
        "ok": len(missing) == 0,
        "check": "n8n_structured_intent_parser",
        "details": {
            "workflow_path": str(workflow_path),
            "missing_tokens": missing,
        },
    }


async def _pm_validate_task_40() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    workflow_path = workspace_root / "n8n" / "workflows" / "meta-webhook-verify.json"
    exists = workflow_path.exists()
    if not exists:
        return {
            "task_id": "MAS-40",
            "ok": False,
            "check": "meta_webhook_challenge_verification",
            "reason": f"Workflow not found: {workflow_path}",
        }

    text = workflow_path.read_text(encoding="utf-8")
    required_tokens = [
        '"httpMethod": "GET"',
        '"path": "meta-webhook"',
        "hub.mode",
        "hub.verify_token",
        "hub.challenge",
        "META_VERIFY_TOKEN",
        "respondToWebhook",
    ]
    missing = [token for token in required_tokens if token not in text]

    return {
        "task_id": "MAS-40",
        "ok": len(missing) == 0,
        "check": "meta_webhook_challenge_verification",
        "details": {
            "workflow_path": str(workflow_path),
            "missing_tokens": missing,
        },
    }


async def _pm_validate_task_41() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    templates_path = workspace_root / "n8n" / "workflows" / "whatsapp-message-templates.json"
    if not templates_path.exists():
        return {
            "task_id": "MAS-41",
            "ok": False,
            "check": "meta_whatsapp_templates",
            "reason": f"Templates file not found: {templates_path}",
        }

    text = templates_path.read_text(encoding="utf-8")
    required_tokens = [
        "Meta Cloud API",
        "APPROVED",
        "task_status_update_v1",
        "task_changes_required_v1",
    ]
    missing = [token for token in required_tokens if token not in text]
    return {
        "task_id": "MAS-41",
        "ok": len(missing) == 0,
        "check": "meta_whatsapp_templates",
        "details": {
            "templates_path": str(templates_path),
            "missing_tokens": missing,
        },
    }


async def _pm_validate_task_42() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    workflow_path = workspace_root / "n8n" / "workflows" / "whisper-transcription.json"
    if not workflow_path.exists():
        return {
            "task_id": "MAS-42",
            "ok": False,
            "check": "whisper_transcription_flow",
            "reason": f"Workflow not found: {workflow_path}",
        }

    text = workflow_path.read_text(encoding="utf-8")
    required_tokens = [
        "whisper-transcribe",
        "Call Whisper Self-Hosted",
        "WHISPER_BASE_URL",
        "isAudioMessage",
        "whisper-large-v3",
    ]
    missing = [token for token in required_tokens if token not in text]
    return {
        "task_id": "MAS-42",
        "ok": len(missing) == 0,
        "check": "whisper_transcription_flow",
        "details": {
            "workflow_path": str(workflow_path),
            "missing_tokens": missing,
        },
    }


async def _pm_validate_task_43() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    workflow_path = workspace_root / "n8n" / "workflows" / "whatsapp.json"
    if not workflow_path.exists():
        return {
            "task_id": "MAS-43",
            "ok": False,
            "check": "whatsapp_structured_response",
            "reason": f"Workflow not found: {workflow_path}",
        }

    text = workflow_path.read_text(encoding="utf-8")
    required_tokens = [
        "whatsapp_response",
        "task_status",
        "pr_url",
        "deploy_url",
        "error_message",
        "meta_cloud_api",
    ]
    missing = [token for token in required_tokens if token not in text]
    return {
        "task_id": "MAS-43",
        "ok": len(missing) == 0,
        "check": "whatsapp_structured_response",
        "details": {
            "workflow_path": str(workflow_path),
            "missing_tokens": missing,
        },
    }


async def _pm_validate_task_44() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    server_path = workspace_root / "orchestrator" / "mcp" / "filesystem_mcp_server.py"
    client_example_path = workspace_root / "orchestrator" / "mcp" / "n8n-mcp.client.example.json"

    if not server_path.exists():
        return {
            "task_id": "MAS-44",
            "ok": False,
            "check": "mcp_filesystem_sandbox",
            "reason": f"Server file not found: {server_path}",
        }

    server_text = server_path.read_text(encoding="utf-8")
    client_text = client_example_path.read_text(encoding="utf-8") if client_example_path.exists() else ""

    required_server_tokens = [
        "FastMCP",
        "ALLOWED_PROJECTS",
        "_resolve_safe_path",
        "Path escapes sandbox",
        "def fs_read_text",
        "def fs_write_text",
    ]
    missing_server = [token for token in required_server_tokens if token not in server_text]

    required_client_tokens = [
        '"filesystem-sandbox"',
        "filesystem_mcp_server.py",
        "ALLOWED_PROJECTS",
    ]
    missing_client = [token for token in required_client_tokens if token not in client_text]

    return {
        "task_id": "MAS-44",
        "ok": len(missing_server) == 0 and len(missing_client) == 0,
        "check": "mcp_filesystem_sandbox",
        "details": {
            "server_path": str(server_path),
            "client_example_path": str(client_example_path),
            "missing_server_tokens": missing_server,
            "missing_client_tokens": missing_client,
        },
    }


async def _pm_validate_task_45() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    server_path = workspace_root / "orchestrator" / "mcp" / "git_mcp_server.py"
    client_example_path = workspace_root / "orchestrator" / "mcp" / "n8n-mcp.client.example.json"

    if not server_path.exists():
        return {
            "task_id": "MAS-45",
            "ok": False,
            "check": "mcp_git_min_permissions",
            "reason": f"Server file not found: {server_path}",
        }

    server_text = server_path.read_text(encoding="utf-8")
    client_text = client_example_path.read_text(encoding="utf-8") if client_example_path.exists() else ""

    required_server_tokens = [
        "GIT_REPO_ROOT",
        "GIT_ALLOWED_COMMANDS",
        "GIT_READ_ONLY",
        "Git command not allowed",
        "read-only mode",
        "def git_status_short",
    ]
    missing_server = [token for token in required_server_tokens if token not in server_text]

    required_client_tokens = [
        '"git-minimal"',
        "git_mcp_server.py",
        "GIT_ALLOWED_COMMANDS",
    ]
    missing_client = [token for token in required_client_tokens if token not in client_text]

    return {
        "task_id": "MAS-45",
        "ok": len(missing_server) == 0 and len(missing_client) == 0,
        "check": "mcp_git_min_permissions",
        "details": {
            "server_path": str(server_path),
            "client_example_path": str(client_example_path),
            "missing_server_tokens": missing_server,
            "missing_client_tokens": missing_client,
        },
    }


async def _pm_validate_task_46() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    server_path = workspace_root / "orchestrator" / "mcp" / "exec_mcp_server.py"
    client_example_path = workspace_root / "orchestrator" / "mcp" / "n8n-mcp.client.example.json"

    if not server_path.exists():
        return {
            "task_id": "MAS-46",
            "ok": False,
            "check": "mcp_exec_whitelist",
            "reason": f"Server file not found: {server_path}",
        }

    server_text = server_path.read_text(encoding="utf-8")
    client_text = client_example_path.read_text(encoding="utf-8") if client_example_path.exists() else ""

    required_server_tokens = [
        "EXEC_ALLOWED_COMMANDS",
        "EXEC_WORKDIR",
        "Blocked shell metacharacter detected",
        "Command not in whitelist",
        "def exec_run",
    ]
    missing_server = [token for token in required_server_tokens if token not in server_text]

    required_client_tokens = [
        '"exec-whitelist"',
        "exec_mcp_server.py",
        "EXEC_ALLOWED_COMMANDS",
    ]
    missing_client = [token for token in required_client_tokens if token not in client_text]

    return {
        "task_id": "MAS-46",
        "ok": len(missing_server) == 0 and len(missing_client) == 0,
        "check": "mcp_exec_whitelist",
        "details": {
            "server_path": str(server_path),
            "client_example_path": str(client_example_path),
            "missing_server_tokens": missing_server,
            "missing_client_tokens": missing_client,
        },
    }


async def _pm_validate_task_48() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    ci_path = workspace_root / "backend-template" / ".github" / "workflows" / "ci.yml"
    cd_path = workspace_root / "backend-template" / ".github" / "workflows" / "cd.yml"
    readme_path = workspace_root / "backend-template" / "README.md"

    missing_files = [
        str(path)
        for path in [ci_path, cd_path, readme_path]
        if not path.exists()
    ]
    if missing_files:
        return {
            "task_id": "MAS-48",
            "ok": False,
            "check": "backend_template_cicd",
            "reason": "Missing expected files",
            "details": {"missing_files": missing_files},
        }

    ci_text = ci_path.read_text(encoding="utf-8")
    cd_text = cd_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")

    required_ci_tokens = [
        "Backend Template CI",
        "actions/setup-node@v4",
        "actions/setup-python@v5",
        "Verify template structure",
    ]
    required_cd_tokens = [
        "Backend Template CD",
        "workflow_dispatch",
        "DEPLOY_COMMAND",
        "actions/upload-artifact@v4",
    ]
    required_readme_tokens = [
        "CI/CD Template Included",
        "DEPLOY_COMMAND",
        "cd.yml",
    ]

    missing_ci = [token for token in required_ci_tokens if token not in ci_text]
    missing_cd = [token for token in required_cd_tokens if token not in cd_text]
    missing_readme = [token for token in required_readme_tokens if token not in readme_text]

    return {
        "task_id": "MAS-48",
        "ok": len(missing_ci) == 0 and len(missing_cd) == 0 and len(missing_readme) == 0,
        "check": "backend_template_cicd",
        "details": {
            "ci_path": str(ci_path),
            "cd_path": str(cd_path),
            "readme_path": str(readme_path),
            "missing_ci_tokens": missing_ci,
            "missing_cd_tokens": missing_cd,
            "missing_readme_tokens": missing_readme,
        },
    }


async def _pm_validate_task_47() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    server_path = workspace_root / "orchestrator" / "mcp" / "http_mcp_server.py"
    client_example_path = workspace_root / "orchestrator" / "mcp" / "n8n-mcp.client.example.json"

    if not server_path.exists():
        return {
            "task_id": "MAS-47",
            "ok": False,
            "check": "mcp_http_whitelist",
            "reason": f"Server file not found: {server_path}",
        }

    server_text = server_path.read_text(encoding="utf-8")
    client_text = client_example_path.read_text(encoding="utf-8") if client_example_path.exists() else ""

    required_server_tokens = [
        "HTTP_ALLOWED_DOMAINS",
        "HTTP_ALLOWED_METHODS",
        "Domain not in whitelist",
        "Method not allowed",
        "Only https URLs are allowed",
        "def http_request",
    ]
    required_client_tokens = [
        '"http-whitelist"',
        "http_mcp_server.py",
        "HTTP_ALLOWED_DOMAINS",
    ]
    missing_server = [token for token in required_server_tokens if token not in server_text]
    missing_client = [token for token in required_client_tokens if token not in client_text]

    return {
        "task_id": "MAS-47",
        "ok": len(missing_server) == 0 and len(missing_client) == 0,
        "check": "mcp_http_whitelist",
        "details": {
            "server_path": str(server_path),
            "client_example_path": str(client_example_path),
            "missing_server_tokens": missing_server,
            "missing_client_tokens": missing_client,
        },
    }


async def _pm_validate_task_49() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    deployer_path = workspace_root / "multiagent-system" / "agents" / "deployer" / "agent.py"
    if not deployer_path.exists():
        return {
            "task_id": "MAS-49",
            "ok": False,
            "check": "github_repo_auto_create",
            "reason": f"Deployer file not found: {deployer_path}",
        }

    text = deployer_path.read_text(encoding="utf-8")
    required_tokens = [
        "def _create_github_repo",
        "GITHUB_TOKEN",
        "/user/repos",
        "github_repo",
        "MAS-49",
    ]
    missing = [token for token in required_tokens if token not in text]
    return {
        "task_id": "MAS-49",
        "ok": len(missing) == 0,
        "check": "github_repo_auto_create",
        "details": {
            "deployer_path": str(deployer_path),
            "missing_tokens": missing,
        },
    }


async def _pm_validate_task_50() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    projects_map_path = workspace_root / "orchestrator" / "config" / "projects.yaml"
    planner_path = workspace_root / "multiagent-system" / "agents" / "planner" / "agent.py"

    missing_files = [
        str(path)
        for path in [projects_map_path, planner_path]
        if not path.exists()
    ]
    if missing_files:
        return {
            "task_id": "MAS-50",
            "ok": False,
            "check": "projects_map_for_planner",
            "reason": "Missing expected files",
            "details": {"missing_files": missing_files},
        }

    map_text = projects_map_path.read_text(encoding="utf-8")
    planner_text = planner_path.read_text(encoding="utf-8")
    required_map_tokens = ["projects:", "name:", "repo:", "environments:"]
    required_planner_tokens = ["projects.yaml", "_load_projects_map", "project_context", "matched_projects"]
    missing_map = [token for token in required_map_tokens if token not in map_text]
    missing_planner = [token for token in required_planner_tokens if token not in planner_text]

    return {
        "task_id": "MAS-50",
        "ok": len(missing_map) == 0 and len(missing_planner) == 0,
        "check": "projects_map_for_planner",
        "details": {
            "projects_map_path": str(projects_map_path),
            "planner_path": str(planner_path),
            "missing_map_tokens": missing_map,
            "missing_planner_tokens": missing_planner,
        },
    }


async def _pm_validate_task_51() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    logger_path = workspace_root / "agent-tools" / "agent_logging" / "standard_logger.py"
    if not logger_path.exists():
        return {
            "task_id": "MAS-51",
            "ok": False,
            "check": "agent_tools_logging_standardized",
            "reason": f"Logger file not found: {logger_path}",
        }

    text = logger_path.read_text(encoding="utf-8")
    required_tokens = ["JsonFormatter", "configure_logging", "get_logger", "timestamp", "run_id"]
    missing = [token for token in required_tokens if token not in text]
    return {
        "task_id": "MAS-51",
        "ok": len(missing) == 0,
        "check": "agent_tools_logging_standardized",
        "details": {
            "logger_path": str(logger_path),
            "missing_tokens": missing,
        },
    }


async def _pm_validate_task_52() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    validators_path = workspace_root / "agent-tools" / "validators" / "input_validators.py"
    if not validators_path.exists():
        return {
            "task_id": "MAS-52",
            "ok": False,
            "check": "agent_tools_input_validators",
            "reason": f"Validators file not found: {validators_path}",
        }

    text = validators_path.read_text(encoding="utf-8")
    required_tokens = ["validate_agent_payload", "planner", "developer", "reviewer", "deployer", "missing_fields"]
    missing = [token for token in required_tokens if token not in text]
    return {
        "task_id": "MAS-52",
        "ok": len(missing) == 0,
        "check": "agent_tools_input_validators",
        "details": {
            "validators_path": str(validators_path),
            "missing_tokens": missing,
        },
    }


async def _pm_validate_task_39() -> Dict[str, Any]:
    workspace_root = Path(__file__).resolve().parents[2]
    required_pairs = [
        (
            workspace_root / "multiagent-system" / "agents" / "planner" / "agent.py",
            workspace_root / "multiagent-system" / "agents" / "planner" / "prompts" / "system.md",
        ),
        (
            workspace_root / "multiagent-system" / "agents" / "developer" / "agent.py",
            workspace_root / "multiagent-system" / "agents" / "developer" / "prompts" / "system.md",
        ),
        (
            workspace_root / "multiagent-system" / "agents" / "reviewer" / "agent.py",
            workspace_root / "multiagent-system" / "agents" / "reviewer" / "prompts" / "system.md",
        ),
        (
            workspace_root / "multiagent-system" / "agents" / "deployer" / "agent.py",
            workspace_root / "multiagent-system" / "agents" / "deployer" / "prompts" / "system.md",
        ),
    ]

    missing_files: List[str] = []
    missing_agent_tokens: Dict[str, List[str]] = {}
    empty_prompts: List[str] = []

    for agent_path, prompt_path in required_pairs:
        if not agent_path.exists():
            missing_files.append(str(agent_path))
            continue
        if not prompt_path.exists():
            missing_files.append(str(prompt_path))
            continue

        agent_text = agent_path.read_text(encoding="utf-8")
        prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        if not prompt_text:
            empty_prompts.append(str(prompt_path))

        expected_tokens = ["_load_system_prompt", "self.system_prompt", "prompts", "system.md"]
        missing_tokens = [token for token in expected_tokens if token not in agent_text]
        if missing_tokens:
            missing_agent_tokens[str(agent_path)] = missing_tokens

    return {
        "task_id": "MAS-39",
        "ok": len(missing_files) == 0 and len(empty_prompts) == 0 and len(missing_agent_tokens) == 0,
        "check": "agent_system_prompts",
        "details": {
            "missing_files": missing_files,
            "empty_prompts": empty_prompts,
            "missing_agent_tokens": missing_agent_tokens,
        },
    }


async def _pm_task_specific_validation(task_id: str) -> Dict[str, Any]:
    validators = {
        "MAS-20": _pm_validate_task_20,
        "MAS-34": _pm_validate_task_34,
        "MAS-35": _pm_validate_task_35,
        "MAS-36": _pm_validate_task_36,
        "MAS-37": _pm_validate_task_37,
        "MAS-38": _pm_validate_task_38,
        "MAS-39": _pm_validate_task_39,
        "MAS-40": _pm_validate_task_40,
        "MAS-41": _pm_validate_task_41,
        "MAS-42": _pm_validate_task_42,
        "MAS-43": _pm_validate_task_43,
        "MAS-44": _pm_validate_task_44,
        "MAS-45": _pm_validate_task_45,
        "MAS-46": _pm_validate_task_46,
        "MAS-47": _pm_validate_task_47,
        "MAS-48": _pm_validate_task_48,
        "MAS-49": _pm_validate_task_49,
        "MAS-50": _pm_validate_task_50,
        "MAS-51": _pm_validate_task_51,
        "MAS-52": _pm_validate_task_52,
        "MAS-33": _pm_validate_task_33,
    }
    validator = validators.get(task_id)
    if validator is None:
        return {
            "task_id": task_id,
            "ok": False,
            "reason": "No task-specific validator implemented yet.",
        }
    try:
        result = validator()
        if asyncio.iscoroutine(result):
            return await result
        return result
    except Exception as exc:
        return {
            "task_id": task_id,
            "ok": False,
            "reason": f"Task-specific validation failed: {type(exc).__name__}: {exc}",
        }


def _pm_load_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
        return parsed if isinstance(parsed, dict) else {"raw": value}
    return {"raw": value}


def _pm_task_family(task_id: str, summary: str) -> str:
    lowered = f"{task_id} {summary}".lower()
    if any(token in lowered for token in ("auth", "api key", "credencial", "secret", "seguridad")):
        return "security"
    if any(token in lowered for token in ("test", "suite", "regresion", "metric", "alerta", "quality")):
        return "quality"
    if any(token in lowered for token in ("whatsapp", "meta", "whisper", "audio")):
        return "whatsapp"
    if any(token in lowered for token in ("mcp", "filesystem", "git server", "exec server", "http server", "tool")):
        return "mcp"
    if any(token in lowered for token in ("db", "database", "postgres", "migracion")):
        return "data"
    if any(token in lowered for token in ("ci/cd", "deploy", "repo", "github", "render", "pipeline")):
        return "delivery"
    return "platform"


def _pm_build_subtasks(task_id: str, summary: str) -> List[str]:
    family = _pm_task_family(task_id, summary)
    templates = {
        "security": [
            "Inspeccionar el estado actual y localizar puntos expuestos.",
            "Diseñar la mitigacion minima segura y compatible con el sistema actual.",
            "Aplicar el cambio tecnico y endurecer los flujos afectados.",
            "Verificar la mitigacion con evidencia reproducible antes de cerrar Jira.",
        ],
        "quality": [
            "Identificar los flujos criticos y el alcance de regresion.",
            "Definir los casos de prueba y los criterios de aceptacion.",
            "Implementar la cobertura y dejar ruta de ejecucion clara.",
            "Ejecutar comprobaciones y registrar evidencia verificable.",
        ],
        "whatsapp": [
            "Definir el contrato de entrada y salida del canal WhatsApp.",
            "Implementar la integracion faltante en el workflow correspondiente.",
            "Conectar la nueva rama del flujo con planner y respuesta final.",
            "Comprobar el recorrido end-to-end antes del cierre.",
        ],
        "mcp": [
            "Definir el contrato de la herramienta y sus limites de seguridad.",
            "Implementar el comportamiento esperado con errores auditables.",
            "Integrar la herramienta en el orquestador y el flujo de ejecucion.",
            "Validar operacion y aislamiento antes de cerrar la tarea.",
        ],
        "data": [
            "Analizar la persistencia actual y la compatibilidad del cambio.",
            "Diseñar la migracion o configuracion con criterio de no downtime.",
            "Aplicar el cambio y documentar el rollback.",
            "Validar el estado final y la continuidad operativa.",
        ],
        "delivery": [
            "Definir el contrato de despliegue o automatizacion requerido.",
            "Implementar la parte faltante del pipeline o de la integracion.",
            "Conectar evidencias y trazabilidad con Jira y run_id.",
            "Verificar el comportamiento final con una comprobacion operativa.",
        ],
        "platform": [
            "Analizar el alcance tecnico y los archivos implicados.",
            "Diseñar el cambio minimo con criterios de aceptacion claros.",
            "Implementar la solucion y revisar riesgos de regresion.",
            "Validar el comportamiento final antes de cerrar Jira.",
        ],
    }
    return templates.get(family, templates["platform"])


def _pm_build_execution_brief(task_id: str, summary: str) -> Dict[str, Any]:
    family = _pm_task_family(task_id, summary)
    subtasks = _pm_build_subtasks(task_id, summary)
    return {
        "task_id": task_id,
        "summary": summary,
        "family": family,
        "subtasks": subtasks,
        "subagents": ["planner", "developer", "reviewer", "deployer"],
        "close_policy": "No cerrar Jira sin review aprobado, despliegue validado y checks tecnicos en verde.",
    }


async def _pm_call_multiagent_stage(stage: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    return await _request_multiagent("POST", f"/agents/{stage}", json_body=payload)


async def _pm_execute_task_autonomously(issue_key: str, task_id: str, summary: str) -> Dict[str, Any]:
    transition_resp = await jira_transition_issue(issue_key=issue_key, transition_name="En curso")
    if not transition_resp.get("ok"):
        return {
            "ok": False,
            "issue_key": issue_key,
            "task_id": task_id,
            "closed": False,
            "error": "Could not transition issue to In Progress",
            "transition": transition_resp,
        }

    brief = _pm_build_execution_brief(task_id, summary)
    await jira_add_comment(issue_key, "Autonomous PM execution plan:\n" + json.dumps(brief, ensure_ascii=True))

    run_resp = await multiagent_create_run()
    run_data = run_resp.get("data") if isinstance(run_resp, dict) else {}
    run_id = (run_data or {}).get("run_id") if isinstance(run_data, dict) else None
    if not run_resp.get("ok") or not run_id:
        return {
            "ok": False,
            "issue_key": issue_key,
            "task_id": task_id,
            "closed": False,
            "error": "Could not create run_id for autonomous execution",
            "run": run_resp,
        }

    planner = await _pm_call_multiagent_stage("planner", {"task": json.dumps(brief, ensure_ascii=True), "run_id": run_id})
    planner_data = planner.get("data") if isinstance(planner, dict) else {}
    plan_payload = _pm_load_json((planner_data or {}).get("plan"))

    developer_input: Dict[str, Any] = plan_payload or brief
    developer = await _pm_call_multiagent_stage("developer", {"plan": developer_input, "run_id": run_id})
    developer_data = developer.get("data") if isinstance(developer, dict) else {}
    code_payload = _pm_load_json((developer_data or {}).get("code"))

    reviewer = await _pm_call_multiagent_stage("reviewer", {"code": code_payload, "run_id": run_id})
    reviewer_data = reviewer.get("data") if isinstance(reviewer, dict) else {}
    review_payload = _pm_load_json((reviewer_data or {}).get("review"))
    approved = bool((reviewer_data or {}).get("approved"))

    if not approved:
        developer_input = {
            **developer_input,
            "review_feedback": review_payload.get("findings", []),
            "retry_cycle": 1,
        }
        developer = await _pm_call_multiagent_stage("developer", {"plan": developer_input, "run_id": run_id})
        developer_data = developer.get("data") if isinstance(developer, dict) else {}
        code_payload = _pm_load_json((developer_data or {}).get("code"))
        reviewer = await _pm_call_multiagent_stage("reviewer", {"code": code_payload, "run_id": run_id})
        reviewer_data = reviewer.get("data") if isinstance(reviewer, dict) else {}
        review_payload = _pm_load_json((reviewer_data or {}).get("review"))
        approved = bool((reviewer_data or {}).get("approved"))

    deployer: Dict[str, Any]
    deployer_data: Dict[str, Any]
    deploy_payload: Dict[str, Any]
    deploy_status = "blocked"
    if approved:
        deployer = await _pm_call_multiagent_stage(
            "deployer",
            {
                "review": {
                    "approved": approved,
                    "review": review_payload,
                    "code": code_payload,
                    "task_id": task_id,
                },
                "run_id": run_id,
            },
        )
        deployer_data = deployer.get("data") if isinstance(deployer, dict) else {}
        deploy_payload = _pm_load_json((deployer_data or {}).get("deployment"))
        deploy_status = str((deployer_data or {}).get("status", deploy_payload.get("status", "blocked")))
    else:
        deployer = {"ok": False, "status_code": 0, "error": "review_not_approved"}
        deployer_data = {}
        deploy_payload = {"status": "blocked", "reason": "Reviewer did not approve changes."}

    tests = await _pm_validation_suite(task_id)
    run_snapshot = await multiagent_get_run(run_id)
    run_state = run_snapshot.get("data") if isinstance(run_snapshot, dict) else {}

    task_validation = await _pm_task_specific_validation(task_id)

    can_close = all(
        [
            bool(planner.get("ok")),
            bool(developer.get("ok")),
            bool(reviewer.get("ok")),
            approved,
            deploy_status in {"validated", "completed", "success"},
            bool(tests.get("ok")),
            bool(task_validation.get("ok")),
        ]
    )

    evidence = {
        "task_id": task_id,
        "run_id": run_id,
        "brief": brief,
        "planner": {"ok": planner.get("ok"), "plan": plan_payload},
        "developer": {"ok": developer.get("ok"), "code": code_payload},
        "reviewer": {"ok": reviewer.get("ok"), "approved": approved, "review": review_payload},
        "deployer": {"ok": deployer.get("ok"), "status": deploy_status, "deployment": deploy_payload},
        "tests": tests,
        "task_validation": task_validation,
        "run_state": run_state,
    }
    await jira_add_comment(issue_key, "Autonomous PM evidence:\n" + json.dumps(evidence, ensure_ascii=True))

    if can_close:
        done_resp = await jira_transition_issue(issue_key=issue_key, transition_name="Listo")
        return {
            "ok": bool(done_resp.get("ok")),
            "issue_key": issue_key,
            "task_id": task_id,
            "closed": bool(done_resp.get("ok")),
            "run_id": run_id,
            "planner": planner,
            "developer": developer,
            "reviewer": reviewer,
            "deployer": deployer,
            "tests": tests,
            "transition_done": done_resp,
        }

    return {
        "ok": False,
        "issue_key": issue_key,
        "task_id": task_id,
        "closed": False,
        "run_id": run_id,
        "planner": planner,
        "developer": developer,
        "reviewer": reviewer,
        "deployer": deployer,
        "tests": tests,
        "error": "Autonomous execution did not satisfy close policy. Issue left in progress.",
    }


async def _pm_execute_task(issue_key: str, task_id: str, summary: str) -> Dict[str, Any]:
    transition_resp = await jira_transition_issue(issue_key=issue_key, transition_name="En curso")
    if not transition_resp.get("ok"):
        return {
            "ok": False,
            "issue_key": issue_key,
            "task_id": task_id,
            "error": "Could not transition issue to In Progress",
            "transition": transition_resp,
        }

    body = {
        "text": f"PM execution for {task_id}: {summary}",
        "jira_issue_key": issue_key,
        "jira_base_url": _jira_base_url(),
        "jira_email": _jira_email(),
        "jira_api_token": _jira_api_token(),
    }
    pipeline: Dict[str, Any] = {"ok": False, "status_code": 0, "error": "not_executed"}
    for _ in range(2):
        pipeline = await _request("POST", "/webhook/whatsapp-intake", json_body=body, use_api_key=False)
        if pipeline.get("ok"):
            break
        await asyncio.sleep(2)

    tests = await _pm_validation_suite(task_id)
    can_close = bool(pipeline.get("ok")) and bool(tests.get("ok"))

    evidence = {
        "task_id": task_id,
        "pipeline": {
            "ok": pipeline.get("ok"),
            "status_code": pipeline.get("status_code"),
            "data": pipeline.get("data"),
        },
        "tests": tests,
    }
    await jira_add_comment(issue_key, f"PM evidence:\n{json.dumps(evidence, ensure_ascii=True)}")

    if can_close:
        done_resp = await jira_transition_issue(issue_key=issue_key, transition_name="Listo")
        return {
            "ok": bool(done_resp.get("ok")),
            "issue_key": issue_key,
            "task_id": task_id,
            "closed": bool(done_resp.get("ok")),
            "pipeline": pipeline,
            "tests": tests,
            "transition_done": done_resp,
        }

    return {
        "ok": False,
        "issue_key": issue_key,
        "task_id": task_id,
        "closed": False,
        "pipeline": pipeline,
        "tests": tests,
        "error": "Execution or tests failed. Issue left in progress for review.",
    }


@mcp.tool()
async def n8n_health_check() -> Dict[str, Any]:
    """Check if n8n responds on the health endpoint."""
    return await _request("GET", "/healthz", use_api_key=False)


@mcp.tool()
async def n8n_list_workflows(limit: int = 50, active: Optional[bool] = None) -> Dict[str, Any]:
    """List workflows from n8n."""
    params: Dict[str, Any] = {"limit": max(1, min(limit, 250))}
    result = await _request("GET", "/api/v1/workflows", params=params)

    if result.get("ok") and active is not None:
        data = result.get("data")
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            data["data"] = [w for w in data["data"] if w.get("active") is active]
    return result


@mcp.tool()
async def n8n_get_workflow(workflow_id: str) -> Dict[str, Any]:
    """Get one workflow by id."""
    return await _request("GET", f"/api/v1/workflows/{workflow_id}")


@mcp.tool()
async def n8n_list_executions(
    limit: int = 20,
    workflow_id: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List workflow executions with optional filters."""
    params: Dict[str, Any] = {"limit": max(1, min(limit, 250))}
    if workflow_id:
        params["workflowId"] = workflow_id
    if status:
        params["status"] = status

    return await _request("GET", "/api/v1/executions", params=params)


@mcp.tool()
async def n8n_get_execution(execution_id: str, include_data: bool = False) -> Dict[str, Any]:
    """Get details of one execution."""
    params = {"includeData": str(include_data).lower()}
    return await _request("GET", f"/api/v1/executions/{execution_id}", params=params)


@mcp.tool()
async def n8n_set_workflow_active(workflow_id: str, active: bool) -> Dict[str, Any]:
    """Activate or deactivate a workflow.

    Requires N8N_MCP_ENABLE_WRITE=true.
    """
    if not _write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Write operations are disabled. Set N8N_MCP_ENABLE_WRITE=true",
        }

    state_path = "activate" if active else "deactivate"
    return await _request(
        "POST",
        f"/api/v1/workflows/{workflow_id}/{state_path}",
    )


@mcp.tool()
async def n8n_trigger_webhook(
    webhook_path: str,
    payload: Optional[Dict[str, Any]] = None,
    method: str = "POST",
) -> Dict[str, Any]:
    """Trigger a public n8n webhook path, e.g. 'planner-entry'.

    This calls /webhook/<path> on N8N_BASE_URL.
    """
    if not _write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Write operations are disabled. Set N8N_MCP_ENABLE_WRITE=true",
        }

    safe_method = method.upper().strip()
    if safe_method not in {"POST", "GET"}:
        return {
            "ok": False,
            "status_code": 0,
            "error": "Unsupported method. Use GET or POST",
        }

    path = f"/webhook/{webhook_path.lstrip('/')}"
    return await _request(
        safe_method,
        path,
        json_body=payload or {},
        use_api_key=False,
    )


@mcp.tool()
async def multiagent_create_run() -> Dict[str, Any]:
    """Create a new run_id in the multiagent backend."""
    return await _request_multiagent("POST", "/runs")


@mcp.tool()
async def multiagent_get_run(run_id: str) -> Dict[str, Any]:
    """Get one run status from multiagent backend."""
    return await _request_multiagent("GET", f"/runs/{run_id}")


@mcp.tool()
async def multiagent_list_runs(limit: int = 20) -> Dict[str, Any]:
    """List recent runs from multiagent backend."""
    return await _request_multiagent("GET", "/runs", params={"limit": max(1, min(limit, 200))})


@mcp.tool()
async def jira_health_check() -> Dict[str, Any]:
    """Validate Jira credentials and connectivity using /myself endpoint."""
    return await _request_jira("GET", "/rest/api/3/myself")


@mcp.tool()
async def jira_create_issue(
    summary: str,
    description: str,
    issue_type: str = "Task",
    project_key: Optional[str] = None,
    parent_key: Optional[str] = None,
    labels: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Create a Jira issue.

    Requires JIRA_MCP_ENABLE_WRITE=true.
    """
    if not _jira_write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Jira write operations are disabled. Set JIRA_MCP_ENABLE_WRITE=true",
        }

    resolved_project_key = (project_key or "").strip() or _jira_project_key()
    if not resolved_project_key:
        return {
            "ok": False,
            "status_code": 0,
            "error": "project_key is required (argument or JIRA_PROJECT_KEY env)",
        }

    fields: Dict[str, Any] = {
        "project": {"key": resolved_project_key},
        "summary": summary,
        "description": _jira_doc(description),
        "issuetype": {"name": issue_type},
    }
    if labels:
        fields["labels"] = labels
    if parent_key:
        fields["parent"] = {"key": parent_key}

    return await _request_jira("POST", "/rest/api/3/issue", json_body={"fields": fields})


@mcp.tool()
async def jira_list_issues(
    jql: Optional[str] = None,
    limit: int = 20,
    project_key: Optional[str] = None,
) -> Dict[str, Any]:
    """List Jira issues using JQL."""
    resolved_project_key = (project_key or "").strip() or _jira_project_key()
    if jql:
        query = jql
    elif resolved_project_key:
        query = f"project={resolved_project_key} ORDER BY created DESC"
    else:
        query = "ORDER BY created DESC"

    params: Dict[str, Any] = {
        "jql": query,
        "maxResults": max(1, min(limit, 100)),
        "fields": "summary,status,issuetype,priority,assignee,created,updated",
    }
    return await _request_jira("GET", "/rest/api/3/search", params=params)


@mcp.tool()
async def jira_add_comment(issue_key: str, comment: str) -> Dict[str, Any]:
    """Add a comment to a Jira issue.

    Requires JIRA_MCP_ENABLE_WRITE=true.
    """
    if not _jira_write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Jira write operations are disabled. Set JIRA_MCP_ENABLE_WRITE=true",
        }

    path = f"/rest/api/3/issue/{issue_key}/comment"
    return await _request_jira("POST", path, json_body={"body": _jira_doc(comment)})


@mcp.tool()
async def jira_transition_issue(
    issue_key: str,
    transition_id: Optional[str] = None,
    transition_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Transition a Jira issue by transition id or transition name.

    Requires JIRA_MCP_ENABLE_WRITE=true.
    """
    if not _jira_write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Jira write operations are disabled. Set JIRA_MCP_ENABLE_WRITE=true",
        }

    resolved_transition_id = (transition_id or "").strip()
    if not resolved_transition_id:
        if not transition_name:
            return {
                "ok": False,
                "status_code": 0,
                "error": "transition_id or transition_name is required",
            }
        transitions_resp = await _request_jira(
            "GET",
            f"/rest/api/3/issue/{issue_key}/transitions",
        )
        if not transitions_resp.get("ok"):
            return transitions_resp

        data = transitions_resp.get("data")
        transitions = data.get("transitions", []) if isinstance(data, dict) else []
        for candidate in transitions:
            if str(candidate.get("name", "")).lower().strip() == transition_name.lower().strip():
                resolved_transition_id = str(candidate.get("id", ""))
                break

        if not resolved_transition_id:
            return {
                "ok": False,
                "status_code": 0,
                "error": f"Transition not found by name: {transition_name}",
                "available": transitions,
            }

    path = f"/rest/api/3/issue/{issue_key}/transitions"
    return await _request_jira(
        "POST",
        path,
        json_body={"transition": {"id": resolved_transition_id}},
    )


@mcp.tool()
async def jira_link_run(issue_key: str, run_id: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Add a Jira comment linking a ticket to a multiagent run_id.

    Requires JIRA_MCP_ENABLE_WRITE=true.
    """
    base = _multiagent_base_url()
    run_url = f"{base}/runs/{run_id}"
    text = f"Linked run_id: {run_id}\nRun URL: {run_url}"
    if note:
        text = f"{text}\nNote: {note}"
    return await jira_add_comment(issue_key=issue_key, comment=text)


@mcp.tool()
async def pm_sync_backlog() -> Dict[str, Any]:
    """Ensure all PM epics and tasks exist in Jira; create missing issues only."""
    if not _jira_write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Jira write operations are disabled. Set JIRA_MCP_ENABLE_WRITE=true",
        }

    index = await _pm_build_index()
    epic_index = index["epic"]
    task_index = index["mas"]

    created_epics: List[str] = []
    created_tasks: List[str] = []

    epic_key_by_code: Dict[str, str] = {}
    for epic in PM_EPICS:
        code = epic["code"]
        existing = epic_index.get(code)
        if existing:
            epic_key_by_code[code] = existing["key"]
            continue

        created = await _request_jira(
            "POST",
            "/rest/api/3/issue",
            json_body={
                "fields": {
                    "project": {"key": _jira_project_key()},
                    "summary": f"{code} {epic['name']}",
                    "description": _jira_doc("Epic tecnico sincronizado por PM agent."),
                    "issuetype": {"name": "Epic"},
                    "priority": {"id": _priority_id(epic["priority"])},
                    "labels": ["mas-backlog-v2", "epic", code.lower()],
                }
            },
        )
        if created.get("ok") and isinstance(created.get("data"), dict):
            key = created["data"].get("key")
            if key:
                epic_key_by_code[code] = key
                created_epics.append(key)

    for task in PM_TASKS:
        task_id = task["id"]
        if task_id in task_index:
            continue
        parent_key = epic_key_by_code.get(task["epic"])
        if not parent_key:
            continue

        labels = ["mas-backlog-v2", task_id.lower(), task["epic"].lower()]
        created = await _request_jira(
            "POST",
            "/rest/api/3/issue",
            json_body={
                "fields": {
                    "project": {"key": _jira_project_key()},
                    "summary": f"{task_id} {task['summary']}",
                    "description": _jira_doc("Tarea tecnica sincronizada por PM agent."),
                    "issuetype": {"name": "Tarea"},
                    "priority": {"id": _priority_id(task["priority"])},
                    "labels": labels,
                    "parent": {"key": parent_key},
                }
            },
        )
        if created.get("ok") and isinstance(created.get("data"), dict):
            key = created["data"].get("key")
            if key:
                created_tasks.append(key)

    return {
        "ok": True,
        "created_epics": created_epics,
        "created_tasks": created_tasks,
        "catalog_epics": len(PM_EPICS),
        "catalog_tasks": len(PM_TASKS),
    }


@mcp.tool()
async def pm_plan_backlog(limit: int = 10) -> Dict[str, Any]:
    """Plan next executable Jira tasks by priority and dependency readiness."""
    index = await _pm_build_index()
    mas = index["mas"]

    done_ids = set()
    for task_id, issue in mas.items():
        fields = issue.get("fields") if isinstance(issue, dict) else None
        status_name = ""
        if isinstance(fields, dict):
            status_obj = fields.get("status")
            if isinstance(status_obj, dict):
                status_name = str(status_obj.get("name", ""))
        if _issue_status_done(status_name):
            done_ids.add(task_id)

    pending: List[Dict[str, Any]] = []
    priority_score = {"High": 1, "Medium": 2, "Low": 3}
    for item in PM_TASKS:
        issue = mas.get(item["id"])
        if not issue:
            pending.append({
                "task_id": item["id"],
                "issue_key": None,
                "summary": item["summary"],
                "priority": item["priority"],
                "deps": item["deps"],
                "deps_ready": False,
                "reason": "Issue missing in Jira. Run pm_sync_backlog first.",
            })
            continue

        fields = issue.get("fields") if isinstance(issue, dict) else {}
        status_name = ""
        if isinstance(fields, dict) and isinstance(fields.get("status"), dict):
            status_name = str(fields["status"].get("name", ""))
        if _issue_status_done(status_name):
            continue

        deps_ready = all(dep in done_ids for dep in item["deps"])
        pending.append({
            "task_id": item["id"],
            "issue_key": issue.get("key"),
            "summary": item["summary"],
            "priority": item["priority"],
            "deps": item["deps"],
            "deps_ready": deps_ready,
            "status": status_name,
            "blocked": ("blocked" in ((fields.get("labels") if isinstance(fields, dict) else []) or [])),
        })

    pending.sort(key=lambda x: (0 if x.get("deps_ready") else 1, priority_score.get(x.get("priority", "Medium"), 2), x.get("task_id", "")))
    ready = [item for item in pending if item.get("deps_ready") and not item.get("blocked")]

    return {
        "ok": True,
        "pending_total": len(pending),
        "ready_total": len(ready),
        "pending": pending,
        "next": ready[: max(1, min(limit, 50))],
    }


@mcp.tool()
async def pm_execute_backlog(max_tasks: int = 1, dry_run: bool = False) -> Dict[str, Any]:
    """Execute next backlog tasks with PM lifecycle: in progress -> evidence -> done."""
    if not _jira_write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Jira write operations are disabled. Set JIRA_MCP_ENABLE_WRITE=true",
        }

    plan = await pm_plan_backlog(limit=max_tasks)
    next_items = plan.get("next", []) if isinstance(plan, dict) else []
    if not isinstance(next_items, list) or not next_items:
        return {"ok": True, "message": "No executable tasks found.", "plan": plan, "executed": []}

    if dry_run:
        return {"ok": True, "dry_run": True, "plan": plan}

    executed: List[Dict[str, Any]] = []
    for item in next_items[: max(1, min(max_tasks, 20))]:
        issue_key = item.get("issue_key")
        task_id = item.get("task_id")
        summary = item.get("summary")
        if not issue_key or not task_id:
            executed.append({"ok": False, "error": "Missing issue key or task id", "item": item})
            continue
        result = await _pm_execute_task(issue_key=issue_key, task_id=task_id, summary=str(summary or ""))
        executed.append(result)

    all_ok = all(bool(item.get("ok")) for item in executed)
    return {
        "ok": all_ok,
        "executed": executed,
        "count": len(executed),
    }


@mcp.tool()
async def pm_execute_backlog_autonomously(max_tasks: int = 1, dry_run: bool = False) -> Dict[str, Any]:
    """Execute next backlog tasks with autonomous PM orchestration and mandatory validation before closing Jira."""
    if not _jira_write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Jira write operations are disabled. Set JIRA_MCP_ENABLE_WRITE=true",
        }

    plan = await pm_plan_backlog(limit=max_tasks)
    next_items = plan.get("next", []) if isinstance(plan, dict) else []
    if not isinstance(next_items, list) or not next_items:
        return {"ok": True, "message": "No executable tasks found.", "plan": plan, "executed": []}

    if dry_run:
        preview = []
        for item in next_items[: max(1, min(max_tasks, 20))]:
            preview.append(_pm_build_execution_brief(item.get("task_id", ""), str(item.get("summary", ""))))
        return {"ok": True, "dry_run": True, "plan": plan, "execution_briefs": preview}

    executed: List[Dict[str, Any]] = []
    for item in next_items[: max(1, min(max_tasks, 20))]:
        issue_key = item.get("issue_key")
        task_id = item.get("task_id")
        summary = item.get("summary")
        if not issue_key or not task_id:
            executed.append({"ok": False, "error": "Missing issue key or task id", "item": item})
            continue
        result = await _pm_execute_task_autonomously(issue_key=issue_key, task_id=task_id, summary=str(summary or ""))
        executed.append(result)

    return {
        "ok": all(bool(item.get("ok")) for item in executed),
        "executed": executed,
        "count": len(executed),
    }


@mcp.tool()
async def pm_find_backlog_duplicates() -> Dict[str, Any]:
    """Find duplicated backlog issues by MAS label and epic label."""
    issues = await _jira_search("project=" + _jira_project_key() + " AND labels=mas-backlog-v2 ORDER BY created ASC")
    by_logical_id: Dict[str, List[str]] = {}

    for issue in issues:
        key = issue.get("key")
        fields = issue.get("fields") if isinstance(issue, dict) else None
        if not key or not isinstance(fields, dict):
            continue
        labels = fields.get("labels") or []
        if not isinstance(labels, list):
            labels = []

        issue_type = ""
        if isinstance(fields.get("issuetype"), dict):
            issue_type = str(fields["issuetype"].get("name", ""))

        logical_ids: List[str] = []
        for label in labels:
            if isinstance(label, str) and label.startswith("mas-") and label[4:].isdigit():
                logical_ids.append("MAS-" + label[4:])
            if isinstance(label, str) and label.startswith("epic-"):
                if issue_type.lower() == "epic":
                    logical_ids.append(label.replace("epic-", "EPIC-").upper())

        for logical in logical_ids:
            by_logical_id.setdefault(logical, []).append(key)

    duplicates = {
        logical: keys
        for logical, keys in by_logical_id.items()
        if len(keys) > 1
    }

    return {
        "ok": True,
        "duplicate_groups": duplicates,
        "duplicate_groups_count": len(duplicates),
    }


@mcp.tool()
async def pm_cleanup_backlog_duplicates(apply_changes: bool = False) -> Dict[str, Any]:
    """Mark duplicate backlog issues, keeping the oldest issue key as canonical."""
    if apply_changes and not _jira_write_enabled():
        return {
            "ok": False,
            "status_code": 0,
            "error": "Jira write operations are disabled. Set JIRA_MCP_ENABLE_WRITE=true",
        }

    duplicates_resp = await pm_find_backlog_duplicates()
    groups = duplicates_resp.get("duplicate_groups", {}) if isinstance(duplicates_resp, dict) else {}
    if not isinstance(groups, dict) or not groups:
        return {"ok": True, "message": "No duplicates found.", "actions": []}

    actions: List[Dict[str, Any]] = []

    def _key_num(issue_key: str) -> int:
        try:
            return int(issue_key.split("-")[1])
        except Exception:
            return 10**9

    for logical_id, issue_keys in groups.items():
        if not isinstance(issue_keys, list) or len(issue_keys) < 2:
            continue
        ordered = sorted([str(k) for k in issue_keys], key=_key_num)
        canonical = ordered[0]
        for duplicate_key in ordered[1:]:
            action = {
                "logical_id": logical_id,
                "canonical": canonical,
                "duplicate": duplicate_key,
                "applied": False,
            }
            if apply_changes:
                await _request_jira(
                    "PUT",
                    f"/rest/api/3/issue/{duplicate_key}",
                    json_body={
                        "update": {
                            "labels": [
                                {"add": "duplicate"},
                                {"add": "mas-backlog-v2-duplicate"},
                            ]
                        }
                    },
                )
                await jira_add_comment(
                    issue_key=duplicate_key,
                    comment=f"Marked as duplicate by PM agent. Canonical issue: {canonical}",
                )
                action["applied"] = True
            actions.append(action)

    return {
        "ok": True,
        "apply_changes": apply_changes,
        "actions_count": len(actions),
        "actions": actions,
    }


if __name__ == "__main__":
    mcp.run()
