---
name: standardize-agent-workspace
description: Standardize and harmonize AI coding agent configurations across Cursor, Claude Code, OpenAI Codex, and Antigravity into the Linux Foundation open standard (AGENTS.md, .cursorrules symlink, .agents/skills/, root .mcp.json) with dry-run diff preview and interactive conflict resolution. Use when a customer wants to migrate, convert, or dual-stack Cursor, Claude Code, or Codex with Antigravity, standardize agent rules, or resolve divergent MCP and skill configurations.
---

# Standardize Agent Workspace

Upgrades a project repository to the open, vendor-neutral **Linux Foundation Agentic AI Foundation (AAIF)** standard so that **Cursor**, **Claude Code**, **OpenAI Codex**, and **Antigravity** operate simultaneously against a single source of truth without configuration drift.

## Architectural Invariants

1. **Workspace Instructions**: Canonical truth is **`AGENTS.md`** at the repo root.
   - `CLAUDE.md`, `GEMINI.md`, and `.cursorrules` are symlinked to `AGENTS.md` to prevent shadow-precedence drift and ensure Cursor, Claude Code, and Antigravity developers share identical instructions.
2. **Skills Directory**: Consolidated under **`.agents/skills/<name>/SKILL.md`**.
   - Universal target supported natively by Codex, Antigravity, and `npx skills add`.
3. **Model Context Protocol (MCP)**: Canonical source is root **`.mcp.json`**.
   - Automatically compiled to Antigravity's `.gemini/mcp_config.json` (wrapping shell commands safely in `/bin/sh`) and Codex's `.codex/config.toml` (TOML tables).
4. **Pre-Seeded Permissions**: Generates **`.gemini/settings.json`** with allowlisted build/test scripts and MCP tools to prevent interactive approval fatigue.

---

## Execution Workflow

### Step 1: Execute Dry-Run Audit

Always run the deterministic Python engine in dry-run mode first to inspect the workspace and capture unified diffs without modifying files:

```bash
python3 <skill-directory>/scripts/standardize.py --root . --dry-run --json
```

Read the JSON output:
* If `status == "ok"` and `changes_count == 0`: Report to the user that the workspace is already fully standardized.
* If `status == "ok"` and `changes_count > 0`: Present the planned file changes and unified diffs inside markdown diff blocks:
  ```diff
  # Example output shown to user
  --- original/CLAUDE.md
  +++ target/AGENTS.md
  ...
  ```
  Proceed to **Step 3 (Apply)** if no conflict was detected.

---

### Step 2: Interactive Conflict Resolution (If Conflicting Instructions Exist)

If the dry run returns `"status": "conflict"` (e.g., both `CLAUDE.md` and `GEMINI.md` exist with differing instructions):

1. **Do not guess or overwrite.**
2. Inspect the conflicting files and prompt the user to choose their strategy:
   * **(Recommended) Merge into Unified Standard**: Synthesize a unified `AGENTS.md` draft combining unique rules and deduplicating common build/test scripts. Write the draft to a temporary scratch file and pass `--merged-file <path>`, or pass `--strategy merge`.
   * **Use Cursor (`.cursorrules`) as Base**: Pass `--strategy pick:cursor`.
   * **Use Claude Code (`CLAUDE.md`) as Base**: Pass `--strategy pick:claude`.
   * **Use Antigravity (`GEMINI.md`) as Base**: Pass `--strategy pick:gemini`.

---

### Step 3: Apply Standardization Changes

Execute the application step with the confirmed strategy:

```bash
# Auto mode (single source of truth exists)
python3 <skill-directory>/scripts/standardize.py --root . --apply

# Or with specific strategy
python3 <skill-directory>/scripts/standardize.py --root . --apply --strategy <pick:claude|pick:gemini|merge>

# Or with an AI-synthesized merged draft
python3 <skill-directory>/scripts/standardize.py --root . --apply --merged-file /tmp/merged_agents.md
```

---

### Step 4: Verification & Handoff

Verify that the filesystem matches the target state:
* [ ] `AGENTS.md` exists and contains project guidelines.
* [ ] `CLAUDE.md` is a valid relative symlink to `AGENTS.md`.
* [ ] `.agents/skills/` contains all project skills.
* [ ] `.gemini/mcp_config.json` and `.codex/config.toml` match `.mcp.json`.
* [ ] `.gemini/settings.json` has pre-seeded tool permissions.

Inform the user that the workspace is now ready for tri-agent operation:
* **Antigravity**: Launch with `agy`.
* **Claude Code**: Launch with `claude`.
* **OpenAI Codex**: Launch with `codex`.
* **Add new skills**: `npx skills add <repo> -a antigravity -a claude-code -a codex`.
