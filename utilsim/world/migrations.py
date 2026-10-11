"""Consistent, uniquely named rollback copies for opt-in world extensions."""
import os
import sqlite3
import uuid
from pathlib import Path


def rollback_backup(world, feature):
    """Call before any writes while the caller holds its transaction reservation."""
    backup = Path(world.path).with_name(Path(world.path).name + f".pre-{feature}-{uuid.uuid4().hex}.bak")
    target_path = str(backup.resolve())
    # SQLite's Windows file API needs the extended absolute form for long backup
    # names even when the shorter source file opens normally. Keep that usable
    # reference in the migration metadata so inspection/restoration can open it.
    if os.name == "nt" and len(target_path) >= 248 and not target_path.startswith("\\\\?\\"):
        target_path = ("\\\\?\\UNC\\" + target_path[2:] if target_path.startswith("\\\\")
                       else "\\\\?\\" + target_path)
    source = sqlite3.connect(Path(world.path).resolve().as_uri() + "?mode=ro", uri=True)
    target = None
    try:
        target = sqlite3.connect(target_path)
        source.backup(target)
    finally:
        source.close()
        if target is not None:
            target.close()
    return target_path
