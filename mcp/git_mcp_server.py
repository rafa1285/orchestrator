"""Minimal-permission Git MCP server with command allowlist."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, List

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("git-minimal-mcp")


def _repo_root() -> Path:
    raw = os.getenv("GIT_REPO_ROOT", "").strip()
    if not raw:
        raise RuntimeError("GIT_REPO_ROOT is required")
    root = Path(raw).resolve()
    if not root.exists() or not root.is_dir():
        raise RuntimeError(f"Invalid GIT_REPO_ROOT: {root}")
    if not (root / ".git").exists():
        raise RuntimeError(f"GIT_REPO_ROOT is not a git repository: {root}")
    return root


def _allowed_commands() -> List[str]:
    raw = os.getenv("GIT_ALLOWED_COMMANDS", "status,log,diff,show,branch,rev-parse").strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


def _read_only() -> bool:
    return os.getenv("GIT_READ_ONLY", "true").lower() == "true"


def _run_git(args: List[str]) -> Dict[str, str | int | bool]:
    if not args:
        raise RuntimeError("Git command is required")

    subcommand = args[0]
    allowed = _allowed_commands()
    if subcommand not in allowed:
        raise RuntimeError(f"Git command not allowed: {subcommand}")

    if _read_only() and subcommand in {"commit", "push", "reset", "checkout", "merge", "rebase", "tag"}:
        raise RuntimeError(f"Write git command blocked in read-only mode: {subcommand}")

    proc = subprocess.run(
        ["git", *args],
        cwd=str(_repo_root()),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


@mcp.tool()
def git_status_short() -> Dict[str, str | int | bool]:
    return _run_git(["status", "--short"])


@mcp.tool()
def git_log_oneline(max_count: int = 10) -> Dict[str, str | int | bool]:
    count = max(1, min(100, int(max_count)))
    return _run_git(["log", f"--max-count={count}", "--oneline"])


@mcp.tool()
def git_diff(ref: str = "HEAD") -> Dict[str, str | int | bool]:
    return _run_git(["diff", ref])


@mcp.tool()
def git_show(revision: str = "HEAD") -> Dict[str, str | int | bool]:
    return _run_git(["show", revision, "--stat"])


if __name__ == "__main__":
    mcp.run(transport="stdio")
