"""Reuse one exact launcher bundle per version instead of copying every launch."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .update_install import plain_path,plain_tree
from .workspace import require_space


def _snapshot(folder):
    plain_tree(folder)
    values={}
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            with path.open('rb') as handle:
                values[path.relative_to(folder).as_posix()]=hashlib.file_digest(handle,'sha256').hexdigest()
    if not values:raise ValueError('Launcher bundle is empty')
    return values


def stage_launcher(source,app):
    """Preserve active/versioned helpers; reserve peak before one atomic copy.

    Different versions have separate identities so updating cannot overwrite a
    running helper. The global workspace cap still includes every old version.
    Existing damaged caches refuse instead of being silently replaced in use.
    """
    source=plain_path(source);app=plain_path(app)
    snapshot=_snapshot(source)
    identity=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()
    cached=app.parent/('.maalimbus-launcher-'+identity)
    if cached.exists():
        if _snapshot(cached)!=snapshot:raise ValueError('Cached launcher bytes changed')
        return cached
    root=app.parent.parent if app.parent.name=='dist' else app.parent
    needed=sum((source/name).stat().st_size for name in snapshot)
    require_space(root,needed+4096)
    with tempfile.TemporaryDirectory(prefix='.maalimbus-launcher-stage-',dir=app.parent) as staging:
        staged=Path(staging)/'bundle'
        shutil.copytree(source,staged)
        if _snapshot(staged)!=snapshot or _snapshot(source)!=snapshot:
            raise ValueError('Launcher changed during staging')
        try:staged.rename(cached)
        except FileExistsError:
            if _snapshot(cached)!=snapshot:raise ValueError('Concurrent launcher cache differs')
    return cached
