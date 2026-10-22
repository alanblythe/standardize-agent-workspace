# Standardize Agent Workspace

> [!IMPORTANT]  
> This project is not provided by Google and does not come with any support or warranties. While the author is an employee at Google, this is a personal project and not an officially supported Google product. This project serves as a utility and reference implementation for standardizing AI coding agent workspaces across Claude Code, OpenAI Codex, and Antigravity.  
> Though functional, you may wish to adapt the configuration and scripts to suit your organization's specific development environments.  

> [!IMPORTANT]  
> Accurate as of 10/22/2026  

A universal developer skill and Python CLI that upgrades code repositories to the open **Linux Foundation Agentic AI Foundation (AAIF)** standard. 

Enables **Claude Code**, **OpenAI Codex**, and **Antigravity** to operate simultaneously against a single source of truth without configuration drift or duplicate file maintenance.

---

## What It Does

| Layer | Before Standardization | After Standardization (Unified Target) |
| :--- | :--- | :--- |
| **Instructions** | Scattered `CLAUDE.md`, `GEMINI.md`, or `AGENTS.md` | Single canonical **`AGENTS.md`** at root; `CLAUDE.md` and `GEMINI.md` symlinked to prevent Claude's shadow-precedence bug. |
| **Skills** | Vendor-specific `.claude/skills/` or `.codex/skills/` | Universal **`.agents/skills/<name>/SKILL.md`** (native to Codex, Antigravity, and `npx skills`). |
| **MCP Servers** | Disconnected `.mcp.json`, `config.toml`, or `mcp_config.json` | Single canonical **`.mcp.json`** compiled automatically to `.gemini/mcp_config.json` and `.codex/config.toml`. |
| **Tool Permissions** | Repeated interactive approval prompts | Pre-seeds **`.gemini/settings.json`** with allowlisted build/test scripts and MCP tools. |

---

## Core Capabilities

1. **Dry-Run Diff Preview by Default**:
   Simulates all planned creations, modifications, moves, and symlinks, emitting standard unified diffs (`diff -u`) before touching disk.
2. **Interactive Conflict Resolution**:
   If conflicting rules exist across tools (e.g. `CLAUDE.md` vs `GEMINI.md`), the tool pauses and lets the user pick a base or merge into a unified standard.
3. **Cross-Platform**:
   Natively supports macOS, Linux, and Windows (via WSL2 or unprivileged copy fallback).
4. **Idempotent**:
   Running on an already standardized repo plans 0 changes.

---

## Quickstart

### 1. Run as an Agent Skill

Install into your agent skills directory (`~/.gemini/config/skills/`, `~/.claude/skills/`, or `~/.codex/skills/`):

```bash
# Clone the repository
git clone https://github.com/alanblythe/standardize-agent-workspace.git ~/.gemini/config/skills/standardize-agent-workspace

# Or use the installer
./scripts/install.sh
```

Then invoke directly from any agent prompt:
* `/standardize-agent-workspace`
* *"standardize this workspace for Claude, Codex, and Antigravity"*

### 2. Run Directly via CLI

```bash
# 1. Preview changes (Dry Run - no files modified)
python3 scripts/standardize.py --root /path/to/repo --dry-run

# 2. Apply changes
python3 scripts/standardize.py --root /path/to/repo --apply

# 3. Resolve conflicts if multiple differing instruction files exist
python3 scripts/standardize.py --root /path/to/repo --apply --strategy merge
```

### CLI Flags
* `--root <path>`: Target workspace directory (defaults to current working directory).
* `--dry-run`: Preview planned changes and output unified diffs (default).
* `--apply`: Execute planned operations on disk.
* `--strategy {auto,pick:claude,pick:gemini,pick:agents,merge}`: Strategy when multiple conflicting rule files exist.
* `--merged-file <path>`: Provide an explicit synthesized markdown file for `AGENTS.md`.
* `--json`: Output machine-readable JSON for CI/CD integrations.

---

## Testing

Run the hermetic test suite:

```bash
# Local test runner (sub-second)
python3 -m unittest discover tests

# Or run inside an isolated container
./scripts/test_in_container.sh
```

---

## License

Apache 2.0
