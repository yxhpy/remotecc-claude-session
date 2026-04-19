# Security Policy

## Supported Versions

Security fixes are applied to the current `main` branch.

## Reporting a Vulnerability

Please do not open a public issue for credential, auth, or remote-execution vulnerabilities.

Preferred path:

1. Use GitHub Security Advisories for this repository if available.
2. If that is not available, open a private channel with the repository owner before public disclosure.

When reporting, include:

- affected command or workflow
- impact scope
- reproduction steps
- whether secrets, remote access, or privilege boundaries are involved

## Security Notes

This project manages remote command execution and SSH session reuse. In practice, the most sensitive areas are:

- SSH authentication and control sockets
- Claude CLI trust and permission prompts
- local session registry contents
- sync boundaries between local and remote workspaces
