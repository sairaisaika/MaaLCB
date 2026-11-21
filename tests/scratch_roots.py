"""A test root short enough for the native socket scratch path, whoever runs the suite.

`native_agent.native_temp` refuses a scratch directory longer than 80 bytes, because the
native socket name has to fit behind it. The tests used to make their root under the
system temp directory, whose length follows the account name: a five-character name left
one byte to spare, and the eleven-character account of GitHub's runner was five over, so
four tests failed there on the path and not on what they test.

The root is taken from the first base that leaves room: the system temp directory, the
directory above this checkout, then the checkout's drive. When none fits, the test skips
and says how long the shortest candidate was.
"""
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

LIMIT = 80
#: `mkdtemp` adds eight characters to a prefix; `native_temp` adds this under the root
RANDOM = 8
SCRATCH = len(os.sep + os.path.join('build', 'native-agent-tmp', 'n-')) + RANDOM


def scratch_length(base, prefix):
    """Bytes of the scratch directory `native_temp` would make under a root in `base`."""
    return len(os.fsencode(str(base))) + len(os.sep) + len(prefix) + RANDOM + SCRATCH


@contextmanager
def short_root(prefix='ma-'):
    repo = Path(__file__).resolve().parents[1]
    bases = [Path(tempfile.gettempdir()), repo.parent, Path(repo.anchor)]
    root = None
    for base in bases:
        if scratch_length(base, prefix) > LIMIT:
            continue
        try:
            root = Path(tempfile.mkdtemp(prefix=prefix, dir=base))
        except OSError:
            continue
        break
    if root is None:
        pytest.skip('no writable base leaves room for the %d-byte native scratch path '
                    '(shortest candidate needs %d)'
                    % (LIMIT, min(scratch_length(base, prefix) for base in bases)))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
