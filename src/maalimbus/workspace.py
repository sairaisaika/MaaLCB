"""工作区维护目标为 3 GB（3,000,000,000 字节）。

占用不是代码写的，是**没人负责删**：`refreeze_agent.py` 每次改名留一份 agent 备份、
launcher 每次启动复制自身、测试安装器每次在 `build/` 建一个 1.4 GiB 的候选目录、
每跑一次就写几百张 1080p 帧。2026-10-31 实测 345 GiB，其中 `dist` 136 / `build` 128 /
`evidence` 81。

这层的职责只有一句话：**在给定的字节预算下，决定哪些可以没有**（D355）。
规则是保守的：源码、资产、`.git`、`dist/MaaLimbus`（跑起来要用的）永远不动。
"""
from __future__ import annotations

import os
import pathlib
import shutil
import json
import hashlib
import threading
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar

BUDGET_BYTES = 3_000_000_000          # Maintenance target and offline allocation limit.
_LIVE_WRITES = ContextVar('maalimbus_live_writes', default=False)
KEEP_BUILD_DIRS = ('mxu-probe-271', 'learning-review', 'native-agent-tmp')
KEEP_RUNS = 5                          # 保留最近几次运行，够定位就行
KEEP_RUN_FRAMES = 3                    # 每次运行只留三张帧
KEEP_AGENT_BACKUPS = 1                 # dist 里 agent 备份只留最新一份

_REFERENCE_CACHE=OrderedDict()
_REFERENCE_CACHE_LOCK=threading.Lock()


def cached_references(path,root,family,parse):
    """Cache lexical references by actual bytes, never by timestamp alone.

    Callers resolve paths after lookup: changed links must not leave cached
    filesystem resolutions in a protection set. Every call rereads the file.
    """
    body=pathlib.Path(path).read_bytes()
    identity=hashlib.sha256(body).digest();key=(str(root),str(path),family)
    with _REFERENCE_CACHE_LOCK:
        previous=_REFERENCE_CACHE.get(key)
        if previous and previous[0]==identity:
            _REFERENCE_CACHE.move_to_end(key)
            return previous[1]
    refs=frozenset(parse(body))
    with _REFERENCE_CACHE_LOCK:
        _REFERENCE_CACHE[key]=(identity,refs)
        _REFERENCE_CACHE.move_to_end(key)
        while len(_REFERENCE_CACHE)>4096:_REFERENCE_CACHE.popitem(last=False)
    return refs


def _linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def resolve_references(paths):
    """Resolve each shared parent once per scan, including current link targets."""
    parents={}
    for path in paths:
        try:
            path=pathlib.Path(path)
            if _linked(path):
                yield path.resolve()
                continue
            if path.parent not in parents:parents[path.parent]=path.parent.resolve()
            yield parents[path.parent]/path.name
        except (OSError,ValueError):continue


def size(path) -> int:
    path = pathlib.Path(path)
    if not path.exists() or _linked(path):
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:]=[name for name in dirs if not _linked(pathlib.Path(root)/name)]
        for name in files:
            try:
                if _linked(pathlib.Path(root)/name):continue
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _remove(path, root) -> int:
    path = pathlib.Path(path)
    root=pathlib.Path(root).resolve()
    if _linked(path):raise ValueError('Refusing linked cleanup target')
    resolved=path.resolve()
    if not resolved.is_relative_to(root) or resolved==root:
        raise ValueError('Cleanup target outside workspace')
    freed = size(path)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        try:
            path.unlink()
        except OSError:
            return 0
    return freed


def protected_evidence(root, *, original_byte_documents=()):
    """Keep evidence referenced by state, models and learning review records.

    This reads paths only; it neither interprets game state nor clears an intent.
    A referenced JSON also protects its PNG companion (and conversely).
    """
    root=pathlib.Path(root).resolve()
    original_byte_documents=frozenset(original_byte_documents)
    runtimes=(root/'evidence/runtime',root/'dist/MaaLimbus/evidence/runtime')
    kept=set();lexical=set()
    def visit(value,found):
        if isinstance(value,dict):
            for item in value.values():visit(item,found)
        elif isinstance(value,list):
            for item in value:visit(item,found)
        elif isinstance(value,str):
            try:
                text=value.replace('\\','/')
                p=pathlib.Path(text)
                if p.suffix.lower() not in ('.json','.png'):return
                paths=[p] if p.is_absolute() else [root/p]
                # Application-relative records occur in installed model/review
                # bundles too. Protect both possible local captures instead of
                # guessing which application's cwd produced the reference.
                if not p.is_absolute() and text.startswith('evidence/runtime/'):
                    paths.append(root/'dist/MaaLimbus'/p)
                found.update(paths)
            except (OSError,ValueError):pass
    def parse(body):
        found=set();visit(json.loads(body.decode('utf8')),found);return found
    for base in (root/'config',root/'dist/MaaLimbus/config',root/'build/learning-review',
                 root/'dist/MaaLimbus/build/learning-review',
                 root/'assets/resource/base/model',root/'dist/MaaLimbus/assets/resource/base/model'):
        if not base.is_dir() or _linked(base):continue
        for path in base.rglob('*.json'):
            try:
                # Lossless-only caller has already verified these untouched
                # proposals and their exact original-byte reader closure.
                # Ordinary deletion/state callers never supply this projection.
                if path in original_byte_documents:continue
                if not path.resolve().is_relative_to(root) or path.stat().st_size>16*1024*1024:continue
                lexical.update(cached_references(path,root,'state',parse))
            except (OSError,ValueError):continue
    for candidate in resolve_references(lexical):
        if any(candidate.is_relative_to(runtime) for runtime in runtimes):
            kept.update((candidate,candidate.with_suffix('.png'),candidate.with_suffix('.json')))
    return kept


def candidates(root=None, *, protected=None) -> list:
    """按“最该先删”的顺序列出可回收的东西（不删，只列）。"""
    root = pathlib.Path(root or '.').resolve()
    protected=protected_evidence(root) if protected is None else protected
    def pinned(path):return any(p==path or p.is_relative_to(path) for p in protected)
    found = []
    build = root / 'build'
    if build.is_dir():
        for child in build.iterdir():
            if child.is_dir() and not _linked(child) and child.name not in KEEP_BUILD_DIRS:
                found.append(child)
    dist = root / 'dist'
    if dist.is_dir():
        backups = sorted(p for p in dist.glob('MaaLimbus.backup-*'))
        found.extend(backups[:-KEEP_AGENT_BACKUPS] if len(backups) > KEEP_AGENT_BACKUPS else [])
        found.extend(sorted(dist.glob('*.staging-*')))
        for name in ('evidence', 'debug'):
            if (dist / 'MaaLimbus' / name).is_dir():
                found.append(dist / 'MaaLimbus' / name)
        agents = sorted((dist / 'MaaLimbus').glob('agent.backup-*'))
        found.extend(agents[:-KEEP_AGENT_BACKUPS] if len(agents) > KEEP_AGENT_BACKUPS else [])
    runtime = root / 'evidence' / 'runtime'
    if runtime.is_dir():
        runs = sorted(p for p in runtime.iterdir() if p.is_dir())
        found.extend(runs[:-KEEP_RUNS] if len(runs) > KEEP_RUNS else [])
    return [path for path in found if not _linked(path) and not pinned(path)]


def trim_runs(root=None, *, keep=KEEP_RUNS, frames=KEEP_RUN_FRAMES, protected=None, max_free=None) -> int:
    """保留最近 keep 次运行，每次只留 frames 张帧；返回回收字节。"""
    root=pathlib.Path(root or '.').resolve()
    protected=protected_evidence(root) if protected is None else protected
    runtime = root / 'evidence' / 'runtime'
    if not runtime.is_dir():
        return 0
    freed = 0
    runs = sorted(p for p in runtime.iterdir() if p.is_dir() and not _linked(p))
    for run in runs[-keep:]:
        shots = sorted(run.glob('frame-*.png'))
        for shot in shots[:-frames] if frames else shots:
            if max_free is not None and freed>=max_free:return freed
            if shot.resolve() not in protected:freed += _remove(shot,root)
    return freed


def prune(root=None, *, budget=BUDGET_BYTES) -> dict:
    """在预算内尽量保留；返回 {before, after, freed, removed}。"""
    root = pathlib.Path(root or '.').resolve()
    before = size(root)
    protected=protected_evidence(root)
    freed = 0
    removed = []
    if before > budget:
        # Rebuildable artifacts first. Never discard frames merely because a
        # run completed while the workspace was already inside its budget.
        for path in candidates(root,protected=protected):
            if before - freed <= budget:
                break
            freed += _remove(path,root)
            removed.append(str(path))
        if before-freed>budget:
            freed+=trim_runs(root,protected=protected,max_free=before-freed-budget)
    after = size(root)
    return {'before': before, 'after': after, 'freed': freed, 'removed': removed,
            'budget':budget,'within_budget':after<=budget}


def require_space(root, additional_bytes, *, budget=BUDGET_BYTES):
    """Refuse an allocation before it crosses the folder limit; never delete data."""
    if type(additional_bytes) is not int or additional_bytes<0:
        raise ValueError('Additional size must be a nonnegative byte count')
    used=size(root)
    if used+additional_bytes>budget:
        raise ValueError('Workspace budget exceeded: %d + %d > %d bytes' % (used,additional_bytes,budget))
    return dict(used_bytes=used,reserved_bytes=additional_bytes,budget_bytes=budget)


@contextmanager
def live_writes():
    """A native task must be able to save its current evidence and receipts."""
    token = _LIVE_WRITES.set(True)
    try:
        yield
    finally:
        _LIVE_WRITES.reset(token)


def require_disk_space(root, additional_bytes):
    if type(additional_bytes) is not int or additional_bytes < 0:
        raise ValueError('Additional size must be a nonnegative byte count')
    free = shutil.disk_usage(root).free
    if free < additional_bytes:
        raise ValueError(f'Runtime evidence volume has {free} bytes free, needs {additional_bytes}')


def reserve_output(destination, additional_bytes, *, application_root=None):
    """Account for installed-app output against the containing project cap."""
    if application_root is None:
        from .runtime_paths import ROOT
        application_root=ROOT
    base=pathlib.Path(application_root).resolve()
    root=base.parent.parent if base.parent.name=='dist' else base
    if pathlib.Path(destination).resolve().is_relative_to(root):
        if _LIVE_WRITES.get():
            return require_disk_space(root, additional_bytes)
        return require_space(root,additional_bytes,budget=BUDGET_BYTES)
    return None


def main(argv=None) -> int:
    """命令行：预演/执行。`--apply` 才真删。"""
    import argparse

    parser = argparse.ArgumentParser(description='把工作区收回到预算内（默认预演）')
    parser.add_argument('--apply', action='store_true', help='真的删（不给就是预演）')
    parser.add_argument('--budget-gib', type=float, default=BUDGET_BYTES / 2**30)
    args = parser.parse_args(argv)
    budget = int(args.budget_gib * 2**30)
    if budget<=0 or budget>BUDGET_BYTES:
        parser.error('Budget must be positive and cannot exceed 3,000,000,000 bytes')
    if args.apply:
        out = prune(budget=budget)
        print('清理前 %.2f GiB → 清理后 %.2f GiB（回收 %.2f GiB，删除 %d 项）'
              % (out['before'] / 2**30, out['after'] / 2**30,
                 out['freed'] / 2**30, len(out['removed'])))
        return 0 if out['within_budget'] else 1
    before = size('.')
    would = sum(size(path) for path in candidates())
    runtime = pathlib.Path('evidence') / 'runtime'
    if runtime.is_dir():
        for run in sorted(p for p in runtime.iterdir() if p.is_dir())[-KEEP_RUNS:]:
            would += sum(size(p) for p in sorted(run.glob('frame-*.png'))[KEEP_RUN_FRAMES:])
    print('当前 %.2f GiB，预算 %.1f GiB，预演可回收 %.2f GiB（加 --apply 才删）'
          % (before / 2**30, args.budget_gib, would / 2**30))
    return 0
