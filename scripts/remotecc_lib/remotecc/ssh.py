from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class LocalDependencyError(RuntimeError):
    pass


class RemoteCommandError(RuntimeError):
    pass


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def ensure_local_binary(name: str) -> None:
    if shutil.which(name) is None:
        raise LocalDependencyError(f"required local binary not found: {name}")


def q(value: str) -> str:
    return shlex.quote(value)


class RemoteRunner:
    def __init__(self, ssh_bin: str = "ssh", rsync_bin: str = "rsync") -> None:
        self.ssh_bin = ssh_bin
        self.rsync_bin = rsync_bin
        ensure_local_binary(self.ssh_bin)
        ensure_local_binary(self.rsync_bin)

    def _ssh_options(
        self,
        *,
        control_path: str | None = None,
        batch_mode: bool = False,
    ) -> list[str]:
        options: list[str] = []
        if control_path:
            options.extend(
                [
                    "-o",
                    "ControlMaster=auto",
                    "-o",
                    "ControlPersist=15m",
                    "-o",
                    f"ControlPath={control_path}",
                ]
            )
        if batch_mode:
            options.extend(["-o", "BatchMode=yes"])
        return options

    def start_master(self, target: str, control_path: str, *, persist: str = "15m") -> None:
        Path(control_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ssh_bin,
            "-o",
            "ControlMaster=yes",
            "-o",
            f"ControlPersist={persist}",
            "-o",
            f"ControlPath={control_path}",
            "-fN",
            target,
        ]
        completed = subprocess.run(cmd, text=True, check=False)
        if completed.returncode != 0:
            raise RemoteCommandError(f"failed to open ssh control master for {target}")

    def check_master(self, target: str, control_path: str) -> bool:
        cmd = [
            self.ssh_bin,
            "-O",
            "check",
            "-o",
            f"ControlPath={control_path}",
            target,
        ]
        completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
        return completed.returncode == 0

    def stop_master(self, target: str, control_path: str) -> None:
        cmd = [
            self.ssh_bin,
            "-O",
            "exit",
            "-o",
            f"ControlPath={control_path}",
            target,
        ]
        subprocess.run(cmd, text=True, capture_output=True, check=False)
        Path(control_path).expanduser().unlink(missing_ok=True)

    def _rsync_base_cmd(self) -> list[str]:
        # macOS often ships an old/openrsync-compatible client that rejects newer
        # GNU-only flags such as `--info=stats1`, so keep the MVP conservative.
        return [
            self.rsync_bin,
            "-az",
        ]

    def ssh(
        self,
        target: str,
        script: str,
        *,
        stdin_text: str | None = None,
        tty: bool = False,
        check: bool = True,
        control_path: str | None = None,
        batch_mode: bool = False,
    ) -> CommandResult:
        cmd = [self.ssh_bin]
        if tty:
            cmd.append("-t")
        cmd.extend(self._ssh_options(control_path=control_path, batch_mode=batch_mode))
        cmd.extend([target, f"bash -lc {q(script)}"])
        completed = subprocess.run(
            cmd,
            input=stdin_text,
            text=True,
            capture_output=not tty,
            check=False,
        )
        result = CommandResult(
            returncode=completed.returncode,
            stdout="" if tty else completed.stdout,
            stderr="" if tty else completed.stderr,
        )
        if check and completed.returncode != 0:
            raise RemoteCommandError(result.stderr.strip() or f"ssh command failed with exit {completed.returncode}")
        return result

    def rsync_push(
        self,
        local_dir: Path,
        target: str,
        remote_dir: str,
        *,
        delete: bool = False,
        excludes: Sequence[str] | None = None,
        control_path: str | None = None,
        batch_mode: bool = False,
    ) -> None:
        excludes = excludes or []
        cmd = self._rsync_base_cmd()
        ssh_cmd = [self.ssh_bin, *self._ssh_options(control_path=control_path, batch_mode=batch_mode)]
        cmd.extend(["-e", shlex.join(ssh_cmd)])
        if delete:
            cmd.append("--delete")
        for item in excludes:
            cmd.append(f"--exclude={item}")
        cmd.extend([
            f"{local_dir.resolve()}/",
            f"{target}:{remote_dir}/",
        ])
        completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RemoteCommandError(completed.stderr.strip() or "rsync push failed")

    def rsync_pull(
        self,
        target: str,
        remote_dir: str,
        local_dir: Path,
        *,
        delete: bool = False,
        excludes: Sequence[str] | None = None,
        control_path: str | None = None,
        batch_mode: bool = False,
    ) -> None:
        excludes = excludes or []
        cmd = self._rsync_base_cmd()
        ssh_cmd = [self.ssh_bin, *self._ssh_options(control_path=control_path, batch_mode=batch_mode)]
        cmd.extend(["-e", shlex.join(ssh_cmd)])
        if delete:
            cmd.append("--delete")
        for item in excludes:
            cmd.append(f"--exclude={item}")
        cmd.extend([
            f"{target}:{remote_dir}/",
            f"{local_dir.resolve()}/",
        ])
        completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RemoteCommandError(completed.stderr.strip() or "rsync pull failed")
