---
name: remotecc-claude-session
description: Manage remote Claude Code workspaces over SSH with persistent tmux sessions, rsync sync, password-auth control-master bootstrap, and explicit model routing. Use when Codex needs to mirror a local project to a remote host, start or resume Claude Code remotely, choose between Opus, Sonnet, Haiku, or OpusPlan, capture remote output, pull edits back locally, or close remote sessions safely.
---

# Remote Claude Session

This repository root is the skill root.

Use the repo-root launcher [scripts/remotecc.py](scripts/remotecc.py). It loads the source package from `src/` directly, so the skill stays aligned with the code in this same repository.

## Quick Start

1. Use `python3 scripts/remotecc.py models --json` when another skill or agent needs machine-readable routing guidance.
2. Create a session.
   Default to `--profile standard` unless the task clearly needs something else.
3. Gate non-interactive automation with `ready --json`.
4. Run `start`, `send`, `capture`, `pull`, and `close` against that session.

Treat the remote side as the active writer while Claude Code is editing files. Pull changes back when you need them locally.

## Core Workflow

### Bootstrap

- Create a session:
  `python3 scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard`
- Add `--password-auth` only when a human can enter the SSH password or key passphrase once.
- If the remote Claude CLI will ask for workspace trust or edit approval, clear that manually once during bootstrap or use `--claude-command "claude --dangerously-skip-permissions"` only when that tradeoff is acceptable.

### Run

- Verify the session is safe for non-interactive use:
  `python3 scripts/remotecc.py ready demo --json`
- Start Claude Code:
  `python3 scripts/remotecc.py start demo`
- Send work:
  `python3 scripts/remotecc.py send demo --text "..." --profile standard`
- Inspect recent pane output:
  `python3 scripts/remotecc.py capture demo --lines 200`

### Collect

- Pull changes back:
  `python3 scripts/remotecc.py pull demo`
- If Claude is still running and you intentionally want the current remote state, use `--force`.

### Tear Down

- Close the session:
  `python3 scripts/remotecc.py close demo --drop-remote`

## Model Routing

- Map `hk` to `haiku`.
- Use `haiku` or profile `simple` for listing, grep, summaries, tiny low-risk edits, and cheap repetitive tasks.
- Use `sonnet` or profile `standard` for default daily coding, normal implementation, common bug fixes, and medium-complexity refactors.
- Use `opus` or profile `complex` for architecture, ambiguous debugging, risky migrations, or deep review.
- Use `opusplan` or profile `plan` when plan quality matters more than one-model consistency.
- Use `sonnet[1m]` or profile `long` when repo scale or conversation length is the main constraint.
- Prefer `models --json` for upstream routing instead of hardcoding assumptions.

If a session is already running and the model must change, use one of these:

- `set-model demo --model opus`
- `start demo --model opus --restart`
- `send demo --profile complex --text "..."`

The launcher persists the configured model in the session registry and switches the running Claude session when possible.

## Session Rules

- `ready --json` is the machine gate for skills and automations.
- Password auth is a bootstrap path, not the normal unattended path.
- Session state lives in `~/.remotecc/sessions.json`.
- Closed sessions are historical records; do not try to `push`, `start`, `send`, `attach`, or `chat` against them.
- If the control master expires on a password-auth session, reconnect with:
  `python3 scripts/remotecc.py connect demo`

## References

- Use [references/command-cookbook.md](references/command-cookbook.md) for concrete command patterns and common failure interpretation.
