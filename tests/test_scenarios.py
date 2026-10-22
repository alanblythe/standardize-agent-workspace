"""Comprehensive real-world scenario test suite for standardize-agent-workspace."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path so scripts.standardize can be imported directly
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.standardize import WorkspaceStandardizer


class TestStandardizeScenarios(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="agy_std_test_")
        self.root = Path(self.test_dir)
        self.script_path = REPO_ROOT / "scripts" / "standardize.py"

    def tearDown(self):
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [sys.executable, str(self.script_path), "--root", str(self.root)] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True)

    # --------------------------------------------------------------------------
    # Scenario 1: Legacy Claude Code Repository
    # --------------------------------------------------------------------------
    def test_scenario_1_legacy_claude_code(self):
        """Tests standardizing a repo that currently only uses Claude Code."""
        # Setup files
        claude_md = self.root / "CLAUDE.md"
        claude_md.write_text("# Claude Guidelines\n- Always run npm test\n- Keep functions small\n", encoding="utf-8")

        skill_dir = self.root / ".claude" / "skills" / "deploy-tool"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: deploy-tool\ndescription: Cloud deployment\n---\nRun deploy\n", encoding="utf-8")

        mcp_json = self.root / ".mcp.json"
        mcp_json.write_text(json.dumps({
            "mcpServers": {
                "fetch": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-fetch"]
                }
            }
        }, indent=2), encoding="utf-8")

        pkg_json = self.root / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "my-project",
            "scripts": {
                "test": "jest",
                "build": "tsc"
            }
        }, indent=2), encoding="utf-8")

        # 1. Execute Dry-Run via CLI
        res_dry = self._run_cli("--dry-run", "--json")
        self.assertEqual(res_dry.returncode, 0, f"Dry-run failed: {res_dry.stderr}")
        data_dry = json.loads(res_dry.stdout)
        self.assertEqual(data_dry["status"], "ok")
        self.assertTrue(data_dry["dry_run"])
        self.assertFalse(data_dry["has_conflict"])
        self.assertIn("CLAUDE.md", data_dry["instructions_detected"])
        self.assertIn("deploy-tool", data_dry["skills_detected"].get("claude", []))
        self.assertGreaterEqual(data_dry["changes_count"], 5)

        # Assert no disk writes occurred in dry-run
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / ".gemini" / "mcp_config.json").exists())

        # 2. Execute Apply via CLI
        res_apply = self._run_cli("--apply", "--json")
        self.assertEqual(res_apply.returncode, 0, f"Apply failed: {res_apply.stderr}")
        data_apply = json.loads(res_apply.stdout)
        self.assertEqual(data_apply["status"], "ok")

        # Assert disk mutations
        agents_md = self.root / "AGENTS.md"
        self.assertTrue(agents_md.is_file())
        self.assertIn("Always run npm test", agents_md.read_text(encoding="utf-8"))

        # Symlinks exist
        self.assertTrue(claude_md.is_symlink())
        self.assertEqual(os.readlink(claude_md), "AGENTS.md")
        gemini_md = self.root / "GEMINI.md"
        self.assertTrue(gemini_md.is_symlink())
        self.assertEqual(os.readlink(gemini_md), "AGENTS.md")

        # Skills moved to .agents/skills/
        target_skill = self.root / ".agents" / "skills" / "deploy-tool" / "SKILL.md"
        self.assertTrue(target_skill.is_file())
        self.assertFalse((self.root / ".claude" / "skills" / "deploy-tool").exists())

        # MCP configs compiled
        gemini_mcp = self.root / ".gemini" / "mcp_config.json"
        self.assertTrue(gemini_mcp.is_file())
        gemini_data = json.loads(gemini_mcp.read_text(encoding="utf-8"))
        self.assertIn("fetch", gemini_data["mcpServers"])

        codex_toml = self.root / ".codex" / "config.toml"
        self.assertTrue(codex_toml.is_file())
        self.assertIn("[mcp_servers.fetch]", codex_toml.read_text(encoding="utf-8"))

        # Settings permissions seeded
        gemini_settings = self.root / ".gemini" / "settings.json"
        self.assertTrue(gemini_settings.is_file())
        settings_data = json.loads(gemini_settings.read_text(encoding="utf-8"))
        allows = settings_data["permissions"]["allow"]
        self.assertIn("run_command(npm test)", allows)
        self.assertIn("mcp(fetch/*)", allows)

    # --------------------------------------------------------------------------
    # Scenario 2: Legacy OpenAI Codex Repository
    # --------------------------------------------------------------------------
    def test_scenario_2_legacy_codex_repo(self):
        """Tests standardizing a repo that currently only uses Codex."""
        agents_md = self.root / "AGENTS.md"
        agents_md.write_text("# Codex Rules\n- Use Python 3.11+\n", encoding="utf-8")

        codex_skill = self.root / ".codex" / "skills" / "linter"
        codex_skill.mkdir(parents=True)
        (codex_skill / "SKILL.md").write_text("---\nname: linter\ndescription: run lint\n---\nLint code\n", encoding="utf-8")

        codex_toml = self.root / ".codex" / "config.toml"
        codex_toml.parent.mkdir(parents=True, exist_ok=True)
        codex_toml.write_text(
            '[mcp_servers.database]\ncommand = "docker"\nargs = ["run", "-i", "db-mcp"]\n',
            encoding="utf-8"
        )

        res_apply = self._run_cli("--apply", "--json")
        self.assertEqual(res_apply.returncode, 0)

        # Assert AGENTS.md preserved
        self.assertTrue(agents_md.is_file())
        self.assertIn("Use Python 3.11+", agents_md.read_text(encoding="utf-8"))

        # Assert symlinks created for Claude and Gemini
        claude_md = self.root / "CLAUDE.md"
        self.assertTrue(claude_md.is_symlink())
        self.assertEqual(os.readlink(claude_md), "AGENTS.md")

        gemini_md = self.root / "GEMINI.md"
        self.assertTrue(gemini_md.is_symlink())
        self.assertEqual(os.readlink(gemini_md), "AGENTS.md")

        # Skill moved to .agents/skills/
        self.assertTrue((self.root / ".agents" / "skills" / "linter" / "SKILL.md").is_file())

        # Root .mcp.json extracted from Codex TOML
        root_mcp = self.root / ".mcp.json"
        self.assertTrue(root_mcp.is_file())
        mcp_data = json.loads(root_mcp.read_text(encoding="utf-8"))
        self.assertIn("database", mcp_data["mcpServers"])
        self.assertEqual(mcp_data["mcpServers"]["database"]["command"], "docker")

        # Antigravity .gemini/mcp_config.json generated
        self.assertTrue((self.root / ".gemini" / "mcp_config.json").is_file())

    # --------------------------------------------------------------------------
    # Scenario 3: Legacy Antigravity Repository
    # --------------------------------------------------------------------------
    def test_scenario_3_legacy_antigravity_repo(self):
        """Tests standardizing a repo that currently only uses Antigravity."""
        gemini_md = self.root / "GEMINI.md"
        gemini_md.write_text("# Gemini Architecture\n- Use gRPC for backend services\n", encoding="utf-8")

        gemini_dir = self.root / ".gemini"
        gemini_dir.mkdir(parents=True)
        (gemini_dir / "mcp_config.json").write_text(json.dumps({
            "mcpServers": {
                "local-docs": {
                    "command": "python3",
                    "args": ["serve_docs.py"]
                }
            }
        }), encoding="utf-8")

        res_apply = self._run_cli("--apply", "--json")
        self.assertEqual(res_apply.returncode, 0)

        # Assert AGENTS.md created from GEMINI.md
        agents_md = self.root / "AGENTS.md"
        self.assertTrue(agents_md.is_file())
        self.assertIn("Use gRPC for backend services", agents_md.read_text(encoding="utf-8"))

        # Assert GEMINI.md is now a symlink pointing to AGENTS.md
        self.assertTrue(gemini_md.is_symlink())
        self.assertEqual(os.readlink(gemini_md), "AGENTS.md")

        # Assert CLAUDE.md symlink
        self.assertTrue((self.root / "CLAUDE.md").is_symlink())

        # Assert .mcp.json and .codex/config.toml generated
        self.assertTrue((self.root / ".mcp.json").is_file())
        self.assertTrue((self.root / ".codex" / "config.toml").is_file())

    # --------------------------------------------------------------------------
    # Scenario 4: Conflicting Multi-Tool Repo (Interactive Resolution)
    # --------------------------------------------------------------------------
    def test_scenario_4_conflicts_and_resolution_strategies(self):
        """Tests detecting divergent rules and applying resolution strategies."""
        (self.root / "CLAUDE.md").write_text("# Claude Policy\nIndent with 2 spaces.\n", encoding="utf-8")
        (self.root / "GEMINI.md").write_text("# Gemini Policy\nIndent with 4 tabs.\n", encoding="utf-8")

        # 1. Verify conflict detection (exit code 2)
        res_conflict = self._run_cli("--dry-run", "--json")
        self.assertEqual(res_conflict.returncode, 2)
        conflict_data = json.loads(res_conflict.stdout)
        self.assertEqual(conflict_data["status"], "conflict")
        self.assertIn("CLAUDE.md", conflict_data["conflict_files"])
        self.assertIn("GEMINI.md", conflict_data["conflict_files"])

        # 2. Test pick:claude strategy
        res_pick_claude = self._run_cli("--apply", "--strategy", "pick:claude", "--json")
        self.assertEqual(res_pick_claude.returncode, 0)
        agents_txt = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Indent with 2 spaces", agents_txt)
        self.assertNotIn("Indent with 4 tabs", agents_txt)

        # 3. Test merge strategy on new conflict
        (self.root / "CLAUDE.md").unlink()
        (self.root / "GEMINI.md").unlink()
        (self.root / "CLAUDE.md").write_text("# Security Rules\nNever commit .env files.\n", encoding="utf-8")
        (self.root / "GEMINI.md").write_text("# Style Rules\nPrefer functional components.\n", encoding="utf-8")

        res_merge = self._run_cli("--apply", "--strategy", "merge", "--json")
        self.assertEqual(res_merge.returncode, 0)
        merged_txt = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Never commit .env files", merged_txt)
        self.assertIn("Prefer functional components", merged_txt)

        # 4. Test --merged-file argument (explicit AI synthesis draft)
        merged_draft = self.root / "custom_draft.md"
        merged_draft.write_text("# Unified AI Handbook\n- Single synthesized rule.\n", encoding="utf-8")

        res_custom = self._run_cli("--apply", "--merged-file", str(merged_draft), "--json")
        self.assertEqual(res_custom.returncode, 0)
        self.assertEqual((self.root / "AGENTS.md").read_text(encoding="utf-8"), "# Unified AI Handbook\n- Single synthesized rule.\n")

    # --------------------------------------------------------------------------
    # Scenario 5: Idempotency (Already Standardized Repo)
    # --------------------------------------------------------------------------
    def test_scenario_5_already_standardized_idempotency(self):
        """Tests that running on a clean, standardized repo plans 0 changes."""
        # Stand up repo and apply standardization once
        (self.root / "AGENTS.md").write_text("# Universal Rules\n", encoding="utf-8")
        res_first = self._run_cli("--apply", "--json")
        self.assertEqual(res_first.returncode, 0)

        # Now run dry-run again on the standardized workspace
        res = self._run_cli("--dry-run", "--json")
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertEqual(data["changes_count"], 0)

        # Text mode output check
        res_text = self._run_cli("--dry-run")
        self.assertIn("already fully standardized", res_text.stdout)

    # --------------------------------------------------------------------------
    # Scenario 6: Windows Unprivileged Symlink Fallback
    # --------------------------------------------------------------------------
    def test_scenario_6_windows_symlink_privilege_fallback(self):
        """Simulates Windows without Developer Mode where symlink_to raises OSError."""
        (self.root / "CLAUDE.md").write_text("# Project Invariants\nRule 1.\n", encoding="utf-8")

        standardizer = WorkspaceStandardizer(self.root)
        audit = standardizer.audit()
        changes = standardizer.plan(audit, strategy="auto")

        # Mock Path.symlink_to to simulate WinError 1314
        with patch.object(Path, "symlink_to", side_effect=OSError(1314, "A required privilege is not held")):
            standardizer.apply(changes)

        # Verify fallback: CLAUDE.md and GEMINI.md exist as regular files copying AGENTS.md
        self.assertFalse((self.root / "CLAUDE.md").is_symlink())
        self.assertTrue((self.root / "CLAUDE.md").is_file())
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), (self.root / "AGENTS.md").read_text(encoding="utf-8"))

        self.assertFalse((self.root / "GEMINI.md").is_symlink())
        self.assertTrue((self.root / "GEMINI.md").is_file())
        self.assertEqual((self.root / "GEMINI.md").read_text(encoding="utf-8"), (self.root / "AGENTS.md").read_text(encoding="utf-8"))

    # --------------------------------------------------------------------------
    # Scenario 7: MCP Script Wrapping and Environment Variables
    # --------------------------------------------------------------------------
    def test_scenario_7_mcp_shell_wrapping_and_env(self):
        """Tests that script commands are wrapped for Antigravity and TOML env is generated for Codex."""
        mcp_json = self.root / ".mcp.json"
        mcp_json.write_text(json.dumps({
            "mcpServers": {
                "custom-script": {
                    "command": "./scripts/run_server.sh",
                    "args": ["--port", "8080"],
                    "env": {
                        "API_TOKEN": "secret_abc_123"
                    }
                }
            }
        }, indent=2), encoding="utf-8")

        res = self._run_cli("--apply", "--json")
        self.assertEqual(res.returncode, 0)

        # Check Antigravity .gemini/mcp_config.json
        gemini_mcp = json.loads((self.root / ".gemini" / "mcp_config.json").read_text(encoding="utf-8"))
        srv = gemini_mcp["mcpServers"]["custom-script"]
        # Script invocation must be wrapped in shell
        self.assertIn(srv["command"], ["/bin/sh", "cmd.exe"])
        self.assertIn("./scripts/run_server.sh", srv["args"][1])

        # Check Codex .codex/config.toml
        codex_toml = (self.root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("[mcp_servers.custom-script.env]", codex_toml)
        self.assertIn('API_TOKEN = "secret_abc_123"', codex_toml)


if __name__ == "__main__":
    unittest.main()
