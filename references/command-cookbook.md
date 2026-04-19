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
- Model guidance:
  `python3 scripts/remotecc.py models --json`

## Session Operations

- Start:
  `python3 scripts/remotecc.py start demo`
- Start and force a different model:
  `python3 scripts/remotecc.py start demo --model opus --restart`
- Send one request:
  `python3 scripts/remotecc.py send demo --profile standard --text "Implement the fix and summarize the diff."`
- Pull current remote edits:
  `python3 scripts/remotecc.py pull demo`
- Pull while Claude is still running:
  `python3 scripts/remotecc.py pull demo --force`
- Close and delete the remote workspace:
  `python3 scripts/remotecc.py close demo --drop-remote`

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
  Clear it once manually during bootstrap, or use a deliberately permissive Claude command if that is acceptable.
