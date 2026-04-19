# remotecc

`remotecc` is a minimal CLI and Codex skill root for running Claude Code in a remote SSH workspace with explicit session management.

This repository root is the source of truth.

- The Python package lives in `src/remotecc`
- The Codex skill lives at this repo root via `SKILL.md`
- The repo-root launcher is `scripts/remotecc.py`

There is no second vendored skill repo to maintain.

## What It Does

`remotecc` is built around this workflow:

1. Sync a local project to a remote machine with `rsync`
2. Start Claude Code inside remote `tmux`
3. Send prompts from Codex or the shell
4. Pull changed files back locally
5. Keep local session state in a durable registry

For the MVP, this deliberately uses `rsync + ssh + tmux` instead of a mounted remote filesystem.

## Why This Shape

This first version avoids SSHFS-style mounts on purpose:

- session stability matters more than live POSIX mount behavior
- reconnect and latency behavior is easier to reason about
- a single-writer remote workflow is much easier to keep safe

## Repository Layout

- [SKILL.md](./SKILL.md): Codex skill instructions
- [agents/openai.yaml](./agents/openai.yaml): skill UI metadata
- [scripts/remotecc.py](./scripts/remotecc.py): run from repo root without installation
- [references/command-cookbook.md](./references/command-cookbook.md): concrete command patterns
- [src/remotecc](./src/remotecc): actual Python implementation
- [README.zh-CN.md](./README.zh-CN.md): Chinese user-facing guide

## Requirements

Local:

- `ssh`
- `rsync`
- Python 3.10+

Remote:

- `bash`
- `tmux`
- `rsync`
- `claude` CLI installed and already authenticated

The local `rsync` flags stay conservative so the CLI works with the older implementation that ships on macOS.

## Local Development

Install in editable mode from this repo root:

```bash
cd /path/to/remotecc
python3 -m pip install -e .
```

Or run directly from the repo root without installation:

```bash
python3 scripts/remotecc.py --help
```

## Use As A Codex Skill

This repo root itself is the skill root. After installation, Codex can invoke:

```text
$remotecc-claude-session
```

Example prompt:

```text
Use $remotecc-claude-session to create a remote Claude session on root@example.com for /Users/me/project, use the standard profile, start it, and report whether it is ready for non-interactive use.
```

## Install As A Skill

### Option 1: clone manually

```bash
git clone https://github.com/yxhpy/remotecc-claude-session.git ~/.codex/skills/remotecc-claude-session
```

### Option 2: use `skill-installer`

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo yxhpy/remotecc-claude-session --path . --name remotecc-claude-session --method git
```

Notes:

- `--path .` is required because the repository root is the skill root
- `--method git` is the reliable fallback when Python download mode hits local SSL certificate issues
- restart Codex after installation so the skill is discovered

## Quick Start

Create a session from the current repo root:

```bash
python3 scripts/remotecc.py create demo user@host --local-dir . --profile standard
```

Use password-auth bootstrap if the first connection needs password or passphrase entry:

```bash
python3 scripts/remotecc.py create demo user@host --local-dir . --profile standard --password-auth
```

Check whether a skill can continue non-interactively:

```bash
python3 scripts/remotecc.py ready demo --json
```

Start Claude Code:

```bash
python3 scripts/remotecc.py start demo
```

Send one request:

```bash
python3 scripts/remotecc.py send demo --text "Inspect this repo and summarize the entrypoint."
```

Pull remote edits back:

```bash
python3 scripts/remotecc.py pull demo
```

Close the session:

```bash
python3 scripts/remotecc.py close demo --drop-remote
```

## Session Model

Each session stores:

- local working directory
- SSH target
- remote workspace path
- remote `tmux` session name
- Claude command
- model profile and model alias
- lifecycle timestamps

State is stored locally in:

```text
~/.remotecc/sessions.json
```

Treat the remote workspace as the active writer while Claude Code is running.

Recommended flow:

1. `create`
2. `ready --json`
3. `start`
4. `send` or `chat`
5. `pull`
6. `close`

## Authentication Model

There are two intended modes:

- key-based SSH: preferred for unattended use
- `--password-auth`: bootstrap path when a human can unlock the session once

`--password-auth` does not store the password. It creates a session-scoped SSH control master so later `ssh` and `rsync` commands can reuse that connection.

If the control socket expires:

```bash
python3 scripts/remotecc.py connect demo
```

For skill use, the rule is simple:

- a human may bootstrap
- the skill should only continue when `ready --json` says the session is safe

## Claude First-Run Prompts

The first remote run may still block on Claude Code itself, for example:

- workspace trust
- edit approval

That is not an SSH problem. Clear it manually once during bootstrap, or choose a deliberately permissive Claude command only when that tradeoff is acceptable:

```bash
python3 scripts/remotecc.py create demo user@host --local-dir . --model opus --claude-command "claude --dangerously-skip-permissions"
```

## Model Routing

Ask for machine-readable routing guidance:

```bash
python3 scripts/remotecc.py models --json
```

Default profiles:

- `simple` -> `haiku`
- `standard` -> `sonnet`
- `complex` -> `opus`
- `plan` -> `opusplan`
- `long` -> `sonnet[1m]`

Practical guidance:

- `haiku` or `hk`: listing, grep, summaries, tiny low-risk edits
- `sonnet`: daily coding, normal implementation, common bug fixes
- `opus`: architecture, risky migrations, ambiguous debugging, deep review
- `opusplan`: planning-first workflows where plan quality matters most

Examples:

```bash
python3 scripts/remotecc.py models --json
python3 scripts/remotecc.py create demo user@host --local-dir . --profile standard
python3 scripts/remotecc.py start demo --model opus
python3 scripts/remotecc.py set-model demo --profile complex
python3 scripts/remotecc.py send demo --profile simple --text "Summarize this folder."
```

## Minimal Closed Loop

```bash
python3 scripts/remotecc.py create demo user@host --local-dir . --profile standard --password-auth
python3 scripts/remotecc.py ready demo --json
python3 scripts/remotecc.py start demo
python3 scripts/remotecc.py send demo --text "Create a file named smoke.txt containing OK."
python3 scripts/remotecc.py pull demo --force
python3 scripts/remotecc.py close demo --drop-remote
```

## Limits

- no live mounted filesystem
- no automatic conflict resolution
- no remote sandboxing
- pane-based output capture instead of a structured Claude API

## Related Docs

- [README.zh-CN.md](./README.zh-CN.md)
- [SKILL.md](./SKILL.md)
- [references/command-cookbook.md](./references/command-cookbook.md)
