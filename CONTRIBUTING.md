# Contributing

Thanks for contributing to `remotecc`.

## Scope

This project is intentionally narrow:

- remote Claude Code session management
- SSH and `tmux` orchestration
- `rsync`-based push and pull workflows
- Codex skill integration

Changes that expand the project should stay consistent with that operational scope.

## Development Setup

```bash
python3 -m pip install -e .
python3 scripts/remotecc.py --help
python3 scripts/remotecc.py models --json
python3 -m compileall src
```

## Before Opening a Pull Request

Please verify:

1. The CLI still runs from the repo root through `scripts/remotecc.py`.
2. `python3 -m compileall src` succeeds.
3. `python3 scripts/remotecc.py --help` succeeds.
4. User-facing docs reflect any behavior change.
5. Session lifecycle, auth assumptions, and model routing remain explicit.

## Change Guidelines

- Prefer small, operationally clear changes.
- Do not silently widen trust or auth behavior.
- Preserve conservative compatibility with macOS-provided `rsync`.
- Keep skill-facing machine interfaces stable where possible.

## Pull Request Style

- Explain the user-facing outcome first.
- Call out behavioral changes to session lifecycle or model routing.
- Include command snippets when the change affects operator workflow.
