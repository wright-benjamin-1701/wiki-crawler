"""Tiny git helpers for provenance metadata."""

from __future__ import annotations

import subprocess


def get_git_commit(cwd: str | None = None) -> str:
    """Return the short git commit SHA, or ``"unknown"`` when not in a repo.

    Never raises — provenance metadata must not break an extraction run.
    """
    try:
        out = subprocess.run(  # noqa: S603 — fixed, trusted command
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except Exception:  # noqa: BLE001 — any failure falls back gracefully
        return "unknown"
    sha = out.stdout.strip()
    return sha[:12] if len(sha) == 40 else (sha or "unknown")
