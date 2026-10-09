#!/usr/bin/env python3
"""Atomic managed-file update node for one Docker-hosted AI Guy agent."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any


SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def locate_deployment(home: Path) -> Path:
    descriptor = home / ".config/ai-guy-agent/go-to-market.json"
    if not descriptor.is_file():
        raise ValueError("deployment descriptor is missing")
    value = json.loads(descriptor.read_text())
    deploy = Path(value["deployment_dir"]).expanduser().resolve()
    if not (deploy / ".env").is_file():
        raise ValueError("deployment directory has no private .env")
    return deploy


def managed_paths(deploy: Path) -> list[Path]:
    data = deploy / "hermes/data"
    return [
        deploy / "compose.yml",
        deploy / "bin",
        deploy / "sync",
        data / "config.yaml",
        data / "SOUL.md",
        data / "skills/ai-guy",
        data / "plugins/latitude-observer",
        data / "managed/services",
        data / "managed/agent-templates",
        data / "managed/policies",
        data / "managed/scripts",
        data / "managed/installed-manifest.json",
    ]


def copy_path(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def snapshot(deploy: Path, state: Path, run_id: str) -> Path:
    backup = state / "backups" / run_id
    if backup.exists():
        raise ValueError("a backup already exists for this run")
    files = backup / "files"
    files.mkdir(parents=True, mode=0o700)
    records: list[dict[str, Any]] = []
    for path in managed_paths(deploy):
        relative = path.relative_to(deploy)
        exists = path.exists() or path.is_symlink()
        records.append({"path": str(relative), "existed": exists})
        if exists:
            copy_path(path, files / relative)
    manifest = backup / "manifest.json"
    manifest.write_text(json.dumps({"paths": records}, indent=2) + "\n")
    manifest.chmod(0o600)
    return backup


def restore(deploy: Path, backup: Path) -> None:
    manifest = json.loads((backup / "manifest.json").read_text())
    for record in manifest["paths"]:
        target = deploy / record["path"]
        remove_path(target)
        if record["existed"]:
            copy_path(backup / "files" / record["path"], target)


def compose(deploy: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return run(["docker", "compose", "--env-file", ".env", *arguments], cwd=deploy)


def emit(value: dict[str, Any]) -> None:
    print("AI_GUY_RESULT=" + json.dumps(value, separators=(",", ":"), sort_keys=True))


def deploy_release(args: argparse.Namespace, home: Path, state: Path) -> int:
    release = args.release.resolve()
    required = [
        release / "services/fleet_node.py",
        release / "services/install_profiles.py",
        release / "orgo/verify.sh",
        release / "fleet/release.json",
    ]
    if not all(path.is_file() for path in required):
        raise ValueError("release is missing the managed update contract")
    static = run([str(release / "orgo/verify.sh"), "--static"], cwd=release)
    if static.returncode:
        raise RuntimeError("release failed static verification")

    deploy = locate_deployment(home)
    backup = snapshot(deploy, state, args.run_id)
    try:
        installed = run(
            [str(release / "new-agent.sh"), str(deploy / ".env")],
            cwd=release,
        )
        if installed.returncode:
            raise RuntimeError(installed.stderr.strip() or "installer failed")
        verified = run([str(deploy / "bin/verify.sh"), "--allow-unconnected"], cwd=deploy)
        if verified.returncode:
            raise RuntimeError(verified.stderr.strip() or "runtime verification failed")
    except Exception:
        restore(deploy, backup)
        compose(deploy, "up", "-d", "--force-recreate", "hermes")
        emit({
            "action": "deploy",
            "status": "rolled-back",
            "run_id": args.run_id,
            "target": args.target_id,
        })
        raise

    release_data = json.loads((release / "fleet/release.json").read_text())
    current = {
        "run_id": args.run_id,
        "target": args.target_id,
        "stack_version": release_data["stack_version"],
        "deployment": str(deploy),
        "updated_at": int(time.time()),
    }
    current_path = state / "current.json"
    current_path.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    current_path.chmod(0o600)
    emit({"action": "deploy", "status": "healthy", **current})
    return 0


def rollback(args: argparse.Namespace, home: Path, state: Path) -> int:
    deploy = locate_deployment(home)
    backup = state / "backups" / args.run_id
    if not (backup / "manifest.json").is_file():
        raise ValueError("no rollback snapshot exists for this run")
    restore(deploy, backup)
    recreated = compose(deploy, "up", "-d", "--force-recreate", "hermes")
    if recreated.returncode:
        raise RuntimeError("restored files but the prior container did not restart")
    emit({
        "action": "rollback",
        "status": "restored",
        "run_id": args.run_id,
        "target": args.target_id,
    })
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("deploy", "rollback"))
    parser.add_argument("--release", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--home", type=Path, default=Path.home())
    args = parser.parse_args()
    if not SAFE_ID.fullmatch(args.target_id) or not RUN_ID.fullmatch(args.run_id):
        raise ValueError("invalid target or run identifier")
    if args.action == "deploy" and args.release is None:
        raise ValueError("deploy requires --release")

    home = args.home.expanduser().resolve()
    state = home / ".local/state/ai-guy-fleet/go-to-market"
    state.mkdir(parents=True, mode=0o700)
    os.chmod(state, 0o700)
    with (state / "update.lock").open("w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "deploy":
            return deploy_release(args, home, state)
        return rollback(args, home, state)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BlockingIOError:
        print("Another agent update is already running.", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print(f"Fleet update stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
