"""Stable project entrypoint; independent of any installed Wiki skill version."""
import runpy
from pathlib import Path

if __name__=='__main__':
    runpy.run_path(str(Path(__file__).with_name('wiki_router.py')),run_name='__main__')
