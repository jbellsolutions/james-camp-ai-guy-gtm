#!/usr/bin/env python3
"""MCP surface for the approval-gated Agent Factory."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_factory import Factory  # noqa: E402
from mcp.server import MCPServer  # noqa: E402


server = MCPServer(
    "ai-guy-go-to-market-factory",
    instructions=(
        "List templates and create proposals. Persistent activation fails closed "
        "until a separate owner approval exists. No delete, credential, billing, "
        "infrastructure, permission, or arbitrary-command tool is exposed."
    ),
)


@server.tool()
def agent_templates() -> str:
    """List allowlisted worker profiles."""
    return json.dumps(Factory().list_templates(), indent=2)


@server.tool()
def agent_propose(template_id: str, need: str, profile_name: str = "") -> str:
    """Propose a persistent worker; this does not approve or activate it."""
    item = Factory().propose(template_id, need, profile_name or None)
    return json.dumps({
        "proposal_id": item["proposal_id"],
        "status": item["status"],
        "profile_name": item["profile_name"],
        "human_approval_required": True,
        "next_step": "Escalate to the owner with the need, permissions, and profile name.",
    }, indent=2)


@server.tool()
def agent_proposals() -> str:
    """List proposals without secrets."""
    keys = ("proposal_id", "template_id", "profile_name", "status", "created_at", "activated_at")
    return json.dumps([{key: item.get(key) for key in keys} for item in Factory().list()], indent=2)


@server.tool()
def agent_activate(proposal_id: str) -> str:
    """Activate only an unchanged proposal with a matching approval record."""
    item = Factory().activate(proposal_id)
    return json.dumps({
        "proposal_id": item["proposal_id"],
        "status": item["status"],
        "profile_name": item["profile_name"],
    }, indent=2)


if __name__ == "__main__":
    asyncio.run(server.run_stdio_async())
