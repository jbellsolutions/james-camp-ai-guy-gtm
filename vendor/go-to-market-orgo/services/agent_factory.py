#!/usr/bin/env python3
"""Approval-gated persistent profile factory for the AI Guy templates."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
import uuid


NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
MODEL_KEYS = {
    "AI_GATEWAY_API_KEY", "ANTHROPIC_API_KEY", "CEREBRAS_API_KEY",
    "COHERE_API_KEY", "DEEPSEEK_API_KEY", "FIREWORKS_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
    "MODEL_API_KEY", "NOUS_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
    "TOGETHER_API_KEY", "XAI_API_KEY", "ZAI_API_KEY",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def write_private(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def canonical_hash(value: dict[str, Any]) -> str:
    protected = {
        key: item
        for key, item in value.items()
        if key not in {"status", "approval", "activated_at", "proposal_hash"}
    }
    body = json.dumps(protected, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


class Factory:
    def __init__(self) -> None:
        self.hermes_home = Path(os.environ.get("HERMES_HOME", "/opt/data")).expanduser().resolve()
        default_assets = self.hermes_home / "managed"
        self.assets = Path(os.environ.get("AI_GUY_FACTORY_ASSETS_DIR", default_assets)).expanduser().resolve()
        default_state = self.assets / "state"
        self.state = Path(os.environ.get("AI_GUY_FACTORY_STATE_DIR", default_state)).expanduser().resolve()
        self.policy = load(self.assets / "policies/agent-factory.json")
        self.proposals = self.state / "proposals"

    def template(self, template_id: str) -> tuple[Path, dict[str, Any]]:
        if template_id not in self.policy["allowed_template_ids"]:
            raise ValueError("Template is not allowlisted.")
        directory = self.assets / "agent-templates" / template_id
        metadata = load(directory / "template.json")
        if metadata.get("template_id") != template_id or not (directory / "SOUL.md").is_file():
            raise ValueError("Template failed its identity check.")
        return directory, metadata

    def list_templates(self) -> list[dict[str, Any]]:
        rows = []
        for template_id in self.policy["allowed_template_ids"]:
            _, item = self.template(template_id)
            rows.append({
                key: item[key]
                for key in ("template_id", "display_name", "description", "capabilities")
            })
        return rows

    def propose(
        self,
        template_id: str,
        need: str,
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        if not need.strip():
            raise ValueError("A concrete business need is required.")
        _, template = self.template(template_id)
        name = (profile_name or template["default_profile_name"]).strip()
        if not NAME.fullmatch(name) or name == "default":
            raise ValueError("Profile name must use lowercase letters, numbers, and dashes.")
        if (self.hermes_home / "profiles" / name).exists():
            raise ValueError("That profile already exists.")
        proposal_id = "ap_" + uuid.uuid4().hex[:12]
        item = {
            "schema_version": 1,
            "proposal_id": proposal_id,
            "status": "proposed",
            "created_at": now(),
            "template_id": template_id,
            "profile_name": name,
            "display_name": template["display_name"],
            "description": template["description"],
            "manager": "default",
            "need": need.strip(),
            "capabilities": template["capabilities"],
            "human_approval_required": True,
            "credentials": [],
            "external_writes": False,
        }
        item["proposal_hash"] = canonical_hash(item)
        write_private(self.proposals / f"{proposal_id}.json", item)
        return item

    def get(self, proposal_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"ap_[0-9a-f]{12}", proposal_id):
            raise ValueError("Invalid proposal ID.")
        path = self.proposals / f"{proposal_id}.json"
        if not path.is_file():
            raise ValueError("Proposal not found.")
        return load(path)

    def list(self) -> list[dict[str, Any]]:
        if not self.proposals.exists():
            return []
        return [load(path) for path in sorted(self.proposals.glob("ap_*.json"))]

    def approve(self, proposal_id: str, approved_by: str) -> dict[str, Any]:
        item = self.get(proposal_id)
        if item["status"] != "proposed" or item.get("proposal_hash") != canonical_hash(item):
            raise ValueError("Only an unchanged proposal can be approved.")
        if not sys.stdin.isatty():
            raise ValueError("Owner approval requires an interactive private terminal.")
        expected = f"APPROVE {proposal_id}"
        entered = input(f"Type {expected} to create this persistent worker: ")
        if entered != expected:
            raise ValueError("Approval phrase did not match.")
        item["status"] = "approved"
        item["approval"] = {
            "approved_by": approved_by.strip() or "owner",
            "approved_at": now(),
            "proposal_hash": item["proposal_hash"],
            "one_time": True,
        }
        write_private(self.proposals / f"{proposal_id}.json", item)
        return item

    @staticmethod
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(args, text=True, capture_output=True)
        if result.returncode:
            message = result.stderr.strip() or result.stdout.strip() or "Hermes command failed."
            raise RuntimeError(message)
        return result

    @classmethod
    def config_set(cls, profile: str, key: str, value: Any) -> None:
        command = ["hermes"] if profile == "default" else ["hermes", "-p", profile]
        encoded = value if isinstance(value, str) else json.dumps(value, separators=(",", ":"))
        cls.run(*command, "config", "set", key, encoded)

    @staticmethod
    def scrub_profile_env(home: Path) -> None:
        path = home / ".env"
        if not path.exists():
            return
        kept = []
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                kept.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in MODEL_KEYS or key.startswith("HERMES_MODEL_"):
                kept.append(line)
        path.write_text("\n".join(kept) + ("\n" if kept else ""))
        path.chmod(0o600)

    def active_routes(self) -> tuple[list[str], dict[str, Any]]:
        active = [item for item in self.list() if item.get("status") == "active"]
        names = [item["profile_name"] for item in active]
        routes = {
            item["profile_name"]: {
                "profile": item["profile_name"],
                "path": item["profile_name"],
                "tenant": item["profile_name"],
                "name": item["display_name"],
                "description": item["description"],
                "advertised_toolsets": item["capabilities"],
                "timeout": 300,
            }
            for item in active
        }
        return names, routes

    def activate(self, proposal_id: str) -> dict[str, Any]:
        item = self.get(proposal_id)
        if item["status"] == "active":
            return item
        approval = item.get("approval") or {}
        if item["status"] != "approved" or approval.get("proposal_hash") != item.get("proposal_hash"):
            raise ValueError("A matching owner approval record is required.")
        if item.get("proposal_hash") != canonical_hash(item):
            raise ValueError("Proposal changed after approval.")
        profile_root = self.hermes_home / "profiles"
        active_count = sum(1 for path in profile_root.glob("*") if path.is_dir())
        if active_count >= int(self.policy["max_active_named_profiles"]):
            raise ValueError("Active profile cap reached.")

        directory, template = self.template(item["template_id"])
        name = item["profile_name"]
        profile_home = profile_root / name
        if profile_home.exists():
            raise ValueError("Profile name is now in use.")
        self.run(
            "hermes", "profile", "create", name, "--clone",
            "--description", item["description"],
        )
        self.scrub_profile_env(profile_home)
        shutil.copy2(directory / "SOUL.md", profile_home / "SOUL.md")
        shared = self.hermes_home / "skills" / "ai-guy"
        if shared.exists():
            shutil.copytree(shared, profile_home / "skills" / "ai-guy", dirs_exist_ok=True)

        settings: dict[str, Any] = {
            "agent.bot_mode_protocol": True,
            "approvals.mode": "manual",
            "approvals.destructive_slash_confirm": True,
            "skills.write_approval": True,
            "skills.guard_agent_created": True,
            "tool_loop_guardrails.hard_stop_enabled": True,
            "terminal.home_mode": "profile",
            "gateway.multiplex_profiles": False,
            "gateway.platforms.slack.enabled": False,
            "gateway.platforms.telegram.enabled": False,
            "gateway.platforms.a2a.enabled": False,
            "mcp_servers": {},
            "platform_toolsets.cli": template["toolsets"],
            "platform_toolsets.a2a": ["session_search", "memory", "file", "web", "kanban"],
        }
        for key, value in settings.items():
            self.config_set(name, key, value)

        item["status"] = "active"
        item["activated_at"] = now()
        write_private(self.proposals / f"{proposal_id}.json", item)
        names, routes = self.active_routes()
        self.config_set("default", "gateway.multiplex_profile_allowlist", names)
        self.config_set("default", "gateway.platforms.a2a.extra.agents", routes)
        return item


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    propose = sub.add_parser("propose")
    propose.add_argument("template_id")
    propose.add_argument("--need", required=True)
    propose.add_argument("--name")
    approve = sub.add_parser("approve")
    approve.add_argument("proposal_id")
    approve.add_argument("--approved-by", required=True)
    activate = sub.add_parser("activate")
    activate.add_argument("proposal_id")
    show = sub.add_parser("show")
    show.add_argument("proposal_id")
    sub.add_parser("list")
    args = parser.parse_args()
    factory = Factory()
    if args.command == "propose":
        result = factory.propose(args.template_id, args.need, args.name)
    elif args.command == "approve":
        result = factory.approve(args.proposal_id, args.approved_by)
    elif args.command == "activate":
        result = factory.activate(args.proposal_id)
    elif args.command == "show":
        result = factory.get(args.proposal_id)
    else:
        result = factory.list()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Agent Factory stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
