#!/usr/bin/env python3
"""Standardize AI coding agent configurations across Cursor, Claude Code, OpenAI Codex, and Antigravity.

Unifies workspace instructions into AGENTS.md, skills into .agents/skills/,
and compiles Model Context Protocol (MCP) definitions into each agent's
native format (.mcp.json, .gemini/mcp_config.json, .codex/config.toml).
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Python 3.11+ has tomllib in the standard library
try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]


@dataclass
class MCPServer:
    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"command": self.command}
        if self.args:
            data["args"] = self.args
        if self.env:
            data["env"] = self.env
        return data


@dataclass
class WorkspaceAudit:
    root: Path
    instructions: Dict[str, str] = field(default_factory=dict)  # filename -> content
    symlinks: Dict[str, str] = field(default_factory=dict)  # filename -> symlink target
    skills: Dict[str, List[str]] = field(default_factory=dict)  # agent_dir -> skill_names
    mcp_servers: Dict[str, MCPServer] = field(default_factory=dict)
    detected_scripts: List[str] = field(default_factory=list)
    has_conflict: bool = False
    conflict_details: List[str] = field(default_factory=list)


@dataclass
class FileChange:
    path: Path
    action: str  # 'create', 'modify', 'delete', 'symlink', 'move'
    original_content: Optional[str] = None
    new_content: Optional[str] = None
    symlink_target: Optional[str] = None
    source_path: Optional[Path] = None

    def diff(self, root: Path) -> str:
        rel = self.path.relative_to(root)
        if self.action == "symlink":
            return f"Symlink: {rel} -> {self.symlink_target}\n"
        if self.action == "move":
            src_rel = self.source_path.relative_to(root) if self.source_path else "?"
            return f"Move: {src_rel} -> {rel}\n"

        orig_lines = (self.original_content or "").splitlines(keepends=True)
        new_lines = (self.new_content or "").splitlines(keepends=True)

        from_file = f"a/{rel}" if self.original_content is not None else "/dev/null"
        to_file = f"b/{rel}" if self.new_content is not None else "/dev/null"

        diff_lines = list(
            difflib.unified_diff(
                orig_lines, new_lines, fromfile=from_file, tofile=to_file
            )
        )
        return "".join(diff_lines)


class WorkspaceStandardizer:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def audit(self) -> WorkspaceAudit:
        audit = WorkspaceAudit(root=self.root)

        # 1. Audit instruction files
        candidates = ["CLAUDE.md", "GEMINI.md", "AGENTS.md", ".cursorrules"]
        found_instructions: Dict[str, str] = {}
        for name in candidates:
            p = self.root / name
            if p.is_symlink():
                audit.symlinks[name] = os.readlink(p)
            elif p.is_file():
                try:
                    found_instructions[name] = p.read_text(encoding="utf-8")
                except Exception as e:
                    found_instructions[name] = f"# Error reading {name}: {e}"

        audit.instructions = found_instructions

        # Check for conflicts among non-symlinked instructions
        if len(found_instructions) > 1:
            contents = list(found_instructions.values())
            # Normalize whitespace to avoid false conflicts
            normalized = ["\n".join(c.strip().splitlines()) for c in contents]
            if len(set(normalized)) > 1:
                audit.has_conflict = True
                audit.conflict_details = list(found_instructions.keys())

        # 2. Audit skills
        skill_dirs = {
            "claude": self.root / ".claude" / "skills",
            "codex": self.root / ".codex" / "skills",
            "agents": self.root / ".agents" / "skills",
        }
        for agent, sdir in skill_dirs.items():
            if sdir.is_dir():
                skills = [
                    d.name
                    for d in sdir.iterdir()
                    if d.is_dir() and (d / "SKILL.md").exists()
                ]
                if skills:
                    audit.skills[agent] = sorted(skills)

        # 3. Audit MCP servers
        # Check root .mcp.json (Claude / Standard)
        claude_mcp = self.root / ".mcp.json"
        if claude_mcp.is_file():
            self._parse_mcp_json(claude_mcp, audit)

        # Check Antigravity .gemini/mcp_config.json
        gemini_mcp = self.root / ".gemini" / "mcp_config.json"
        if gemini_mcp.is_file() and not audit.mcp_servers:
            self._parse_mcp_json(gemini_mcp, audit)

        # Check Codex .codex/config.toml
        codex_toml = self.root / ".codex" / "config.toml"
        if codex_toml.is_file() and not audit.mcp_servers and tomllib is not None:
            self._parse_codex_toml(codex_toml, audit)

        # 4. Audit scripts (package.json, Makefile, pyproject.toml)
        pkg_json = self.root / "package.json"
        if pkg_json.is_file():
            try:
                pkg_data = json.loads(pkg_json.read_text(encoding="utf-8"))
                for s in pkg_data.get("scripts", {}).keys():
                    audit.detected_scripts.append(f"npm run {s}" if s != "test" else "npm test")
            except Exception:
                pass

        return audit

    def _parse_mcp_json(self, path: Path, audit: WorkspaceAudit) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", {})
            for name, s_cfg in servers.items():
                if name not in audit.mcp_servers:
                    audit.mcp_servers[name] = MCPServer(
                        name=name,
                        command=s_cfg.get("command", ""),
                        args=s_cfg.get("args", []),
                        env=s_cfg.get("env", {}),
                    )
        except Exception:
            pass

    def _parse_codex_toml(self, path: Path, audit: WorkspaceAudit) -> None:
        if tomllib is None:
            return
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            servers = data.get("mcp_servers", {})
            for name, s_cfg in servers.items():
                if name not in audit.mcp_servers:
                    audit.mcp_servers[name] = MCPServer(
                        name=name,
                        command=s_cfg.get("command", ""),
                        args=s_cfg.get("args", []),
                        env=s_cfg.get("env", {}),
                    )
        except Exception:
            pass

    def plan(
        self,
        audit: WorkspaceAudit,
        strategy: str = "auto",
        merged_content: Optional[str] = None,
    ) -> List[FileChange]:
        changes: List[FileChange] = []

        # 1. Resolve AGENTS.md content
        agents_path = self.root / "AGENTS.md"
        orig_agents = (
            agents_path.read_text(encoding="utf-8")
            if agents_path.is_file() and not agents_path.is_symlink()
            else None
        )

        chosen_content: Optional[str] = None

        if merged_content is not None:
            chosen_content = merged_content
        elif strategy == "pick:claude":
            chosen_content = audit.instructions.get("CLAUDE.md")
        elif strategy == "pick:gemini":
            chosen_content = audit.instructions.get("GEMINI.md")
        elif strategy == "pick:cursor":
            chosen_content = audit.instructions.get(".cursorrules")
        elif strategy == "pick:agents":
            chosen_content = audit.instructions.get("AGENTS.md")
        elif strategy == "merge":
            chosen_content = self._simple_merge(audit.instructions)
        else:  # auto
            if "AGENTS.md" in audit.instructions and not audit.has_conflict:
                chosen_content = audit.instructions["AGENTS.md"]
            elif "CLAUDE.md" in audit.instructions and not audit.has_conflict:
                chosen_content = audit.instructions["CLAUDE.md"]
            elif "GEMINI.md" in audit.instructions and not audit.has_conflict:
                chosen_content = audit.instructions["GEMINI.md"]
            elif ".cursorrules" in audit.instructions and not audit.has_conflict:
                chosen_content = audit.instructions[".cursorrules"]
            elif audit.has_conflict:
                raise ValueError(
                    f"Conflict detected between instruction files: {', '.join(audit.conflict_details)}. "
                    "Must specify --strategy (pick:claude, pick:gemini, pick:cursor, pick:agents, or merge)."
                )
            else:
                chosen_content = (
                    "# Repository Agent Guidelines\n\n"
                    "Universal instructions for AI coding agents (Cursor, Claude Code, OpenAI Codex, Antigravity).\n"
                )

        if chosen_content is not None:
            # Ensure clean trailing newline
            if not chosen_content.endswith("\n"):
                chosen_content += "\n"

            if orig_agents != chosen_content:
                changes.append(
                    FileChange(
                        path=agents_path,
                        action="modify" if orig_agents else "create",
                        original_content=orig_agents,
                        new_content=chosen_content,
                    )
                )

        # 2. Plan symlinks (CLAUDE.md -> AGENTS.md, GEMINI.md -> AGENTS.md, .cursorrules -> AGENTS.md)
        for link_name in ["CLAUDE.md", "GEMINI.md", ".cursorrules"]:
            link_path = self.root / link_name
            # If it's already a correct symlink, skip
            if link_path.is_symlink() and os.readlink(link_path) == "AGENTS.md":
                continue
            orig_txt = (
                link_path.read_text(encoding="utf-8")
                if link_path.is_file() and not link_path.is_symlink()
                else None
            )
            changes.append(
                FileChange(
                    path=link_path,
                    action="symlink",
                    original_content=orig_txt,
                    symlink_target="AGENTS.md",
                )
            )

        # 3. Plan Skill consolidation (.claude/skills/*, .codex/skills/* -> .agents/skills/*)
        target_skills_dir = self.root / ".agents" / "skills"
        existing_target_skills = set(audit.skills.get("agents", []))

        for source_agent in ["claude", "codex"]:
            for sname in audit.skills.get(source_agent, []):
                if sname not in existing_target_skills:
                    src_path = self.root / f".{source_agent}" / "skills" / sname
                    dest_path = target_skills_dir / sname
                    changes.append(
                        FileChange(
                            path=dest_path,
                            action="move",
                            source_path=src_path,
                        )
                    )
                    existing_target_skills.add(sname)

        # 4. Plan MCP configurations across clients
        if audit.mcp_servers:
            # A. Root .mcp.json (Standard / Claude Code)
            mcp_json_path = self.root / ".mcp.json"
            orig_mcp_json = (
                mcp_json_path.read_text(encoding="utf-8")
                if mcp_json_path.is_file()
                else None
            )
            mcp_data = {
                "mcpServers": {
                    name: s.to_dict() for name, s in sorted(audit.mcp_servers.items())
                }
            }
            new_mcp_json = json.dumps(mcp_data, indent=2) + "\n"
            if orig_mcp_json != new_mcp_json:
                changes.append(
                    FileChange(
                        path=mcp_json_path,
                        action="modify" if orig_mcp_json else "create",
                        original_content=orig_mcp_json,
                        new_content=new_mcp_json,
                    )
                )

            # B. Antigravity .gemini/mcp_config.json
            gemini_mcp_path = self.root / ".gemini" / "mcp_config.json"
            orig_gemini_mcp = (
                gemini_mcp_path.read_text(encoding="utf-8")
                if gemini_mcp_path.is_file()
                else None
            )
            # Adapt Antigravity commands: wrap relative or shell-dependent executions safely
            is_windows = os.name == "nt"
            gemini_servers: Dict[str, Any] = {}
            for name, s in sorted(audit.mcp_servers.items()):
                server_dict = s.to_dict()
                cmd = server_dict["command"]
                # If command is a relative path or script invocation, wrap in shell for portable execution
                if cmd.endswith(".sh") or cmd.endswith(".py") or cmd.startswith("./") or " " in cmd:
                    if is_windows:
                        server_dict["command"] = "cmd.exe"
                        args_str = " ".join(s.args)
                        server_dict["args"] = ["/c", f"{cmd} {args_str}".strip()]
                    else:
                        server_dict["command"] = "/bin/sh"
                        args_str = " ".join(f'"{a}"' for a in s.args)
                        server_dict["args"] = ["-c", f"exec {cmd} {args_str}".strip()]
                gemini_servers[name] = server_dict

            new_gemini_mcp = (
                json.dumps({"mcpServers": gemini_servers}, indent=2) + "\n"
            )
            if orig_gemini_mcp != new_gemini_mcp:
                changes.append(
                    FileChange(
                        path=gemini_mcp_path,
                        action="modify" if orig_gemini_mcp else "create",
                        original_content=orig_gemini_mcp,
                        new_content=new_gemini_mcp,
                    )
                )

            # C. Codex .codex/config.toml
            codex_toml_path = self.root / ".codex" / "config.toml"
            orig_codex_toml = (
                codex_toml_path.read_text(encoding="utf-8")
                if codex_toml_path.is_file()
                else None
            )
            toml_lines = ["# Codex Model Context Protocol (MCP) Configuration\n"]
            for name, s in sorted(audit.mcp_servers.items()):
                toml_lines.append(f"[mcp_servers.{name}]")
                toml_lines.append(f'command = "{s.command}"')
                if s.args:
                    args_json = json.dumps(s.args)
                    toml_lines.append(f"args = {args_json}")
                if s.env:
                    toml_lines.append(f"[mcp_servers.{name}.env]")
                    for k, v in sorted(s.env.items()):
                        toml_lines.append(f'{k} = "{v}"')
                toml_lines.append("")
            new_codex_toml = "\n".join(toml_lines) + "\n"
            if orig_codex_toml != new_codex_toml:
                changes.append(
                    FileChange(
                        path=codex_toml_path,
                        action="modify" if orig_codex_toml else "create",
                        original_content=orig_codex_toml,
                        new_content=new_codex_toml,
                    )
                )

        # 5. Plan Antigravity pre-approved permissions (.gemini/settings.json)
        gemini_settings_path = self.root / ".gemini" / "settings.json"
        orig_settings = (
            gemini_settings_path.read_text(encoding="utf-8")
            if gemini_settings_path.is_file()
            else None
        )

        existing_allow: List[str] = []
        if orig_settings:
            try:
                s_data = json.loads(orig_settings)
                existing_allow = s_data.get("permissions", {}).get("allow", [])
            except Exception:
                pass

        allow_set = set(existing_allow)
        # Default essential tool capabilities
        for std_cmd in ["git status", "git diff", "git log"]:
            allow_set.add(f"run_command({std_cmd})")

        # Add detected package test/build scripts
        for sc in audit.detected_scripts[:5]:
            allow_set.add(f"run_command({sc})")

        # Add MCP tools
        for sname in audit.mcp_servers.keys():
            allow_set.add(f"mcp({sname}/*)")

        new_settings_data = {
            "permissions": {
                "allow": sorted(list(allow_set))
            }
        }
        new_settings_json = json.dumps(new_settings_data, indent=2) + "\n"
        if orig_settings != new_settings_json:
            changes.append(
                FileChange(
                    path=gemini_settings_path,
                    action="modify" if orig_settings else "create",
                    original_content=orig_settings,
                    new_content=new_settings_json,
                )
            )

        return changes

    def _simple_merge(self, instructions: Dict[str, str]) -> str:
        """Heuristic merge combining distinct sections across instruction files."""
        lines: List[str] = [
            "# Universal Agent Guidelines (AGENTS.md)\n",
            "This repository standardizes AI coding agent instructions across Cursor, Claude Code, OpenAI Codex, and Antigravity.\n",
        ]
        seen_headers: Set[str] = set()

        for filename, content in instructions.items():
            lines.append(f"\n<!-- Section merged from {filename} -->\n")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    header_norm = stripped.lstrip("#").strip().lower()
                    if header_norm in seen_headers:
                        continue
                    seen_headers.add(header_norm)
                lines.append(line)

        return "\n".join(lines) + "\n"

    def apply(self, changes: List[FileChange]) -> None:
        for c in changes:
            c.path.parent.mkdir(parents=True, exist_ok=True)

            if c.action in ("create", "modify"):
                c.path.write_text(c.new_content or "", encoding="utf-8")
            elif c.action == "symlink":
                if c.path.is_symlink() or c.path.exists():
                    c.path.unlink()
                try:
                    c.path.symlink_to(c.symlink_target)
                except OSError:
                    # Windows fallback without Developer Mode / elevated privileges: copy canonical file
                    target_file = c.path.parent / c.symlink_target
                    if target_file.is_file():
                        shutil.copy2(target_file, c.path)
            elif c.action == "move" and c.source_path:
                if c.path.exists():
                    shutil.rmtree(c.path)
                shutil.move(str(c.source_path), str(c.path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Standardize AI coding agent configurations across Cursor, Claude Code, OpenAI Codex, and Antigravity."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Workspace root directory (defaults to current working directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate changes and emit unified diffs without modifying files (default).",
    )
    parser.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Apply planned changes to the filesystem.",
    )
    parser.add_argument(
        "--strategy",
        choices=["auto", "pick:claude", "pick:gemini", "pick:cursor", "pick:agents", "merge"],
        default="auto",
        help="Conflict resolution strategy if multiple differing instruction files exist.",
    )
    parser.add_argument(
        "--merged-file",
        type=Path,
        default=None,
        help="Path to a pre-synthesized file to use as the canonical AGENTS.md content.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results and diffs as a JSON payload for programmatic consumption.",
    )

    args = parser.parse_args()
    args.root = args.root.resolve()
    standardizer = WorkspaceStandardizer(args.root)

    try:
        audit = standardizer.audit()
    except Exception as e:
        sys.stderr.write(f"Error during workspace audit: {e}\n")
        return 1

    merged_content = None
    if args.merged_file and args.merged_file.is_file():
        merged_content = args.merged_file.read_text(encoding="utf-8")

    try:
        changes = standardizer.plan(
            audit=audit,
            strategy=args.strategy,
            merged_content=merged_content,
        )
    except ValueError as e:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "conflict",
                        "error": str(e),
                        "conflict_files": audit.conflict_details,
                    },
                    indent=2,
                )
            )
        else:
            sys.stderr.write(f"CONFLICT ERROR: {e}\n")
        return 2

    # Render results
    if args.json:
        payload = {
            "status": "ok",
            "dry_run": args.dry_run,
            "has_conflict": audit.has_conflict,
            "instructions_detected": list(audit.instructions.keys()),
            "skills_detected": audit.skills,
            "mcp_servers": list(audit.mcp_servers.keys()),
            "changes_count": len(changes),
            "changes": [
                {
                    "path": str(c.path.relative_to(args.root)),
                    "action": c.action,
                    "diff": c.diff(args.root),
                }
                for c in changes
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        if not changes:
            print("Workspace is already fully standardized! No changes needed.")
            return 0

        mode_str = "[DRY RUN - No files touched]" if args.dry_run else "[APPLYING CHANGES]"
        print(f"=== Standardize Agent Workspace: {mode_str} ===")
        print(f"Target Root: {args.root}\n")

        for c in changes:
            diff_text = c.diff(args.root)
            if diff_text:
                print(f"--- File: {c.path.relative_to(args.root)} ({c.action}) ---")
                print(diff_text)

    if not args.dry_run:
        standardizer.apply(changes)
        if not args.json:
            print("\nSuccessfully applied all standardization changes!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
