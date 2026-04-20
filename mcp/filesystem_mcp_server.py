"""Sandboxed filesystem MCP server scoped to configured project roots."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("filesystem-sandbox-mcp")


def _allowed_projects() -> Dict[str, Path]:
    """Parse ALLOWED_PROJECTS as name=absolute_path pairs separated by ';'."""
    raw = os.getenv("ALLOWED_PROJECTS", "").strip()
    if not raw:
        raise RuntimeError("ALLOWED_PROJECTS is required. Example: orchestrator=C:/repo/orchestrator;n8n=C:/repo/n8n")

    projects: Dict[str, Path] = {}
    for chunk in raw.split(";"):
        piece = chunk.strip()
        if not piece:
            continue
        if "=" not in piece:
            raise RuntimeError(f"Invalid ALLOWED_PROJECTS entry: {piece}")
        name, root = piece.split("=", 1)
        key = name.strip()
        path = Path(root.strip()).resolve()
        if not key:
            raise RuntimeError("Project name cannot be empty in ALLOWED_PROJECTS")
        if not path.exists() or not path.is_dir():
            raise RuntimeError(f"Project root does not exist or is not a directory: {path}")
        projects[key] = path

    if not projects:
        raise RuntimeError("No valid projects configured in ALLOWED_PROJECTS")
    return projects


def _resolve_safe_path(project: str, relative_path: str) -> Path:
    projects = _allowed_projects()
    if project not in projects:
        raise RuntimeError(f"Project not allowed: {project}")

    base = projects[project]
    target = (base / relative_path).resolve()
    if target != base and base not in target.parents:
        raise RuntimeError("Path escapes sandbox")
    return target


@mcp.tool()
def fs_list_projects() -> Dict[str, List[str]]:
    projects = _allowed_projects()
    return {"projects": sorted(projects.keys())}


@mcp.tool()
def fs_list_dir(project: str, relative_path: str = ".") -> Dict[str, List[str]]:
    target = _resolve_safe_path(project, relative_path)
    if not target.exists() or not target.is_dir():
        raise RuntimeError(f"Directory not found: {target}")

    items: List[str] = []
    for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        items.append(f"{child.name}/" if child.is_dir() else child.name)
    return {"project": project, "path": str(target), "items": items}


@mcp.tool()
def fs_read_text(project: str, relative_path: str, max_chars: int = 20000) -> Dict[str, str]:
    target = _resolve_safe_path(project, relative_path)
    if not target.exists() or not target.is_file():
        raise RuntimeError(f"File not found: {target}")

    text = target.read_text(encoding="utf-8")
    clipped = text[: max(1, max_chars)]
    return {"project": project, "path": str(target), "content": clipped}


@mcp.tool()
def fs_write_text(project: str, relative_path: str, content: str) -> Dict[str, str]:
    target = _resolve_safe_path(project, relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"project": project, "path": str(target), "status": "written"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
