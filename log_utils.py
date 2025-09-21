import os
import glob
from typing import Iterable


def _iter_log_images(paths: Iterable[str]) -> list[tuple[str, int, float]]:
    files: list[tuple[str, int, float]] = []
    for p in paths:
        try:
            st = os.stat(p)
            files.append((p, int(st.st_size), float(st.st_mtime)))
        except Exception:
            continue
    return files


def enforce_logs_quota(limit_mb: float = 300.0, logs_dir: str = "logs") -> None:
    """Ensure image logs under logs_dir do not exceed limit_mb.

    Deletes oldest image files first until total size <= limit.
    """
    try:
        limit_bytes = int(max(0, limit_mb) * 1024 * 1024)
        if limit_bytes <= 0:
            return
        if not os.path.isdir(logs_dir):
            return
        # Match common image extensions
        patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.gif"]
        paths: list[str] = []
        for pat in patterns:
            paths.extend(glob.glob(os.path.join(logs_dir, pat)))
        items = _iter_log_images(paths)
        total = sum(sz for _, sz, _ in items)
        if total <= limit_bytes:
            return
        # Oldest first
        items.sort(key=lambda t: t[2])
        idx = 0
        while total > limit_bytes and idx < len(items):
            p, sz, _ = items[idx]
            try:
                os.remove(p)
                total -= sz
            except Exception:
                pass
            idx += 1
    except Exception:
        # Best-effort; never raise
        return

