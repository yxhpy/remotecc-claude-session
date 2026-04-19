from __future__ import annotations

import argparse
import json
import secrets
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from remotecc.ssh import LocalDependencyError, RemoteCommandError, RemoteRunner, q
from remotecc.store import SessionRecord, SessionStore, utc_now


DEFAULT_REMOTE_ROOT = "~/.remotecc/workspaces"
DEFAULT_CLAUDE_COMMAND = "claude"
DEFAULT_CAPTURE_LINES = 160
DEFAULT_EXCLUDES = [".git/", ".remotecc/", ".DS_Store"]
MODEL_SWITCH_TIMEOUT = 20

MODEL_ALIASES = {
    "default": "Use Claude Code's account/provider default model.",
    "best": "Use the most capable available model. Claude Code docs say this is currently equivalent to opus.",
    "sonnet": "Daily coding model for normal implementation, bug fixes, and refactors.",
    "opus": "Highest-capability reasoning model for architecture, hard debugging, and risky changes.",
    "haiku": "Fast and cheap model for simple tasks, summaries, and low-risk boilerplate.",
    "sonnet[1m]": "Sonnet with extended 1M context for long sessions or large repos.",
    "opus[1m]": "Opus with extended 1M context for long, difficult sessions.",
    "opusplan": "Hybrid mode: Opus in plan mode, then Sonnet in execution mode.",
}

MODEL_PROFILES = {
    "simple": {
        "model": "haiku",
        "when": "Simple listing, grep, summaries, tiny edits, and low-risk repetitive work.",
    },
    "standard": {
        "model": "sonnet",
        "when": "Default daily coding: implementation, normal bug fixes, and medium-complexity refactors.",
    },
    "complex": {
        "model": "opus",
        "when": "Architecture, ambiguous debugging, risky migrations, and deep review/reasoning.",
    },
    "plan": {
        "model": "opusplan",
        "when": "Need strong planning quality but still want efficient execution afterwards.",
    },
    "long": {
        "model": "sonnet[1m]",
        "when": "Big repo scans or long-context sessions where standard context is the main constraint.",
    },
}


@dataclass
class RemoteStatus:
    workspace_exists: bool
    tmux_exists: bool
    pane_command: str
    claude_running: bool


@dataclass
class ReadinessStatus:
    ready: bool
    auth_mode: str
    control_master_active: bool
    remote_reachable: bool
    workspace_exists: bool
    tmux_exists: bool
    claude_installed: bool
    configured_model: str | None
    configured_profile: str | None
    reason: str


def fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def sanitize_name(value: str) -> str:
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {"-", "_"}:
            allowed.append(char)
        elif char in {".", " "}:
            allowed.append("-")
    normalized = "".join(allowed).strip("-_")
    return normalized or f"session-{secrets.token_hex(2)}"


def make_session_id(name: str) -> str:
    return f"{sanitize_name(name)}-{secrets.token_hex(3)}"


def remote_workspace_path(remote_root: str, session_id: str) -> str:
    return str(PurePosixPath(remote_root) / session_id)


def remote_tmux_name(session_id: str) -> str:
    return f"remotecc_{session_id.replace('-', '_')}"


def default_control_path(session_id: str) -> str:
    return str((Path.home() / ".remotecc" / "control" / f"{session_id}.sock").expanduser())


def resolve_local_dir(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"local directory does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"local path is not a directory: {path}")
    return path


def resolve_store() -> SessionStore:
    return SessionStore()


def resolve_runner() -> RemoteRunner:
    return RemoteRunner()


def shell_path(value: str) -> str:
    if value == "~":
        return "$HOME"
    if value.startswith("~/"):
        return f"$HOME/{q(value[2:])}"
    return q(value)


def configured_model_label(record: SessionRecord) -> str:
    return record.model or "default"


def normalize_model_selection(
    explicit_model: str | None,
    profile: str | None,
) -> tuple[str | None, str | None]:
    if explicit_model and profile:
        raise ValueError("use either --model or --profile, not both")
    if profile is None:
        return explicit_model, None
    if profile not in MODEL_PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    return MODEL_PROFILES[profile]["model"], profile


def serialize_model_catalog() -> dict:
    return {
        "aliases": MODEL_ALIASES,
        "profiles": MODEL_PROFILES,
        "notes": {
            "default": "Claude Code default depends on account/provider tier.",
            "best": "Claude Code docs currently say best is equivalent to opus.",
            "recommended_skill_default": "sonnet",
            "recommended_long_context_default": "sonnet[1m]",
        },
    }


def print_model_catalog(*, json_mode: bool) -> None:
    payload = serialize_model_catalog()
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
        return

    print("Aliases:")
    for alias, description in MODEL_ALIASES.items():
        print(f"{alias}\t{description}")
    print()
    print("Profiles:")
    for profile, item in MODEL_PROFILES.items():
        print(f"{profile}\t{item['model']}\t{item['when']}")
    print()
    print("Notes:")
    for key, value in payload["notes"].items():
        print(f"{key}: {value}")


def resolve_remote_home(
    runner: RemoteRunner,
    ssh_target: str,
    *,
    control_path: str | None = None,
) -> str:
    result = runner.ssh(
        ssh_target,
        'set -euo pipefail\nprintf "%s\\n" "$HOME"',
        control_path=control_path,
        batch_mode=bool(control_path),
    )
    return result.stdout.strip()


def resolve_remote_root_path(
    runner: RemoteRunner,
    ssh_target: str,
    remote_root: str,
    *,
    control_path: str | None = None,
) -> str:
    if remote_root == "~":
        remote_root = resolve_remote_home(runner, ssh_target, control_path=control_path)
    elif remote_root.startswith("~/"):
        remote_root = str(PurePosixPath(resolve_remote_home(runner, ssh_target, control_path=control_path)) / remote_root[2:])

    script = f"""
set -euo pipefail
resolved={q(remote_root)}
mkdir -p "$resolved"
cd "$resolved"
pwd -P
"""
    result = runner.ssh(
        ssh_target,
        script,
        control_path=control_path,
        batch_mode=bool(control_path),
    )
    return result.stdout.strip()


def require_control_connection(record: SessionRecord, runner: RemoteRunner) -> None:
    if not record.control_path:
        return
    if runner.check_master(record.ssh_target, record.control_path):
        return
    raise RemoteCommandError(
        f"ssh control connection is not active for session {record.name}; "
        f"run `remotecc connect {record.session_id}` and enter your password"
    )


def ensure_open_session(record: SessionRecord, action: str) -> None:
    if record.status == "closed":
        raise ValueError(f"session is closed; cannot {action}: {record.session_id}")


def is_claude_process_name(value: str) -> bool:
    name = value.strip()
    return name in {"claude", "claude-code"} or name.endswith("claude")


def resolve_remote_command(
    record: SessionRecord,
    runner: RemoteRunner,
    *,
    required: bool,
) -> str | None:
    parts = shlex.split(record.claude_command)
    if not parts:
        if required:
            raise RemoteCommandError("claude command is empty")
        return None

    binary = parts[0]
    if binary == "~":
        script = 'set -euo pipefail\nprintf "%s\\n" "$HOME"'
    elif binary.startswith("~/"):
        script = (
            "set -euo pipefail\n"
            f'candidate="$HOME/{binary[2:]}"\n'
            'if [ -x "$candidate" ]; then printf "%s\\n" "$candidate"; fi'
        )
    elif "/" in binary:
        script = (
            "set -euo pipefail\n"
            f"candidate={q(binary)}\n"
            'if [ -x "$candidate" ]; then printf "%s\\n" "$candidate"; fi'
        )
    else:
        script = (
            "set -euo pipefail\n"
            f"if resolved=$(command -v {q(binary)} 2>/dev/null); then\n"
            '  printf "%s\\n" "$resolved"\n'
            f'elif [ -x "$HOME/.local/bin/{binary}" ]; then\n'
            f'  printf "%s\\n" "$HOME/.local/bin/{binary}"\n'
            "fi\n"
        )

    result = runner.ssh(
        record.ssh_target,
        script,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
        check=False,
    )
    resolved_binary = result.stdout.strip()
    if not resolved_binary:
        if required:
            raise RemoteCommandError(f"{binary} is not installed or not executable on the remote host")
        return None
    return shlex.join([resolved_binary, *parts[1:]])


def build_claude_launch_command(record: SessionRecord, runner: RemoteRunner) -> str:
    resolved_command = resolve_remote_command(record, runner, required=True)
    parts = shlex.split(resolved_command)
    if record.model:
        if "--model" in parts:
            raise ValueError("do not use --claude-command with --model at the same time; set the model via --model/--profile")
        parts.extend(["--model", record.model])
    return shlex.join(parts)


def ensure_remote_shell(record: SessionRecord, runner: RemoteRunner) -> None:
    script = f"""
set -euo pipefail
command -v tmux >/dev/null 2>&1
mkdir -p {shell_path(record.remote_dir)}
if ! tmux has-session -t {q(record.tmux_session)} 2>/dev/null; then
  tmux new-session -d -s {q(record.tmux_session)} -c {shell_path(record.remote_dir)}
fi
"""
    require_control_connection(record, runner)
    runner.ssh(record.ssh_target, script, control_path=record.control_path, batch_mode=bool(record.control_path))


def probe_remote(record: SessionRecord, runner: RemoteRunner) -> RemoteStatus:
    script = f"""
set -euo pipefail
workspace_exists=0
tmux_exists=0
pane_command=""
claude_running=0

if [ -d {shell_path(record.remote_dir)} ]; then
  workspace_exists=1
fi

if command -v tmux >/dev/null 2>&1 && tmux has-session -t {q(record.tmux_session)} 2>/dev/null; then
  tmux_exists=1
  pane_command="$(tmux display-message -p -t {q(record.tmux_session)}:0.0 '#{{pane_current_command}}' || true)"
  if [ "$pane_command" = "claude" ] || [ "$pane_command" = "claude-code" ]; then
    claude_running=1
  fi
fi

printf 'workspace_exists=%s\\n' "$workspace_exists"
printf 'tmux_exists=%s\\n' "$tmux_exists"
printf 'pane_command=%s\\n' "$pane_command"
printf 'claude_running=%s\\n' "$claude_running"
"""
    require_control_connection(record, runner)
    result = runner.ssh(
        record.ssh_target,
        script,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
    )
    values = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        values[key.strip()] = raw.strip()
    return RemoteStatus(
        workspace_exists=values.get("workspace_exists") == "1",
        tmux_exists=values.get("tmux_exists") == "1",
        pane_command=values.get("pane_command", ""),
        claude_running=values.get("claude_running") == "1",
    )


def probe_remote_safe(record: SessionRecord, runner: RemoteRunner) -> RemoteStatus:
    try:
        return probe_remote(record, runner)
    except RemoteCommandError:
        if record.status == "closed":
            return RemoteStatus(
                workspace_exists=False,
                tmux_exists=False,
                pane_command="",
                claude_running=False,
            )
        raise


def check_readiness(record: SessionRecord, runner: RemoteRunner) -> ReadinessStatus:
    control_master_active = True
    if record.auth_mode == "control_master":
        control_master_active = bool(record.control_path) and runner.check_master(record.ssh_target, record.control_path)
        if not control_master_active:
            return ReadinessStatus(
                ready=False,
                auth_mode=record.auth_mode,
                control_master_active=False,
                remote_reachable=False,
                workspace_exists=False,
                tmux_exists=False,
                claude_installed=False,
                configured_model=record.model,
                configured_profile=record.model_profile,
                reason="control master is not active; run `remotecc connect <session>` first",
            )

    script = f"""
set -euo pipefail
workspace_exists=0
tmux_exists=0
if [ -d {shell_path(record.remote_dir)} ]; then
  workspace_exists=1
fi
if command -v tmux >/dev/null 2>&1; then
  tmux_exists=1
fi
printf 'workspace_exists=%s\\n' "$workspace_exists"
printf 'tmux_exists=%s\\n' "$tmux_exists"
"""
    try:
        result = runner.ssh(
            record.ssh_target,
            script,
            control_path=record.control_path,
            batch_mode=True,
        )
    except RemoteCommandError as exc:
        return ReadinessStatus(
            ready=False,
            auth_mode=record.auth_mode,
            control_master_active=control_master_active,
            remote_reachable=False,
            workspace_exists=False,
            tmux_exists=False,
            claude_installed=False,
            configured_model=record.model,
            configured_profile=record.model_profile,
            reason=str(exc),
        )

    values = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, raw = line.split("=", 1)
        values[key.strip()] = raw.strip()

    workspace_exists = values.get("workspace_exists") == "1"
    tmux_exists = values.get("tmux_exists") == "1"
    claude_installed = resolve_remote_command(record, runner, required=False) is not None

    reasons = []
    if not workspace_exists:
        reasons.append("remote workspace is missing")
    if not tmux_exists:
        reasons.append("tmux is not installed on the remote host")
    if not claude_installed:
        reasons.append("claude CLI is not installed or not executable on the remote host")

    return ReadinessStatus(
        ready=not reasons,
        auth_mode=record.auth_mode,
        control_master_active=control_master_active,
        remote_reachable=True,
        workspace_exists=workspace_exists,
        tmux_exists=tmux_exists,
        claude_installed=claude_installed,
        configured_model=record.model,
        configured_profile=record.model_profile,
        reason="ok" if not reasons else "; ".join(reasons),
    )


def start_claude(record: SessionRecord, runner: RemoteRunner, *, restart: bool = False) -> None:
    ensure_remote_shell(record, runner)
    launch_command = build_claude_launch_command(record, runner)
    start_cmd = f"cd {shell_path(record.remote_dir)} && {launch_command}"
    script = f"""
set -euo pipefail
if ! tmux has-session -t {q(record.tmux_session)} 2>/dev/null; then
  tmux new-session -d -s {q(record.tmux_session)} -c {shell_path(record.remote_dir)}
fi
current_cmd="$(tmux display-message -p -t {q(record.tmux_session)}:0.0 '#{{pane_current_command}}' || true)"
if [ "$current_cmd" = "claude" ] || [ "$current_cmd" = "claude-code" ]; then
  if [ "{1 if restart else 0}" = "0" ]; then
    exit 0
  fi
fi
tmux send-keys -t {q(record.tmux_session)} C-c
sleep 0.2
tmux send-keys -t {q(record.tmux_session)} {q(start_cmd)} C-m
"""
    runner.ssh(
        record.ssh_target,
        script,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
    )


def capture_pane(record: SessionRecord, runner: RemoteRunner, *, lines: int = DEFAULT_CAPTURE_LINES) -> str:
    script = f"""
set -euo pipefail
tmux has-session -t {q(record.tmux_session)} 2>/dev/null
tmux capture-pane -p -t {q(record.tmux_session)} -S -{int(lines)}
"""
    return runner.ssh(
        record.ssh_target,
        script,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
    ).stdout


def send_buffer(record: SessionRecord, runner: RemoteRunner, text: str) -> None:
    buffer_name = f"remotecc_{record.session_id}"
    script = f"""
set -euo pipefail
tmp_file="$(mktemp)"
cat > "$tmp_file"
tmux load-buffer -b {q(buffer_name)} "$tmp_file"
tmux paste-buffer -p -t {q(record.tmux_session)} -b {q(buffer_name)}
tmux send-keys -t {q(record.tmux_session)} C-m
rm -f "$tmp_file"
tmux delete-buffer -b {q(buffer_name)} >/dev/null 2>&1 || true
"""
    runner.ssh(
        record.ssh_target,
        script,
        stdin_text=text,
        check=True,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
    )


def wait_for_quiet_output(
    record: SessionRecord,
    runner: RemoteRunner,
    *,
    timeout_seconds: int,
    poll_interval: float,
    lines: int,
) -> str:
    started = time.monotonic()
    previous = capture_pane(record, runner, lines=lines)
    stable_rounds = 0

    while time.monotonic() - started < timeout_seconds:
        time.sleep(poll_interval)
        current = capture_pane(record, runner, lines=lines)
        if current == previous:
            stable_rounds += 1
            if stable_rounds >= 2:
                return current
            continue

        stable_rounds = 0
        previous_lines = previous.splitlines()
        current_lines = current.splitlines()
        shared = 0
        for old, new in zip(previous_lines, current_lines):
            if old != new:
                break
            shared += 1
        delta = current_lines[shared:]
        if delta:
            print("\n".join(delta))
        previous = current

    return previous


def maybe_switch_running_model(
    record: SessionRecord,
    runner: RemoteRunner,
    *,
    target_model: str | None,
) -> None:
    if not target_model:
        return
    remote_status = probe_remote(record, runner)
    if not remote_status.claude_running:
        return
    send_buffer(record, runner, f"/model {target_model}")
    wait_for_quiet_output(
        record,
        runner,
        timeout_seconds=MODEL_SWITCH_TIMEOUT,
        poll_interval=1.0,
        lines=120,
    )


def apply_model_selection(
    record: SessionRecord,
    runner: RemoteRunner,
    *,
    explicit_model: str | None,
    profile: str | None,
    switch_running: bool,
) -> bool:
    selected_model, selected_profile = normalize_model_selection(explicit_model, profile)
    if explicit_model is None and profile is None:
        return False

    changed = record.model != selected_model or record.model_profile != selected_profile
    record.model = selected_model
    record.model_profile = selected_profile
    if changed and switch_running:
        maybe_switch_running_model(record, runner, target_model=selected_model)
    return changed


def send_to_claude(record: SessionRecord, runner: RemoteRunner, prompt: str) -> None:
    status = probe_remote(record, runner)
    if not status.tmux_exists or not status.claude_running:
        start_claude(record, runner)
    send_buffer(record, runner, prompt)


def format_status(record: SessionRecord, remote_status: RemoteStatus) -> str:
    return "\n".join(
        [
            f"session_id: {record.session_id}",
            f"name: {record.name}",
            f"status: {record.status}",
            f"ssh_target: {record.ssh_target}",
            f"local_dir: {record.local_dir}",
            f"remote_dir: {record.remote_dir}",
            f"tmux_session: {record.tmux_session}",
            f"claude_command: {record.claude_command}",
            f"model: {configured_model_label(record)}",
            f"model_profile: {record.model_profile or '-'}",
            f"auth_mode: {record.auth_mode}",
            f"workspace_exists: {'yes' if remote_status.workspace_exists else 'no'}",
            f"tmux_exists: {'yes' if remote_status.tmux_exists else 'no'}",
            f"pane_command: {remote_status.pane_command or '-'}",
            f"claude_running: {'yes' if remote_status.claude_running else 'no'}",
            f"last_push_at: {record.last_push_at or '-'}",
            f"last_pull_at: {record.last_pull_at or '-'}",
            f"last_seen_at: {record.last_seen_at or '-'}",
            f"updated_at: {record.updated_at}",
            f"control_path: {record.control_path or '-'}",
        ]
    )


def cmd_models(args: argparse.Namespace) -> int:
    print_model_catalog(json_mode=args.json)
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    local_dir = resolve_local_dir(args.local_dir)
    for existing in store.list_sessions():
        if existing.name == args.name and existing.status != "closed":
            return fail(f"active session name already exists: {args.name}")

    model, model_profile = normalize_model_selection(args.model, args.profile)
    session_id = make_session_id(args.name)
    control_path = default_control_path(session_id) if args.password_auth else None
    if control_path:
        runner.start_master(args.ssh_target, control_path)

    remote_root = resolve_remote_root_path(
        runner,
        args.ssh_target,
        args.remote_root,
        control_path=control_path,
    )
    record = SessionRecord(
        session_id=session_id,
        name=args.name,
        local_dir=str(local_dir),
        ssh_target=args.ssh_target,
        remote_root=remote_root,
        remote_dir=remote_workspace_path(remote_root, session_id),
        tmux_session=remote_tmux_name(session_id),
        claude_command=args.claude_command,
        model=model,
        model_profile=model_profile,
        auth_mode="control_master" if args.password_auth else "key",
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
        control_path=control_path,
    )

    ensure_remote_shell(record, runner)
    runner.rsync_push(
        local_dir,
        record.ssh_target,
        record.remote_dir,
        delete=args.delete,
        excludes=DEFAULT_EXCLUDES,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
    )
    record.last_push_at = utc_now()
    store.create_session(record)

    print(f"created session {record.name} ({record.session_id})")
    print(f"remote_dir: {record.remote_dir}")
    print(f"tmux_session: {record.tmux_session}")
    print(f"model: {configured_model_label(record)}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = resolve_store()
    sessions = store.list_sessions(include_closed=args.all)
    if not sessions:
        print("no sessions")
        return 0
    for record in sessions:
        print(
            "\t".join(
                [
                    record.session_id,
                    record.name,
                    record.status,
                    configured_model_label(record),
                    record.ssh_target,
                    record.remote_dir,
                ]
            )
        )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session, include_closed=True)
    remote_status = probe_remote_safe(record, runner)
    record.last_seen_at = utc_now()
    store.save_session(record)
    print(format_status(record, remote_status))
    return 0


def cmd_ready(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session, include_closed=True)
    readiness = check_readiness(record, runner)
    payload = {
        "session_id": record.session_id,
        "name": record.name,
        "ready": readiness.ready,
        "auth_mode": readiness.auth_mode,
        "control_master_active": readiness.control_master_active,
        "remote_reachable": readiness.remote_reachable,
        "workspace_exists": readiness.workspace_exists,
        "tmux_exists": readiness.tmux_exists,
        "claude_installed": readiness.claude_installed,
        "configured_model": readiness.configured_model or "default",
        "configured_profile": readiness.configured_profile,
        "reason": readiness.reason,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return 0 if readiness.ready else 1


def cmd_connect(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session, include_closed=True)
    if not record.control_path:
        return fail("session is not configured for password-auth control connection")
    runner.start_master(record.ssh_target, record.control_path)
    record.last_seen_at = utc_now()
    store.save_session(record)
    print(f"connected ssh control master for {record.name}")
    return 0


def cmd_set_model(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session, include_closed=True)
    changed = apply_model_selection(
        record,
        runner,
        explicit_model=args.model,
        profile=args.profile,
        switch_running=record.status != "closed",
    )
    if not changed:
        print(f"model unchanged: {configured_model_label(record)}")
        return 0
    store.save_session(record)
    print(f"configured model for {record.name}: {configured_model_label(record)}")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session)
    ensure_open_session(record, "push")
    remote_status = probe_remote(record, runner)
    if remote_status.claude_running and not args.force:
        return fail("claude is running remotely; use --force to push anyway")
    runner.rsync_push(
        Path(record.local_dir),
        record.ssh_target,
        record.remote_dir,
        delete=args.delete,
        excludes=DEFAULT_EXCLUDES,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
    )
    record.last_push_at = utc_now()
    store.save_session(record)
    print(f"pushed {record.local_dir} -> {record.ssh_target}:{record.remote_dir}")
    return 0


def cmd_pull(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session, include_closed=True)
    remote_status = probe_remote(record, runner)
    if remote_status.claude_running and not args.force:
        return fail("claude is running remotely; use --force to pull anyway")
    runner.rsync_pull(
        record.ssh_target,
        record.remote_dir,
        Path(record.local_dir),
        delete=args.delete,
        excludes=DEFAULT_EXCLUDES,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
    )
    record.last_pull_at = utc_now()
    store.save_session(record)
    print(f"pulled {record.ssh_target}:{record.remote_dir} -> {record.local_dir}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session)
    ensure_open_session(record, "start")
    apply_model_selection(
        record,
        runner,
        explicit_model=args.model,
        profile=args.profile,
        switch_running=False,
    )
    start_claude(record, runner, restart=args.restart or bool(args.model or args.profile))
    record.last_seen_at = utc_now()
    store.save_session(record)
    print(f"claude started in tmux session {record.tmux_session}")
    print(f"model: {configured_model_label(record)}")
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session)
    ensure_open_session(record, "send")
    prompt = args.text if args.text is not None else sys.stdin.read()
    if not prompt.strip():
        return fail("prompt is empty")

    apply_model_selection(
        record,
        runner,
        explicit_model=args.model,
        profile=args.profile,
        switch_running=True,
    )
    send_to_claude(record, runner, prompt)
    record.last_seen_at = utc_now()
    store.save_session(record)
    if args.wait:
        final_capture = wait_for_quiet_output(
            record,
            runner,
            timeout_seconds=args.timeout,
            poll_interval=args.poll_interval,
            lines=args.lines,
        )
        if not final_capture.endswith("\n"):
            print()
    else:
        print("prompt sent")
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session, include_closed=True)
    print(capture_pane(record, runner, lines=args.lines), end="")
    return 0


def cmd_attach(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session, include_closed=True)
    ensure_open_session(record, "attach")
    ensure_remote_shell(record, runner)
    runner.ssh(
        record.ssh_target,
        f"tmux attach -t {q(record.tmux_session)}",
        tty=True,
        check=True,
        control_path=record.control_path,
        batch_mode=bool(record.control_path),
    )
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session, include_closed=True)

    if args.pull:
        status = probe_remote(record, runner)
        if status.claude_running and not args.force:
            return fail("claude is still running remotely; use --force with --pull or stop it first")
        runner.rsync_pull(
            record.ssh_target,
            record.remote_dir,
            Path(record.local_dir),
            delete=args.delete,
            excludes=DEFAULT_EXCLUDES,
            control_path=record.control_path,
            batch_mode=bool(record.control_path),
        )
        record.last_pull_at = utc_now()

    if args.kill_remote:
        runner.ssh(
            record.ssh_target,
            f"set -euo pipefail\n"
            f"tmux kill-session -t {q(record.tmux_session)} 2>/dev/null || true\n"
            + (f"rm -rf {q(record.remote_dir)}\n" if args.drop_remote else ""),
            control_path=record.control_path,
            batch_mode=bool(record.control_path),
        )

    if record.control_path:
        runner.stop_master(record.ssh_target, record.control_path)

    record.status = "closed"
    store.save_session(record)
    print(f"closed session {record.name} ({record.session_id})")
    return 0


def print_chat_help() -> None:
    print(":help            show commands")
    print(":capture         print the latest pane capture")
    print(":attach          attach to remote tmux directly")
    print(":pull            rsync remote workspace back locally")
    print(":push            rsync local workspace to remote if Claude is not running")
    print(":status          print remote session status")
    print(":models          print model routing guidance")
    print(":model <alias>   switch model in the running Claude session")
    print(":exit            leave chat mode")


def cmd_chat(args: argparse.Namespace) -> int:
    store = resolve_store()
    runner = resolve_runner()
    record = store.get_session(args.session)
    ensure_open_session(record, "chat")
    start_claude(record, runner)
    print(f"chat session: {record.name} ({record.session_id})")
    print(f"model: {configured_model_label(record)}")
    print("type :help for commands")

    while True:
        try:
            line = input("remotecc> ")
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            break

        message = line.strip()
        if not message:
            continue
        if message == ":help":
            print_chat_help()
            continue
        if message == ":capture":
            print(capture_pane(record, runner, lines=args.lines), end="")
            continue
        if message == ":attach":
            runner.ssh(
                record.ssh_target,
                f"tmux attach -t {q(record.tmux_session)}",
                tty=True,
                check=True,
                control_path=record.control_path,
                batch_mode=bool(record.control_path),
            )
            continue
        if message == ":pull":
            status = probe_remote(record, runner)
            if status.claude_running:
                print("claude is running; use `remotecc pull ... --force` outside chat if you really need this")
                continue
            runner.rsync_pull(
                record.ssh_target,
                record.remote_dir,
                Path(record.local_dir),
                excludes=DEFAULT_EXCLUDES,
                control_path=record.control_path,
                batch_mode=bool(record.control_path),
            )
            record.last_pull_at = utc_now()
            store.save_session(record)
            print("pulled remote changes")
            continue
        if message == ":push":
            status = probe_remote(record, runner)
            if status.claude_running:
                print("claude is running; refusing push")
                continue
            runner.rsync_push(
                Path(record.local_dir),
                record.ssh_target,
                record.remote_dir,
                excludes=DEFAULT_EXCLUDES,
                control_path=record.control_path,
                batch_mode=bool(record.control_path),
            )
            record.last_push_at = utc_now()
            store.save_session(record)
            print("pushed local changes")
            continue
        if message == ":status":
            status = probe_remote(record, runner)
            record.last_seen_at = utc_now()
            store.save_session(record)
            print(format_status(record, status))
            continue
        if message == ":models":
            print_model_catalog(json_mode=False)
            continue
        if message.startswith(":model "):
            alias = message.split(maxsplit=1)[1].strip()
            record.model = alias
            record.model_profile = None
            maybe_switch_running_model(record, runner, target_model=alias)
            store.save_session(record)
            print(f"model switched to {alias}")
            continue
        if message == ":exit":
            break

        send_to_claude(record, runner, line)
        wait_for_quiet_output(
            record,
            runner,
            timeout_seconds=args.timeout,
            poll_interval=args.poll_interval,
            lines=args.lines,
        )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remotecc",
        description="Manage remote Claude CLI workspaces over SSH + tmux.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    models = subparsers.add_parser("models", help="print machine-readable Claude model guidance for skill routing")
    models.add_argument("--json", action="store_true")
    models.set_defaults(func=cmd_models)

    create = subparsers.add_parser("create", help="create a new remote session")
    create.add_argument("name")
    create.add_argument("ssh_target")
    create.add_argument("--local-dir", default=".")
    create.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    create.add_argument("--claude-command", default=DEFAULT_CLAUDE_COMMAND)
    model_group = create.add_mutually_exclusive_group()
    model_group.add_argument("--model")
    model_group.add_argument("--profile", choices=sorted(MODEL_PROFILES))
    create.add_argument("--password-auth", action="store_true", help="use a session-scoped SSH control master and prompt once for password")
    create.add_argument("--delete", action="store_true", help="mirror local files and delete remote extras on initial push")
    create.set_defaults(func=cmd_create)

    list_cmd = subparsers.add_parser("list", help="list sessions")
    list_cmd.add_argument("--all", action="store_true")
    list_cmd.set_defaults(func=cmd_list)

    status = subparsers.add_parser("status", help="inspect one session")
    status.add_argument("session")
    status.set_defaults(func=cmd_status)

    ready = subparsers.add_parser("ready", help="check whether a session is usable non-interactively by a skill")
    ready.add_argument("session")
    ready.add_argument("--json", action="store_true")
    ready.set_defaults(func=cmd_ready)

    connect = subparsers.add_parser("connect", help="open or refresh the ssh control master for a password-auth session")
    connect.add_argument("session")
    connect.set_defaults(func=cmd_connect)

    set_model = subparsers.add_parser("set-model", help="persist or switch the configured Claude model for a session")
    set_model.add_argument("session")
    set_group = set_model.add_mutually_exclusive_group(required=True)
    set_group.add_argument("--model")
    set_group.add_argument("--profile", choices=sorted(MODEL_PROFILES))
    set_model.set_defaults(func=cmd_set_model)

    push = subparsers.add_parser("push", help="sync local files to the remote workspace")
    push.add_argument("session")
    push.add_argument("--delete", action="store_true")
    push.add_argument("--force", action="store_true")
    push.set_defaults(func=cmd_push)

    pull = subparsers.add_parser("pull", help="sync remote files back to the local workspace")
    pull.add_argument("session")
    pull.add_argument("--delete", action="store_true")
    pull.add_argument("--force", action="store_true")
    pull.set_defaults(func=cmd_pull)

    start = subparsers.add_parser("start", help="start Claude in the remote tmux session")
    start.add_argument("session")
    start_group = start.add_mutually_exclusive_group()
    start_group.add_argument("--model")
    start_group.add_argument("--profile", choices=sorted(MODEL_PROFILES))
    start.add_argument("--restart", action="store_true", help="restart Claude even if it is already running")
    start.set_defaults(func=cmd_start)

    send = subparsers.add_parser("send", help="send one prompt to the remote Claude session")
    send.add_argument("session")
    send.add_argument("--text")
    send_group = send.add_mutually_exclusive_group()
    send_group.add_argument("--model")
    send_group.add_argument("--profile", choices=sorted(MODEL_PROFILES))
    send.add_argument("--wait", action=argparse.BooleanOptionalAction, default=True)
    send.add_argument("--timeout", type=int, default=90)
    send.add_argument("--poll-interval", type=float, default=1.2)
    send.add_argument("--lines", type=int, default=DEFAULT_CAPTURE_LINES)
    send.set_defaults(func=cmd_send)

    capture = subparsers.add_parser("capture", help="print recent tmux pane output")
    capture.add_argument("session")
    capture.add_argument("--lines", type=int, default=DEFAULT_CAPTURE_LINES)
    capture.set_defaults(func=cmd_capture)

    attach = subparsers.add_parser("attach", help="attach to the remote tmux session")
    attach.add_argument("session")
    attach.set_defaults(func=cmd_attach)

    close = subparsers.add_parser("close", help="close a session")
    close.add_argument("session")
    close.add_argument("--pull", action="store_true")
    close.add_argument("--delete", action="store_true", help="delete local extras during --pull")
    close.add_argument("--force", action="store_true")
    close.add_argument("--kill-remote", action=argparse.BooleanOptionalAction, default=True)
    close.add_argument("--drop-remote", action="store_true")
    close.set_defaults(func=cmd_close)

    chat = subparsers.add_parser("chat", help="enter a minimal local REPL")
    chat.add_argument("session")
    chat.add_argument("--timeout", type=int, default=90)
    chat.add_argument("--poll-interval", type=float, default=1.2)
    chat.add_argument("--lines", type=int, default=DEFAULT_CAPTURE_LINES)
    chat.set_defaults(func=cmd_chat)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (LocalDependencyError, RemoteCommandError, ValueError, KeyError) as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
