"""Seed notebooks without overwriting user modifications; repair volume ownership."""
import os
import shutil
from pathlib import Path
for source in Path('/seed').rglob('*'):
    target = Path('/notebooks') / source.relative_to('/seed')
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    elif not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
import pwd
uid = pwd.getpwnam('spark').pw_uid
gid = pwd.getpwnam('spark').pw_gid
for path in [Path('/notebooks'), *Path('/notebooks').rglob('*')]:
    os.chown(path, uid, gid)
