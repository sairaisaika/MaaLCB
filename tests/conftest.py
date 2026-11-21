"""Session-level guards for tests that need the real controller lease to be free.

Twice in one session the full suite went red for the same reason: a live
`MaaLimbusAgent` held `%LOCALAPPDATA%/MaaLimbus/controller.lock`, so the two tests
that prove lease exclusion saw an owner that was not theirs.  A failure that is
caused by the environment and repeats is a missing fixture, not a flaky test: it
skips with the holder's pid named, so the operator can act on it instead of
re-deriving why a red suite is fine.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

LEASE = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'MaaLimbus', 'controller.lock')

NEEDS_FREE_LEASE = (
    'tests/test_controller_lease.py::test_cli_and_agent_cannot_acquire_another_process_controller',
    'tests/test_update_install.py::test_real_controller_lock_blocks_installation',
)


def lease_holder():
    """The owning pid of the real lease, or ``None`` when nothing holds it."""
    if not os.path.exists(LEASE):
        return None
    try:
        raw = open(LEASE, 'r', encoding='utf-8').read().strip()
    except OSError:
        # The lock exists but cannot be read -- that is the *held* case, not the free
        # one.  Treating it as absent is why the guard had no effect while a live
        # agent held the file (measured 2026-10-23).
        return -1
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    # The lock has been written as both a bare pid and a dict over time; accepting
    # only one shape turned a guard into an INTERNALERROR (measured 2026-10-23).
    if isinstance(parsed, int):
        return parsed
    if isinstance(parsed, dict):
        return parsed.get('pid')
    return None


def is_alive(pid):
    if not pid:
        return False
    check = subprocess.run(['tasklist', '/FI', f'PID eq {int(pid)}'],
                           capture_output=True, text=True)
    return str(pid) in (check.stdout or '')


def pytest_collection_modifyitems(config, items):
    pid = lease_holder()
    if not pid:
        return
    # These two tests need the lease to be *absent*, not merely unowned: a lock file
    # left behind by a killed process still blocks them (measured twice on 2026-10-23,
    # the second time with a dead pid 11172).  Report the state so the operator knows
    # whether to kill a process or just delete a file.
    state = 'unknown' if pid == -1 else ('live' if is_alive(pid) else 'stale')
    reason = (f'the real controller lease is present (pid {pid}, {state}); remove it to '
              'exercise lease exclusion')
    for item in items:
        if item.nodeid in NEEDS_FREE_LEASE:
            item.add_marker(pytest.mark.skip(reason=reason))


# ---------------------------------------------------------------------------
# Local prerequisites: what a public checkout never had
# ---------------------------------------------------------------------------
# `evidence/`, `build/`, `dist/` and `config/` are ignored by git, so a fresh clone and
# the CI runner have none of them.  A test that reads one of them says which:
#
#     @pytest.mark.needs_local('evidence/runtime/packaged-mirror-20261118-190145')
#
# and is skipped with that path named when it is absent.  The declaration is per test,
# or `pytestmark` only where every test of the module starts from the same file: a
# module-wide skip hides the tests beside it that need nothing.  A glob is satisfied by
# one match.  This is not for a failure that has another cause -- an undeclared
# dependency or a clock assumption is a defect on a public checkout and gets fixed.
#
# Only those four directories can be declared, plus the game bitmaps below.  A tracked
# file that went missing is a regression, and a marker naming it fails the test instead
# of skipping it.
#
# Game bitmaps are the other thing a public checkout never has: the artwork is not
# redistributable, so no recognition template and no game screenshot is tracked (see
# docs/local-assets.md).  Only a `.png` under these directories can be declared; the
# JSON beside them is tracked and must be there.
import glob as _glob

_CHECKOUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_ONLY = ('evidence/', 'build/', 'dist/', 'config/')
LOCAL_BITMAPS = ('assets/resource/base/image/', 'tests/fixtures/frames/',
                 'tests/fixtures/floor-gift-ocr-drift/')


def not_local_only(paths):
    """Declared paths that git tracks: neither a local directory nor a local game bitmap."""
    def local(path):
        path = path.replace('\\', '/')
        return path.startswith(LOCAL_ONLY) or (path.startswith(LOCAL_BITMAPS) and path.endswith('.png'))
    return [path for path in paths if not local(path) or '..' in path]


def absent_locally(paths, checkout=None):
    """The declared repository-relative paths or globs that match nothing here."""
    root = _CHECKOUT if checkout is None else str(checkout)
    return [path for path in paths
            if not _glob.glob(os.path.join(root, *path.replace('\\', '/').split('/')))]


def pytest_configure(config):
    config.addinivalue_line(
        'markers', 'needs_local(*paths): the test reads these git-ignored local paths '
                   '(repository-relative, globs allowed) and is skipped where one is absent')


@pytest.fixture(autouse=True)
def _local_prerequisites(request):
    declared = [path for mark in request.node.iter_markers('needs_local') for path in mark.args]
    tracked = not_local_only(declared)
    if tracked:
        pytest.fail('needs_local names %s; only %s and the game bitmaps under %s can be absent '
                    'from a checkout' % (', '.join(tracked), ' '.join(LOCAL_ONLY),
                                         ' '.join(LOCAL_BITMAPS)), pytrace=False)
    absent = absent_locally(declared)
    if absent:
        pytest.skip('needs local %s, which git ignores and this checkout does not have'
                    % ', '.join(absent))


# A test that loads a catalog reaches the game bitmaps without naming one: the loader
# opens every icon the catalog lists.  The loaders raise `MissingLocalAssets` for exactly
# that case, so the skip is taken from the error itself and names the bitmap.  Nothing
# else is turned into a skip here: a plain `FileNotFoundError`, which is what a missing
# tracked fixture raises, still fails the test.
def _skip_for_missing_game_bitmap(outcome):
    from maalimbus.local_assets import MissingLocalAssets
    error = outcome.excinfo[1] if outcome.excinfo else None
    if isinstance(error, MissingLocalAssets):
        outcome.force_exception(pytest.skip.Exception(
            'needs local game assets, which are not redistributable and this checkout does '
            'not have: %s' % error, _use_item_location=True))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    _skip_for_missing_game_bitmap((yield))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _skip_for_missing_game_bitmap((yield))


# ---------------------------------------------------------------------------
# Retired evidence: a frame that no fixture keeps is gone for ever
# ---------------------------------------------------------------------------
# The workspace budget (D355, `src/maalimbus/workspace.py`) retires runtime runs the
# fixture drop does not keep.  A test that names one of those runs then fails on
# `FileNotFoundError`, which reads as a regression although the code is unchanged.
# This guard turns exactly that case into a skip with the run's name, so a red suite
# still means a red suite (the same reasoning as the lease guard above).
#
# The decision is taken per test.  It used to be taken per module: one string naming a
# retired run skipped every test beside it, and on 2026-11-20 that was 545 test
# functions in 49 modules, 301 of which never reach a retired frame.  Tests had gone
# stale behind that skip while the suite stayed green.  A test is skipped only when a
# retired run is *reachable* from it: a path in its own body, or in a module-level
# name, fixture or helper it uses, followed through the module and into helpers
# borrowed from a sibling test module.
import re
import pathlib
import ast
from functools import lru_cache

_ROOT = pathlib.Path(__file__).resolve().parents[1]

_RUN = re.compile(r'^evidence/runtime/([\w.-]*\d{8}-[\w.-]+)/')
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_SCOPES = (*_FUNCTIONS, ast.Lambda, ast.ClassDef, *_COMPREHENSIONS)
# What pytest runs for a test without the test naming it.
_IMPLICIT = frozenset(('pytestmark', 'pytest_generate_tests', 'setup_module', 'teardown_module',
                       'setup_function', 'teardown_function', 'setup_class', 'teardown_class',
                       'setup_method', 'teardown_method', 'setup', 'teardown'))


def _inert(tree):
    """Strings no code reads: docstrings and other bare string statements."""
    return {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}


def _strings(nodes, inert):
    for root in nodes:
        for node in ast.walk(root):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in inert):
                yield node.value


def _runs(nodes, inert):
    found = set()
    for value in _strings(nodes, inert):
        match = _RUN.match(value.replace('\\', '/'))
        if match:
            found.add(match.group(1))
    return frozenset(found)


@lru_cache(maxsize=512)
def retained_dependencies(text):
    """Declared dated fixture paths, not comments or temporary test data."""
    tree = ast.parse(text)
    return _runs([tree], _inert(tree))


def _names(nodes):
    return {node.id for root in nodes for node in ast.walk(root) if isinstance(node, ast.Name)}


def _parameters(function):
    spec = function.args
    return {arg.arg for arg in (*spec.posonlyargs, *spec.args, *spec.kwonlyargs,
                                *filter(None, (spec.vararg, spec.kwarg)))}


def _outer(node):
    """The parts of a definition that its enclosing scope evaluates."""
    if isinstance(node, ast.ClassDef):
        return [*node.decorator_list, *node.bases, *(keyword.value for keyword in node.keywords)]
    spec = node.args
    parts = [*spec.defaults, *(default for default in spec.kw_defaults if default is not None)]
    if not isinstance(node, ast.Lambda):
        parts += node.decorator_list
    return parts


def _free(scope):
    """Names a scope reads without binding them: what it takes from its module.

    A local that shadows a module-level name is not a use of it, so a test that builds
    its own `FRAME` under `tmp_path` does not inherit the module's retained `FRAME`.
    """
    bound, loaded, declared, nested = set(), set(), set(), set()
    if isinstance(scope, (*_FUNCTIONS, ast.Lambda)):
        bound |= _parameters(scope)
        stack = [scope.body] if isinstance(scope, ast.Lambda) else list(scope.body)
    elif isinstance(scope, ast.ClassDef):
        stack = list(scope.body)
    else:
        stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        if isinstance(node, _SCOPES):
            if isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
                bound.add(node.name)
            if not isinstance(node, _COMPREHENSIONS):
                stack.extend(_outer(node))
            nested |= _free(node)
            continue
        if isinstance(node, ast.Name):
            (loaded if isinstance(node.ctx, ast.Load) else bound).add(node.id)
        elif isinstance(node, ast.Global):
            declared.update(node.names)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((alias.asname or alias.name).split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            bound.add(node.rest)
        stack.extend(ast.iter_child_nodes(node))
    local = bound - declared
    if isinstance(scope, ast.ClassDef):
        # A class body's own names are invisible to its methods.
        return (loaded - local) | nested | declared
    return ((loaded | nested) - local) | declared


def _is_fixture(function):
    return any(getattr(node, 'id', getattr(node, 'attr', None)) == 'fixture'
               for decorator in function.decorator_list for node in ast.walk(decorator))


def _is_autouse(function):
    return any(isinstance(node, ast.keyword) and node.arg == 'autouse'
               and not (isinstance(node.value, ast.Constant) and not node.value.value)
               for decorator in function.decorator_list for node in ast.walk(decorator))


def _root(node):
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _binds(statement):
    """Module-level names a statement defines or changes in place."""
    bound, stack = set(), [statement]
    while stack:
        node = stack.pop()
        if isinstance(node, _SCOPES):
            if isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
                bound.add(node.name)
            continue
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            bound.add(node.id)
        elif isinstance(node, (ast.Attribute, ast.Subscript)) and not isinstance(node.ctx, ast.Load):
            bound.add(_root(node))
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Attribute)):
            # `FRAMES.append(...)` changes FRAMES for every later reader.
            bound.add(_root(node.value.func))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((alias.asname or alias.name).split('.')[0] for alias in node.names)
        stack.extend(ast.iter_child_nodes(node))
    bound.discard(None)
    return bound


class _Module:
    """What each module-level name of one test module leads to.

    `definitions` maps a name to every statement that defines or changes it, each as
    (runs named there, names read there, names borrowed from a sibling module).
    `always` holds what reaches every test of the module without being named by it.
    """

    def __init__(self, path):
        self.path = path
        tree = ast.parse(pathlib.Path(path).read_text(encoding='utf-8', errors='ignore'))
        self.inert = _inert(tree)
        self.everything = _runs([tree], self.inert)
        self.definitions = {}
        self.always = set()
        self.fixtures = {node.name for node in tree.body
                         if isinstance(node, _FUNCTIONS) and _is_fixture(node)}
        for statement in tree.body:
            if isinstance(statement, _FUNCTIONS):
                self._function(statement.name, statement)
                if statement.name in _IMPLICIT or _is_autouse(statement):
                    self.always.add(statement.name)
            elif isinstance(statement, ast.ClassDef):
                self._class(statement)
            elif isinstance(statement, (ast.Import, ast.ImportFrom)):
                self._import(statement)
            else:
                self._statement(statement)

    def _add(self, name, nodes, reads, borrowed=()):
        self.definitions.setdefault(name, []).append(
            (_runs(nodes, self.inert), frozenset(reads), tuple(borrowed)))

    def _requests(self, function, fixtures):
        """Fixtures a function asks pytest for: by parameter, or by name in a string."""
        asked = {value for value in _strings([function], self.inert) if value in fixtures}
        if function.name.startswith('test') or _is_fixture(function):
            asked |= _parameters(function) & fixtures
        return asked

    def _function(self, key, function, extra=()):
        reads = (_free(function) | _names(_outer(function))
                 | self._requests(function, self.fixtures))
        self._add(key, [function], reads | set(extra))

    def _class(self, statement):
        name = statement.name
        methods = [child for child in statement.body if isinstance(child, _FUNCTIONS)]
        # Bases, decorators and class attributes are read through `self` in ways no name
        # shows, so they belong to every method.
        shared = [*_outer(statement),
                  *(child for child in statement.body if not isinstance(child, _FUNCTIONS))]
        members = {method.name for method in methods}
        fixtures = {method.name for method in methods if _is_fixture(method)}
        implicit = {'%s.%s' % (name, method.name) for method in methods
                    if method.name in _IMPLICIT or _is_autouse(method)}
        self._add(name + '.', shared, _names(shared) | implicit)
        for method in methods:
            used = {node.attr for node in ast.walk(method)
                    if isinstance(node, ast.Attribute) and node.attr in members}
            used |= self._requests(method, fixtures)
            self._function('%s.%s' % (name, method.name), method,
                           {name + '.', *('%s.%s' % (name, member) for member in used)})
        # The class used as a name leads to everything in it.
        self._add(name, [], {name + '.', *('%s.%s' % (name, member) for member in members)})

    def _import(self, statement):
        here = pathlib.Path(self.path).parent
        for alias in statement.names:
            if isinstance(statement, ast.ImportFrom):
                source = None if statement.level else statement.module
                wanted = None if alias.name == '*' else alias.name
            else:
                source, wanted = alias.name, None
            sibling = here / ('%s.py' % source)
            if not source or not sibling.is_file():
                continue
            # A helper borrowed from another test module brings that helper's reach
            # along; `import module` is not resolved name by name and brings it all.
            self._add((alias.asname or alias.name).split('.')[0], [], (),
                      [(str(sibling), wanted)])

    def _statement(self, statement):
        reads = _names([statement]) | {value for value in _strings([statement], self.inert)
                                       if value in self.fixtures}
        names = _binds(statement)
        if not names:
            # Code that only runs at import still runs before every test of the module.
            names = {'<line %d>' % statement.lineno}
            self.always |= names
        self.always |= names & _IMPLICIT
        for name in names:
            self._add(name, [statement], reads)


@lru_cache(maxsize=None)
def _module(path):
    return _Module(path)


@lru_cache(maxsize=None)
def reachable_runs(path, name, cls=None):
    """The retained runs one test can reach.

    `name` is the test function and `cls` its class, as the module spells them.  A test
    the source does not define under that name (generated, or inherited from elsewhere)
    cannot be followed, so it keeps the old answer: every run the module names.
    """
    module = _module(path)
    start = '%s.%s' % (cls, name) if cls else name
    if cls and start not in module.definitions:
        start = cls
    if start not in module.definitions:
        return module.everything
    found, seen, stack = set(), set(), [(path, key) for key in (start, *module.always)]
    while stack:
        where, key = stack.pop()
        if (where, key) in seen:
            continue
        seen.add((where, key))
        graph = _module(where)
        if key is None:
            found |= graph.everything
            continue
        for runs, reads, borrowed in graph.definitions.get(key, ()):
            found |= runs
            stack.extend((where, read) for read in reads)
            stack.extend(borrowed)
    return frozenset(found)


def retired(run):
    return not (_ROOT / 'evidence' / 'runtime' / run).is_dir()


@pytest.fixture(autouse=True)
def _retained_evidence(request):
    path = getattr(getattr(request, 'module', None), '__file__', None)
    if not path:
        yield
        return
    node, cls = request.node, getattr(request, 'cls', None)
    try:
        runs = reachable_runs(str(path), getattr(node, 'originalname', None) or node.name,
                              cls.__name__ if cls else None)
    except (OSError, SyntaxError):
        yield
        return
    for run in sorted(runs):
        if retired(run):
            pytest.skip('the retained run %s was retired by the workspace budget (D355)'
                        % run)
    yield
