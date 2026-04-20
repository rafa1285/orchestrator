"""Isolated command execution MCP server with strict allowlist."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Dict, List

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("exec-whitelist-mcp")


def _working_dir() -> Path:
    raw = os.getenv("EXEC_WORKDIR", "").strip()
    if not raw:
        raise RuntimeError("EXEC_WORKDIR is required")
    path = Path(raw).resolve()
    if not path.exists() or not path.is_dir():
        raise RuntimeError(f"Invalid EXEC_WORKDIR: {path}")
    return path


def _allowed_commands() -> List[str]:
    raw = os.getenv("EXEC_ALLOWED_COMMANDS", "echo,pwd,whoami,python,node,npm,git").strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


def _blocked_tokens() -> List[str]:
    return ["&&", "||", ";", "|", ">", "<", "`"]


def _validate_command(command_line: str) -> List[str]:
    if any(token in command_line for token in _blocked_tokens()):
        raise RuntimeError("Blocked shell metacharacter detected")

    parts = shlex.split(command_line)
    if not parts:
        raise RuntimeError("Command cannot be empty")

    allowed = _allowed_commands()
    if parts[0] not in allowed:
        raise RuntimeError(f"Command not in whitelist: {parts[0]}")
    return parts


@mcp.tool()
def exec_allowed_commands() -> Dict[str, List[str]]:
    return {"allowed_commands": _allowed_commands()}


@mcp.tool()
def exec_run(command_line: str, timeout_seconds: int = 20) -> Dict[str, str | int | bool]:
    args = _validate_command(command_line)
    timeout = max(1, min(120, int(timeout_seconds)))

    proc = subprocess.run(
        args,
        cwd=str(_working_dir()),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
