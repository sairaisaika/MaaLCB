"""Identify the actual public source inputs, including uncommitted changes."""
import hashlib
from pathlib import Path
import subprocess


def source_snapshot(root):
    root=Path(root).resolve()
    files=subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard',
                          '--','src','agent','assets'],cwd=root,capture_output=True,check=True).stdout
    snapshot={}
    for name in sorted(set(files.decode('utf8').split('\0'))):
        if not name:continue
        path=root/name
        if not path.is_file():continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Linked source input outside build contract')
        with path.open('rb') as handle:snapshot[name]=hashlib.file_digest(handle,'sha256').hexdigest()
    return snapshot
