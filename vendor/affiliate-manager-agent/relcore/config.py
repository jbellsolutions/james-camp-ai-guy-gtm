"""Paths and settings for each run mode.

Modes: agent (Hermes on the droplet, user trp), plugin (Claude Code session, files under ./trp), approve (relapprove),
send (relsend), test (everything under RELCORE_ROOT, used by tests and the sample).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = Path(os.environ.get("TRP_REPO") or PKG.parent)
DEFAULTS = PKG / "defaults"


@dataclass
class Paths:
    mode: str
    home: Path            # relationship data owned by this process's user (rel.sqlite3, config, call-inbox)
    vault: Path           # the Obsidian vault (cards are written here by the agent-side process only)
    spool: Path | None    # /var/lib/relcore/spool (None in plugin mode)
    control: Path | None  # /var/lib/relcore/control (stop mirror)
    stop_primary: Path | None  # ~/.hermes/trp/state/EXTERNAL_WRITES_STOPPED (agent side)
    approve_home: Path | None = None
    send_home: Path | None = None
    key_file: Path | None = None
    employee: str = ""
    etc: Path | None = None  # root-owned config: owners.json, sender.json, approvals.json (never trp-writable)
    extra: dict = field(default_factory=dict)

    @property
    def rel_db(self) -> Path:
        return self.home / "rel.sqlite3"

    @property
    def approvals_db(self) -> Path:
        return (self.approve_home or self.home) / "approvals.sqlite3"

    @property
    def sends_db(self) -> Path:
        return (self.send_home or self.home) / "sends.sqlite3"

    def config_file(self, name: str) -> Path:
        own = self.home / "config" / name
        return own if own.exists() else DEFAULTS / name


def resolve(mode: str | None = None) -> Paths:
    env = os.environ
    mode = "test" if env.get("RELCORE_MODE") == "test" else (mode or env.get("RELCORE_MODE", "agent"))
    if mode == "test":
        root = Path(env["RELCORE_ROOT"])
        return Paths(mode, root / "home", root / "vault", root / "spool", root / "control",
                     root / "state" / "EXTERNAL_WRITES_STOPPED", root / "approve", root / "send",
                     root / "approval.key", env.get("RELCORE_EMPLOYEE", ""), root / "etc")
    if mode == "plugin":
        project = next((v for v in (env.get("RELCORE_PROJECT"), env.get("CLAUDE_PROJECT_DIR"))
                        if v and "${" not in v), None)  # an unexpanded ${VAR} from a plugin config is ignored
        base = Path(env.get("RELCORE_BASE") or Path(project or os.getcwd()) / "trp")
        home = Path(env.get("RELCORE_HOME") or base / "relationship")
        vault = Path(env.get("RELCORE_VAULT") or base / "vault")  # drafts-only installs point this at an Obsidian vault
        return Paths(mode, home, vault, None, None, Path(env.get("RELCORE_STOP_FILE") or base / "EXTERNAL_WRITES_STOPPED"),
                     employee=env.get("RELCORE_EMPLOYEE", ""))
    hermes = Path(env.get("HERMES_HOME") or Path.home() / ".hermes")
    trp_home = Path(env.get("TRP_HOME") or hermes / "trp")
    lib = Path(env.get("RELCORE_LIB") or "/var/lib/relcore")
    return Paths(
        mode,
        home=Path(env.get("RELCORE_HOME") or trp_home / "private-business" / "relationship"),
        vault=Path(env.get("TRP_VAULT") or Path.home() / "trp-vault"),
        spool=Path(env.get("RELCORE_SPOOL") or lib / "spool"),
        control=Path(env.get("RELCORE_CONTROL") or lib / "control"),
        stop_primary=trp_home / "state" / "EXTERNAL_WRITES_STOPPED",
        approve_home=Path(env.get("RELAPPROVE_HOME") or "/var/lib/relapprove"),
        send_home=Path(env.get("RELSEND_HOME") or "/var/lib/relsend"),
        key_file=Path(env.get("RELCORE_KEY_FILE") or "/etc/relcore/approval.key"),
        employee=env.get("RELCORE_EMPLOYEE", ""),
        etc=Path(env.get("RELCORE_ETC") or "/etc/relcore"),
    )


def load_json(paths: Paths, name: str) -> dict:
    return json.loads(paths.config_file(name).read_text())


def settings(paths: Paths) -> dict:
    """relationship.json with defaults filled in."""
    base = json.loads((DEFAULTS / "relationship.json").read_text())
    own = paths.home / "config" / "relationship.json"
    if own.exists():
        base.update(json.loads(own.read_text()))
    return base


def schema(paths: Paths) -> dict:
    return load_json(paths, "profile-schema.json")


def root_json(paths: Paths, name: str, default=None):
    """owners.json, sender.json, approvals.json from the root-owned config folder. Never from trp's own files."""
    if not paths.etc:
        return default
    path = paths.etc / name
    if not path.exists():
        return default
    return json.loads(path.read_text())


def read_key(path: Path) -> bytes:
    """The approval key is 64 hex characters (install/bootstrap-droplet.sh). Readable only by relsig members."""
    text = path.read_text().strip()
    key = bytes.fromhex(text)
    if len(key) < 32:
        raise SystemExit("approval key is too short")
    return key
