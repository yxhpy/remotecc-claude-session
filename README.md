# remotecc-claude-session

Self-contained Codex skill for running Claude Code in a remote SSH workspace with persistent sessions.

It is designed for this workflow:

1. Mirror a local project to a remote server.
2. Start Claude Code inside remote `tmux`.
3. Send prompts from Codex or shell.
4. Pull edited files back locally.
5. Keep session state explicit and recoverable.

The repository is both:

- a Codex skill: `remotecc-claude-session`
- a bundled CLI launcher: `scripts/remotecc.py`

## Who This Is For

Use this if you want an agent or a human operator to control Claude Code on a remote Linux box, while keeping the local project as the source repository.

This is especially useful when:

- the remote machine has better network access or compute
- Claude Code must run near remote files or services
- you want a repeatable session model instead of ad hoc `ssh` tabs
- a higher-level skill needs a stable CLI surface

## What The Skill Provides

- SSH + `rsync` workspace sync
- remote `tmux` session management
- local session registry in `~/.remotecc/sessions.json`
- bootstrap support for password-auth via SSH control master
- non-interactive readiness gate via `ready --json`
- explicit model routing for `haiku`, `sonnet`, `opus`, `opusplan`

## Installation

Clone the repository into your Codex skills directory:

```bash
git clone https://github.com/yxhpy/remotecc-claude-session.git ~/.codex/skills/remotecc-claude-session
```

If you use `CODEX_HOME`, install it under:

```bash
${CODEX_HOME}/skills/remotecc-claude-session
```

After that, Codex can invoke it by name:

```text
$remotecc-claude-session
```

## Install With skill-installer

If you already use Codex's built-in `skill-installer`, install this repo-root skill with:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo yxhpy/remotecc-claude-session --path . --name remotecc-claude-session --method git
```

Notes:

- `--path .` is required because this repository root is the skill root.
- `--method git` is the reliable fallback when Python download mode hits local SSL certificate issues.
- Restart Codex after installation so the new skill is discovered.

## Requirements

Local machine:

- `ssh`
- `rsync`
- Python 3.10+

Remote machine:

- `bash`
- `tmux`
- `rsync`
- `claude` CLI installed and already authenticated

## How To Use It In Codex

Example prompt:

```text
Use $remotecc-claude-session to create a remote Claude session on root@example.com for /Users/me/project, use the standard profile, start it, and report whether it is ready for non-interactive use.
```

The skill internally uses the bundled launcher:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py --help
```

## Quick Start

### 1. Create a session

Default daily-use path:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard
```

If the remote host needs password entry or local key passphrase entry during bootstrap:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard --password-auth
```

### 2. Check readiness

For higher-level skills or automation, always gate on:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py ready demo --json
```

If `ready` is false, do not assume a skill can continue unattended.

### 3. Start Claude Code

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py start demo
```

### 4. Send one instruction

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py send demo --text "Inspect the repo and fix the failing test."
```

### 5. Pull remote edits back

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py pull demo
```

### 6. Close the session

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py close demo --drop-remote
```

## Session Model

Treat the remote workspace as the active writer while Claude Code is running.

Practical rules:

- `create` performs the initial sync and records session metadata locally
- `start` launches Claude Code inside remote `tmux`
- `send` talks to the running remote session
- `pull` copies edited files back to the local project
- `close` marks the session closed and can also clean remote state

Closed sessions are history records. Do not keep sending work to them.

## Authentication Model

There are two intended modes:

- key-based SSH: preferred for unattended use
- password-auth bootstrap: acceptable only when a human can unlock the connection once

`--password-auth` does not store passwords. It creates a session-scoped SSH control master so later `ssh` and `rsync` calls can reuse that connection.

For skill use, the rule is:

- a human may bootstrap
- the skill should only consume a session after `ready --json` says it is safe

If the control master expires, reconnect with:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py connect demo
```

## Claude CLI First-Run Prompts

The first run on a remote machine may still block on Claude Code itself, for example:

- workspace trust
- edit approval

That is not an SSH problem. Clear those prompts once during bootstrap, or use a deliberately permissive Claude command only if that tradeoff is acceptable:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --model opus --claude-command "claude --dangerously-skip-permissions"
```

## Model Routing

Ask for machine-readable guidance:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py models --json
```

Default profiles:

- `simple` -> `haiku`
- `standard` -> `sonnet`
- `complex` -> `opus`
- `plan` -> `opusplan`
- `long` -> `sonnet[1m]`

Practical guidance:

- `haiku` or `hk`: listing, grep, summaries, tiny low-risk edits
- `sonnet`: default daily coding, normal implementation, common bug fixes
- `opus`: architecture, risky migrations, ambiguous debugging, deep review
- `opusplan`: planning-first workflows where plan quality matters more than one-model consistency

You can choose a model at create time, start time, or later:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --profile complex
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py set-model demo --model opus
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py start demo --model opus --restart
```

## Main Commands

The launcher exposes these commands:

- `models`
- `create`
- `list`
- `status`
- `ready`
- `connect`
- `set-model`
- `push`
- `pull`
- `start`
- `send`
- `capture`
- `attach`
- `close`
- `chat`

For concrete examples, see [references/command-cookbook.md](./references/command-cookbook.md).

## Minimal Closed Loop

This is the smallest useful end-to-end flow:

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard --password-auth
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py ready demo --json
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py start demo
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py send demo --text "Create a file named smoke.txt containing OK."
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py pull demo --force
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py close demo --drop-remote
```

## Limits And Assumptions

- This is an MVP session layer, not a distributed filesystem.
- The recommended path is sync in, run remotely, sync back.
- Password-auth is a bootstrap path, not the final unattended architecture.
- If local and remote both edit the same files concurrently, you own the merge problem.

## Repository Layout

- [SKILL.md](./SKILL.md): skill instructions for Codex
- [scripts/remotecc.py](./scripts/remotecc.py): bundled launcher
- [references/command-cookbook.md](./references/command-cookbook.md): concrete command patterns

## State Storage

Local session state is stored at:

```text
~/.remotecc/sessions.json
```

## Related Files

- [SKILL.md](./SKILL.md)
- [references/command-cookbook.md](./references/command-cookbook.md)
- [README.zh-CN.md](./README.zh-CN.md)
