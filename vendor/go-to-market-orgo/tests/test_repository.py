from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import re


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class RepositoryTests(unittest.TestCase):
    def test_runtime_and_permission_contract(self) -> None:
        compose = (ROOT / "compose.yml").read_text()
        factory = (ROOT / "services/agent_factory.py").read_text()
        env = (ROOT / "agent.example.env").read_text()
        self.assertIn("v2026.9.11@sha256:9469b3e78b9545b6d576eb8887a95352e9a0ea83730eaf31431cf862ca1010e1", compose)
        self.assertNotIn("/var/run/docker.sock", compose)
        self.assertNotIn("entrypoint:", compose)
        self.assertIn("${HERMES_MEM_LIMIT:-3g}", compose)
        self.assertIn('"mcp_servers": {}', factory)
        self.assertIn("ENABLE_AGENT_BUNDLE=false", env)
        self.assertIn("HERMES_MEM_LIMIT=3g", env)

    def test_small_host_recovery_is_installed(self) -> None:
        installer = (ROOT / "new-agent.sh").read_text()
        provisioner = (ROOT / "provision-vps.sh").read_text()
        verifier = (ROOT / "bin/verify.sh").read_text()
        watchdog = (ROOT / "bin/watchdog.sh").read_text()
        self.assertIn("install_watchdog_schedule", installer)
        self.assertIn("crontab", installer)
        self.assertIn("ensure_cron_service", provisioner)
        self.assertIn("ensure_small_host_swap", provisioner)
        self.assertIn("/swapfile", provisioner)
        self.assertIn("$BASE_DIR/bin/watchdog.sh", verifier)
        self.assertIn(".State.Status", watchdog)

    def test_no_committed_secrets(self) -> None:
        patterns = [
            re.compile(r"sk_live_[A-Za-z0-9]{12,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{12,}"),
            re.compile(r"fw_[A-Za-z0-9]{20,}"),
        ]
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                self.assertIsNone(pattern.search(text), str(path.relative_to(ROOT)))

    def test_release_and_policy(self) -> None:
        release = json.loads((ROOT / "fleet/release.json").read_text())
        policy = json.loads((ROOT / "policies/agent-factory.json").read_text())
        self.assertEqual(release["stack_version"], "2026.09.13.1")
        self.assertTrue(policy["persistent_activation_requires_human_approval"])
        self.assertIn("arbitrary-command", policy["never_exposed_as_factory_tools"])

    def test_factory_fails_closed_without_approval(self) -> None:
        factory_module = load_module("factory_test", ROOT / "services/agent_factory.py")
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            assets = Path(temporary) / "assets"
            (home / "profiles").mkdir(parents=True)
            shutil.copytree(ROOT / "agent-templates", assets / "agent-templates")
            shutil.copytree(ROOT / "policies", assets / "policies")
            old = dict(os.environ)
            try:
                os.environ["HERMES_HOME"] = str(home)
                os.environ["AI_GUY_FACTORY_ASSETS_DIR"] = str(assets)
                os.environ["AI_GUY_FACTORY_STATE_DIR"] = str(Path(temporary) / "state")
                factory = factory_module.Factory()
                item = factory.propose("prospect-research", "Recurring account research")
                with self.assertRaises(ValueError):
                    factory.activate(item["proposal_id"])
                with self.assertRaises(ValueError):
                    factory.approve(item["proposal_id"], "owner")
            finally:
                os.environ.clear()
                os.environ.update(old)

    def test_asset_update_preserves_customized_file(self) -> None:
        installer = load_module("installer_test", ROOT / "services/install_assets.py")
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "hermes"
            old_argv = list(__import__("sys").argv)
            try:
                __import__("sys").argv = [
                    "install_assets.py", "--root", str(ROOT), "--home", str(home)
                ]
                self.assertEqual(installer.main(), 0)
                soul = home / "SOUL.md"
                soul.write_text("customer customization\n")
                self.assertEqual(installer.main(), 0)
                self.assertEqual(soul.read_text(), "customer customization\n")
            finally:
                __import__("sys").argv = old_argv

    def test_latitude_defaults_to_metadata_only(self) -> None:
        observer = load_module(
            "latitude_test", ROOT / "plugins/latitude-observer/__init__.py"
        )
        old = os.environ.pop("LATITUDE_CAPTURE_MODE", None)
        try:
            self.assertEqual(observer._capture_mode(), "metadata")
            self.assertIsNone(observer._content("private conversation"))
        finally:
            if old is not None:
                os.environ["LATITUDE_CAPTURE_MODE"] = old

    def test_business_tools_are_current_and_fail_closed(self) -> None:
        config = (ROOT / "hermes/config.template.yaml").read_text()
        configure = (ROOT / "bin/configure-managed.sh").read_text()
        self.assertIn("url: '${COMPOSIO_MCP_URL}'", config)
        self.assertIn("mcp_servers.composio.enabled true", configure)
        self.assertIn("api/v3.1/mcp/${COMPOSIO_MCP_SERVER_ID}", configure)
        self.assertNotIn("backend.composio.dev/v3/mcp", configure)
        self.assertNotIn("api.latitude.so/v1/mcp", config)


if __name__ == "__main__":
    unittest.main()
