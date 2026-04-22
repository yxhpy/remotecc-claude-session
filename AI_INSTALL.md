---
artifact_type: codex_plugin_install_guide
schema_version: "1.0"
plugin_name: remotecc-claude-session
repository_url: https://github.com/yxhpy/remotecc-claude-session
plugin_root: "."
manifest_path: .codex-plugin/plugin.json
skill_entrypoint: SKILL.md
marketplace_path: .agents/plugins/marketplace.json
default_install_path: "~/.codex/plugins/remotecc-claude-session"
requires_restart: true
---

# AI Install Guide

This repository is a Codex plugin root. Install it by cloning the repository
directly into the Codex plugins directory.

## Machine-Readable Install Manifest

```json
{
  "type": "codex_plugin",
  "name": "remotecc-claude-session",
  "source": {
    "kind": "git",
    "url": "https://github.com/yxhpy/remotecc-claude-session.git",
    "branch": "main"
  },
  "install": {
    "target_directory": "~/.codex/plugins/remotecc-claude-session",
    "commands": [
      "mkdir -p ~/.codex/plugins",
      "git clone https://github.com/yxhpy/remotecc-claude-session.git ~/.codex/plugins/remotecc-claude-session"
    ],
    "post_install": [
      "Restart Codex so the plugin manifest and skill are discovered."
    ]
  },
  "verify": {
    "working_directory": "~/.codex/plugins/remotecc-claude-session",
    "commands": [
      "python3 scripts/remotecc.py --help",
      "python3 scripts/remotecc.py models --json",
      "python3 -m compileall src",
      "python3 -m json.tool .codex-plugin/plugin.json",
      "python3 -m json.tool .agents/plugins/marketplace.json"
    ]
  },
  "entrypoints": {
    "plugin_manifest": ".codex-plugin/plugin.json",
    "skill": "SKILL.md",
    "launcher": "scripts/remotecc.py",
    "marketplace": ".agents/plugins/marketplace.json"
  },
  "capabilities": [
    "remote Claude Code session lifecycle",
    "ready and observe machine gates",
    "Claude blocker approval",
    "model routing",
    "rsync push and pull"
  ]
}
```

## Install

```bash
mkdir -p ~/.codex/plugins
git clone https://github.com/yxhpy/remotecc-claude-session.git ~/.codex/plugins/remotecc-claude-session
```

Restart Codex after cloning.

## Update

```bash
cd ~/.codex/plugins/remotecc-claude-session
git pull --ff-only
```

Restart Codex after updating.

## Verify

```bash
cd ~/.codex/plugins/remotecc-claude-session
python3 scripts/remotecc.py --help
python3 scripts/remotecc.py models --json
python3 -m compileall src
python3 -m json.tool .codex-plugin/plugin.json
python3 -m json.tool .agents/plugins/marketplace.json
```

## Use From Codex

After restart, invoke the skill by asking Codex to use:

```text
$remotecc-claude-session
```

The skill entrypoint is `SKILL.md`; it instructs agents to use
`scripts/remotecc.py` for session creation, readiness checks, observation,
approval, model routing, sync, and close.

## Uninstall

```bash
rm -rf ~/.codex/plugins/remotecc-claude-session
```

Restart Codex after removal.
