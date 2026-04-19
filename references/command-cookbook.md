# Command Cookbook

Use the repo-root launcher:

`python3 scripts/remotecc.py ...`

## Bootstrap Examples

- Create with default daily model:
  `python3 scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard`
- Create with password-auth bootstrap:
  `python3 scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard --password-auth`
- Create with explicit risky-power mode:
  `python3 scripts/remotecc.py create demo user@host --local-dir /abs/project --model opus --claude-command "claude --dangerously-skip-permissions"`

## Readiness and Status

- Machine gate:
  `python3 scripts/remotecc.py ready demo --json`
- Human-readable status:
  `python3 scripts/remotecc.py status demo`
- Tail-safe async observation:
  `python3 scripts/remotecc.py observe demo`
- Follow until the remote run stops changing, blocks, or errors:
  `python3 scripts/remotecc.py observe demo --follow`
- Approve a detected blocker once:
  `python3 scripts/remotecc.py approve demo`
- Approve and persist edit/bash access for the current session when available:
  `python3 scripts/remotecc.py approve demo --mode session`
- If you call `approve` immediately after `start`, let it wait for the blocker instead of adding custom sleep logic:
  `python3 scripts/remotecc.py approve demo --detect-timeout 8`
- Model guidance:
  `python3 scripts/remotecc.py models --json`

## Session Operations

- Start:
  `python3 scripts/remotecc.py start demo`
- Start and force a different model:
  `python3 scripts/remotecc.py start demo --model opus --restart`
- Send one request:
  `python3 scripts/remotecc.py send demo --profile standard --text "Implement the fix and summarize the diff."`
- Send asynchronously for larger or noisier work:
  `python3 scripts/remotecc.py send demo --profile standard --text "Implement the fix and summarize the diff." --no-wait`
- Check whether it is still running, likely done, blocked, or failed:
  `python3 scripts/remotecc.py observe demo --json`
- Pull current remote edits:
  `python3 scripts/remotecc.py pull demo`
- Pull while Claude is still running:
  `python3 scripts/remotecc.py pull demo --force`
- Close and delete the remote workspace:
  `python3 scripts/remotecc.py close demo --drop-remote`

## Cheap CRUD Pattern

- Create with `haiku`:
  `python3 scripts/remotecc.py send demo --model haiku --text "Create demo/crud.txt with exactly these three lines: ... Do not run bash."`
- If `send` returns `blocked:`:
  `python3 scripts/remotecc.py approve demo --mode session`
- For longer hk work, submit first and watch the short tail instead of reading a huge pane:
  `python3 scripts/remotecc.py send demo --model haiku --text "..." --no-wait`
  `python3 scripts/remotecc.py observe demo --follow`
- Pull after the write:
  `python3 scripts/remotecc.py pull demo --force`
- Inspect locally before the next step.
- Use a separate `send` for read, another for update, and another for delete.
- Do not overlap `pull` with `close --drop-remote`; close only after the sync step has finished.

## Model Mapping

- `simple` -> `haiku`
- `standard` -> `sonnet`
- `complex` -> `opus`
- `plan` -> `opusplan`
- `long` -> `sonnet[1m]`

Use `haiku` for cheap and obvious tasks. Use `sonnet` for the default coding lane. Use `opus` for risky or ambiguous work. Use `opusplan` when planning quality matters first.

## Common Failures

- `control master is not active`
  Re-run `connect` or bootstrap again. Skills should not expect to enter passwords.
- `claude CLI is not installed or not executable`
  Fix the remote machine before trying to automate.
- First-run workspace trust or edit approval prompt inside Claude Code
  Resolve it with `approve` instead of replaying the original prompt. Use `--mode session` when you intentionally want to reduce repeated edit confirmations during a short test lane.
- Very long pane output
  Prefer `observe` first. It only reads the recent tail by default, which is safer for upstream model consumers than `capture`.
- Repo-root session plus `pull --force`
  Treat that as a destructive full sync from the remote mirror. For self-hosted tests, prefer a smaller `--local-dir` under `demo/` so a remote stale copy does not overwrite your local source tree.
