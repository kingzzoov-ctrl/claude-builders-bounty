#!/usr/bin/env python3
"""Claude Code PreToolUse hook that blocks destructive Bash commands.

The hook reads the Claude Code hook JSON payload from stdin, inspects Bash tool
commands, and emits a structured deny decision when a dangerous command is
found. Blocked attempts are appended to ~/.claude/hooks/blocked.log.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_PATH = Path.home() / ".claude" / "hooks" / "blocked.log"

DANGEROUS_MESSAGE = (
    "Blocked destructive Bash command before execution. This command matched "
    "a configured safety rule: {reason}. Review the command and use a safer, "
    "more targeted alternative before retrying."
)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*(?=\n|$)", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return sql


def has_delete_without_where(command: str) -> bool:
    sql = normalize_space(strip_sql_comments(command)).lower()
    for match in re.finditer(r"\bdelete\s+from\s+[`\"\[]?[\w.\]-]+[`\"\]]?", sql):
        tail = sql[match.end() :]
        stop_positions = [pos for pos in (tail.find(";"), tail.find("&&"), tail.find("||")) if pos != -1]
        statement_tail = tail[: min(stop_positions)] if stop_positions else tail
        if not re.search(r"\bwhere\b", statement_tail):
            return True
    return False


def detect_destructive_pattern(command: str) -> str | None:
    compact = normalize_space(command)
    lowered = compact.lower()

    # Required shell patterns. Token-aware checks catch common spelling variants
    # while avoiding harmless strings like `echo rm -rf` where possible.
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = compact.split()

    for index, token in enumerate(tokens):
        if token == "rm":
            flags = "".join(t[1:] for t in tokens[index + 1 :] if t.startswith("-") and not t.startswith("--"))
            long_flags = {t for t in tokens[index + 1 :] if t.startswith("--")}
            has_recursive = "r" in flags or "R" in flags or "--recursive" in long_flags
            has_force = "f" in flags or "--force" in long_flags
            if has_recursive and has_force:
                return "rm recursive+force (for example rm -rf)"

    if re.search(r"\bgit\s+push\b[^\n;|&]*(?:--force(?:-with-lease)?\b|-f\b|\+[^\s]+)", compact):
        return "git push --force"

    if re.search(r"\bdrop\s+table\b", lowered):
        return "DROP TABLE"

    if re.search(r"\btruncate\b", lowered):
        return "TRUNCATE"

    if has_delete_without_where(command):
        return "DELETE FROM without a WHERE clause"

    return None


def extract_command(payload: dict[str, Any]) -> str | None:
    tool_name = str(payload.get("tool_name") or payload.get("toolName") or "")
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}

    if tool_name and tool_name.lower() not in {"bash", "shell"}:
        return None

    if isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd") or tool_input.get("script")
        if isinstance(command, str):
            return command
    elif isinstance(tool_input, str):
        return tool_input

    # Be permissive for local tests or format changes.
    command = payload.get("command") or payload.get("cmd")
    return command if isinstance(command, str) else None


def project_path(payload: dict[str, Any]) -> str:
    for key in ("cwd", "project_path", "projectPath"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
    if isinstance(tool_input, dict):
        for key in ("cwd", "project_path", "projectPath"):
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                return value
    return os.getcwd()


def log_blocked(command: str, path: str, reason: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempted_command": command,
        "project_path": path,
        "reason": reason,
    }
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def deny(reason: str) -> None:
    message = DANGEROUS_MESSAGE.format(reason=reason)
    print(json.dumps({"permissionDecision": "deny", "permissionDecisionReason": message}))


def allow() -> None:
    print(json.dumps({"permissionDecision": "allow"}))


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # Malformed hook input should not break normal Claude Code usage.
        allow()
        return 0

    command = extract_command(payload)
    if not command:
        allow()
        return 0

    reason = detect_destructive_pattern(command)
    if not reason:
        allow()
        return 0

    path = project_path(payload)
    log_blocked(command, path, reason)
    deny(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
