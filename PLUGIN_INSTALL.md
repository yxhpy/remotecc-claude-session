# RemoteCC Claude Session Plugin

This repository is a Codex plugin root. The plugin manifest lives at:

```text
.codex-plugin/plugin.json
```

For automation and AI installers, prefer [AI_INSTALL.md](./AI_INSTALL.md). It
contains frontmatter plus a machine-readable JSON install manifest.

## Machine-Readable Summary

```json
{
  "type": "codex_plugin",
  "name": "remotecc-claude-session",
  "repository": "https://github.com/yxhpy/remotecc-claude-session.git",
  "install_path": "~/.codex/plugins/remotecc-claude-session",
  "manifest": ".codex-plugin/plugin.json",
  "skill": "SKILL.md",
  "marketplace": ".agents/plugins/marketplace.json",
  "requires_restart": true
}
```

## Install From Git

Clone the plugin into your local Codex plugins directory:

```bash
mkdir -p ~/.codex/plugins
git clone https://github.com/yxhpy/remotecc-claude-session.git ~/.codex/plugins/remotecc-claude-session
```

Restart Codex so the plugin and its `remotecc-claude-session` skill are discovered.

## Optional Marketplace Entry

This repository also includes:

```text
.agents/plugins/marketplace.json
```

The marketplace entry points to `./`, because this repository root is the plugin root.

## Verify

From the cloned plugin directory:

```bash
python3 scripts/remotecc.py --help
python3 scripts/remotecc.py models --json
python3 -m compileall src
```

The plugin exposes the repo-root `SKILL.md`, which instructs Codex to use
`scripts/remotecc.py` for session lifecycle, readiness, observation, approval,
model routing, and sync.
