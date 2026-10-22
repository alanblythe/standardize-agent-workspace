"""Unit tests for WorkspaceStandardizer."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.standardize import WorkspaceStandardizer


class TestWorkspaceStandardizer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_legacy_claude_setup_dry_run_and_apply(self):
        # 1. Setup legacy Claude workspace
        claude_md = self.root / "CLAUDE.md"
        claude_md.write_text("# Project Guidelines\n- Run npm test before commit\n", encoding="utf-8")

        skill_dir = self.root / ".claude" / "skills" / "pr-review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: pr-review\ndescription: review PRs\n---\n", encoding="utf-8")

        mcp_json = self.root / ".mcp.json"
        mcp_json.write_text(json.dumps({
            "mcpServers": {
                "fetch": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-fetch"]
                }
            }
        }), encoding="utf-8")

        pkg_json = self.root / "package.json"
        pkg_json.write_text(json.dumps({
            "scripts": {
                "test": "jest",
                "build": "tsc"
            }
        }), encoding="utf-8")

        standardizer = WorkspaceStandardizer(self.root)

        # 2. Audit
        audit = standardizer.audit()
        self.assertFalse(audit.has_conflict)
        self.assertIn("CLAUDE.md", audit.instructions)
        self.assertIn("pr-review", audit.skills.get("claude", []))
        self.assertIn("fetch", audit.mcp_servers)

        # 3. Dry-Run Plan
        changes = standardizer.plan(audit, strategy="auto")
        self.assertTrue(len(changes) >= 5)

        # Check diff output
        diff_texts = [c.diff(self.root) for c in changes]
        self.assertTrue(any("AGENTS.md" in d for d in diff_texts))

        # Ensure no files were modified in dry-run
        self.assertFalse((self.root / "AGENTS.md").exists())

        # 4. Apply
        standardizer.apply(changes)

        # Verify AGENTS.md was created
        agents_md = self.root / "AGENTS.md"
        self.assertTrue(agents_md.is_file())
        self.assertIn("Run npm test before commit", agents_md.read_text(encoding="utf-8"))

        # Verify CLAUDE.md is now a symlink
        self.assertTrue(claude_md.is_symlink())
        self.assertEqual(os.readlink(claude_md), "AGENTS.md")

        # Verify GEMINI.md symlink
        gemini_md = self.root / "GEMINI.md"
        self.assertTrue(gemini_md.is_symlink())
        self.assertEqual(os.readlink(gemini_md), "AGENTS.md")

        # Verify skill was moved to .agents/skills/
        target_skill = self.root / ".agents" / "skills" / "pr-review" / "SKILL.md"
        self.assertTrue(target_skill.is_file())

        # Verify Antigravity MCP config
        gemini_mcp = self.root / ".gemini" / "mcp_config.json"
        self.assertTrue(gemini_mcp.is_file())
        gemini_mcp_data = json.loads(gemini_mcp.read_text(encoding="utf-8"))
        self.assertIn("fetch", gemini_mcp_data["mcpServers"])

        # Verify Codex config.toml
        codex_toml = self.root / ".codex" / "config.toml"
        self.assertTrue(codex_toml.is_file())
        self.assertIn("[mcp_servers.fetch]", codex_toml.read_text(encoding="utf-8"))

        # Verify Antigravity settings.json permissions
        gemini_settings = self.root / ".gemini" / "settings.json"
        self.assertTrue(gemini_settings.is_file())
        settings_data = json.loads(gemini_settings.read_text(encoding="utf-8"))
        allows = settings_data["permissions"]["allow"]
        self.assertIn("mcp(fetch/*)", allows)
        self.assertIn("run_command(npm test)", allows)

    def test_conflict_detection_and_resolution(self):
        (self.root / "CLAUDE.md").write_text("# Claude Rules\nAlways use tabs.\n", encoding="utf-8")
        (self.root / "GEMINI.md").write_text("# Gemini Rules\nAlways use spaces.\n", encoding="utf-8")

        standardizer = WorkspaceStandardizer(self.root)
        audit = standardizer.audit()
        self.assertTrue(audit.has_conflict)

        # auto should raise ValueError
        with self.assertRaises(ValueError):
            standardizer.plan(audit, strategy="auto")

        # pick:claude should resolve
        changes_claude = standardizer.plan(audit, strategy="pick:claude")
        agents_change = next(c for c in changes_claude if c.path.name == "AGENTS.md")
        self.assertIn("Always use tabs", agents_change.new_content)

        # merge strategy should combine
        changes_merge = standardizer.plan(audit, strategy="merge")
        merged_change = next(c for c in changes_merge if c.path.name == "AGENTS.md")
        self.assertIn("Always use tabs", merged_change.new_content)
        self.assertIn("Always use spaces", merged_change.new_content)


if __name__ == "__main__":
    unittest.main()
