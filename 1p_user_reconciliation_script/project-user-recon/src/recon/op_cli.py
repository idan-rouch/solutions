# src/recon/op_cli.py
import os
import shlex
import subprocess
from typing import Optional

def _shell() -> str:
    # Use the user's login shell (fallback to /bin/zsh)
    return os.environ.get("SHELL") or "/bin/zsh"

def _run_shell(cmd_str: str) -> subprocess.CompletedProcess:
    if os.getenv("DEBUG_OP") == "1":
        print(f"[debug] shell exec: {cmd_str}")
    # -l: login shell; -c: run command string
    return subprocess.run([_shell(), "-lc", cmd_str], text=True, capture_output=True)

def _require_signed_in(account: str) -> None:
    # Make sure we’re signed into the right account in this shell context
    check = _run_shell(f"op whoami --account {shlex.quote(account)}")
    if check.returncode != 0:
        msg = (check.stderr or check.stdout or "").strip()
        raise RuntimeError(
            f"Not signed in to 1Password account '{account}'. "
            f"Run: op signin --account {account}\nDetails: {msg}"
        )

def suspend_user_cli(email: str, account: Optional[str] = None, dry_run: bool = False) -> None:
    """
    Suspend a user via 1Password CLI v2, executed through the user's login shell.
    - Forces the tenant with --account.
    - Uses your existing signed-in human session (no OP_SESSION_* needed in v2).
    - If DEBUG_OP=1, prints the exact command run.
    """
    acct = account or os.environ.get("OP_ACCOUNT") or "idanrouch.b5test.eu"
    _require_signed_in(acct)

    cmd_str = f"op user suspend {shlex.quote(email)} --account {shlex.quote(acct)}"

    if dry_run:
        if os.getenv("DEBUG_OP") == "1":
            print(f"[debug] dry-run: {cmd_str}")
        return

    cp = _run_shell(cmd_str)
    if cp.returncode != 0:
        msg = (cp.stderr or cp.stdout or "").strip() or f"op exited with code {cp.returncode}"
        raise RuntimeError(msg)
