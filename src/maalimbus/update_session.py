"""One bounded external update session, with a verified copy before replacement.

Cross-volume copies are not atomic swaps. A durable replacement intent and exact
backup hashes allow the next launcher to restore an interrupted installation.
The caller must serialize this session with its existing launcher lease.
"""
import hashlib
import json
from pathlib import Path
import shutil

from .archives import safe_name
from .controller_lease import ControllerLease
from .storage import write_json, read_json
from .update_install import (PRIVATE, closed_app, metadata, plain_path, plain_tree,
                             private_hashes, self_test, validate_install)
from .update_stage import StageError, file_digest, stage_release
from .workspace import BUDGET_BYTES, require_space, size

SESSION_BYTES = 1_000_000_000
HEADROOM = 1_048_576
TERMINAL = {'installed', 'rolled_back', 'staging_failed', 'aborted_before_replace'}


def snapshot(root):
    plain_tree(root)
    return {p.relative_to(root).as_posix(): file_digest(p)
            for p in root.rglob('*') if p.is_file()}


class UpdateSession:
    def __init__(self, app, work, *, temporary_root=None, project_root=None,
                 project_budget=BUDGET_BYTES, session_budget=SESSION_BYTES,
                 process_check=closed_app, validator=self_test,
                 lease_factory=ControllerLease):
        self.app, self.work = map(plain_path, (app, work))
        if (self.app == Path(self.app.anchor) or self.app == Path.home() or
                (self.app/'.git').exists() or self.work == self.app or
                self.work.is_relative_to(self.app)):
            raise StageError('Unsafe installation or transaction work location')
        self.project = plain_path(project_root or
            (self.app.parent.parent if self.app.parent.name == 'dist' else self.app))
        if not self.app.is_relative_to(self.project):
            raise StageError('Installation outside project budget root')
        if (type(project_budget) is not int or not 0 < project_budget <= BUDGET_BYTES or
                type(session_budget) is not int or not 0 < session_budget <= SESSION_BYTES):
            raise StageError('Update budgets cannot exceed their hard limits')
        self.project_budget, self.session_budget = project_budget, session_budget
        key = hashlib.sha256(str(self.app).casefold().encode('utf8')).hexdigest()[:24]
        # A frozen executable can reject the OS TEMP locations and silently
        # select its cwd. That can put updates inside the immutable helper or
        # make a later launcher look in a different place for pending rollback.
        # Use a stable, capacity-bounded sibling of the project instead.
        self.root = plain_path(Path(temporary_root or self.project.parent) /
                               ('MaaLimbus-update-'+key))
        if self.root.is_relative_to(self.project) or self.project.is_relative_to(self.root):
            raise StageError('Update session must be outside the project')
        self.report, self.backup = self.root/'transaction.json', self.root/'backup'
        self.process_check, self.validator = process_check, validator
        self.lease_factory = lease_factory
        self.result = None

    def _owned(self):
        plain_tree(self.root)
        if not self.report.is_file():
            raise StageError('Unowned update directory; nothing removed')
        data = read_json(self.report, limit=16*1024*1024)
        if (not isinstance(data, dict) or data.get('schema') != 1 or
                data.get('install') != str(self.app) or
                data.get('status') not in TERMINAL | {'staging', 'preparing',
                    'backup_verified', 'replacement_pending', 'rollback_failed'}):
            raise StageError('Invalid update session ownership or state')
        return data

    def _reserve(self, additional):
        proof = require_space(self.root, additional+HEADROOM, budget=self.session_budget)
        if self.result is not None:
            self.result['session_reserved_peak'] = max(
                self.result.get('session_reserved_peak', 0),
                proof['used_bytes']+proof['reserved_bytes'])
        return proof

    def _save(self):
        # JSON's atomic writer also has a temporary sibling; reserve both copies.
        count = len(json.dumps(self.result, ensure_ascii=False, indent=2).encode('utf8'))
        self._reserve(2*count)
        write_json(self.report, self.result)

    def _proof(self):
        # The full rollback manifest stays in the bounded external journal. Do
        # not duplicate it into the app's startup report or launcher stdout.
        return {key:value for key,value in self.result.items() if key != 'before'}

    def _remove(self, path):
        path = plain_path(path)
        if path == self.root or not path.is_relative_to(self.root):
            raise StageError('Cleanup outside this update session')
        plain_tree(path)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    def _clear_terminal(self):
        if self.root.exists():
            old = self._owned()
            if old['status'] not in TERMINAL | {'staging'}:
                raise StageError('Unresolved update requires recovery before another download')
            # No accumulated archives, candidates or backups from earlier updates.
            for path in list(self.root.iterdir()):
                if path != self.report:
                    self._remove(path)

    def stage(self, release, unused_root, **kwargs):
        require_space(self.project, HEADROOM, budget=self.project_budget)
        self._clear_terminal()
        self.result = dict(schema=1, status='staging', install=str(self.app),
                           installed=False, rolled_back=False, game_input_sent=False,
                           ui_verified=False, project_budget=self.project_budget,
                           session_budget=self.session_budget)
        self._save()
        try:
            staged = stage_release(release, self.root/'stages', reserve=self._reserve,
                                   discard_archive=True, **kwargs)
            if staged['status'] != 'staged':
                self.result.update(status='staging_failed')
                self._save()
                self._remove(self.root/'stages')
            return staged
        except Exception:
            self.result.update(status='staging_failed')
            self._save()
            self._remove(self.root/'stages')
            raise

    def _verify_backup(self):
        before = self.result.get('before')
        if (not isinstance(before, dict) or not before or
                any(not isinstance(k, str) or safe_name(k) != k or
                    not isinstance(v, str) or len(v) != 64 or
                    any(c not in '0123456789abcdef' for c in v)
                    for k, v in before.items()) or not self.backup.is_dir() or
                snapshot(self.backup) != before):
            raise StageError('Exact rollback backup not proven; retained without deletion')

    def _restore(self):
        self._verify_backup()  # Never remove a failed/current app before this passes.
        self.process_check(self.app)
        growth = max(0, size(self.backup)-size(self.app))
        require_space(self.project, growth+HEADROOM, budget=self.project_budget)
        plain_tree(self.app)
        if self.app.exists():
            shutil.rmtree(self.app)
        shutil.copytree(self.backup, self.app)
        if snapshot(self.app) != self.result['before']:
            raise StageError('Restored application hash mismatch')
        self.result.update(status='rolled_back', installed=False, rolled_back=True)
        self._save()
        self._remove(self.root/'stages')

    def recover(self):
        """Call before reading app metadata: interruption may have removed the app."""
        if not self.root.exists():
            return None
        self.result = self._owned()
        status = self.result['status']
        if status in ('replacement_pending', 'rollback_failed'):
            lease = self.lease_factory(self.work/'controller.lock')
            try:
                self._restore()
            except Exception:
                self.result.update(status='rollback_failed', reason='manual_backup_restore_required')
                self._save()
                raise StageError('Update recovery requires retained backup inspection') from None
            finally:
                lease.close()
        elif status in ('preparing', 'backup_verified'):
            # These phases precede the durable permission to remove the old app.
            if not self.app.is_dir() or snapshot(self.app) != self.result.get('before'):
                raise StageError('Application changed before replacement intent')
            self.result.update(status='aborted_before_replace')
            self._save()
        return self._proof()

    def install(self, stage, target):
        if plain_path(target) != self.app:
            raise StageError('Update target differs from session owner')
        stage = plain_path(stage)
        if not stage.is_relative_to(self.root/'stages'):
            raise StageError('Stage outside this update session')
        self.result = self._owned()
        if self.result['status'] != 'staging':
            raise StageError('Session is not ready to install')
        _, _, lock, package, record = validate_install(stage, self.app, self.work/'controller.lock')
        self.process_check(self.app)
        lease = self.lease_factory(lock)
        before = None
        try:
            self.process_check(self.app)
            before_private = private_hashes(self.app)
            before = snapshot(self.app)
            growth = max(0, size(package)+sum(size(self.app/n) for n in PRIVATE)-size(self.app))
            require_space(self.project, growth+HEADROOM, budget=self.project_budget)
            self._reserve(size(self.app))
            self.result.update(status='preparing', version=record['version'], before=before,
                               backup=str(self.backup), project_growth_reserved=growth)
            self._save()
            self._reserve(size(self.app))
            shutil.copytree(self.app, self.backup)
            self._verify_backup()
            self.result['status'] = 'backup_verified'
            self._save()
            self.process_check(self.app)
            if snapshot(self.app) != before:
                raise StageError('Application changed during backup')
            require_space(self.project, growth+HEADROOM, budget=self.project_budget)
            self.result['status'] = 'replacement_pending'
            self._save()  # Fsync intent before removing any installed file.
            shutil.rmtree(self.app)
            shutil.copytree(package, self.app)
            for name in PRIVATE:
                if (self.backup/name).exists():
                    shutil.copytree(self.backup/name, self.app/name)
            metadata(self.app, record['version'])
            manifest = read_json(package/'package-manifest.json', limit=4*1024*1024)
            if any(file_digest(self.app/name) != digest.lower() for name, digest in manifest.items()):
                raise StageError('Installed public file mismatch')
            proof = self.validator(self.app)
            if not isinstance(proof, dict) or proof.get('agent_self_test') is not True:
                raise StageError('Installed verification missing')
            if private_hashes(self.app) != before_private:
                raise StageError('Private configuration changed during verification')
            self.result.update(status='installed', installed=True, verification=proof,
                               private_files=len(before_private),
                               pending=['MXU UI restart/version verification'])
            self._save()
            self._remove(self.root/'stages')
        except Exception:
            if self.result['status'] == 'replacement_pending':
                try:
                    self._restore()
                except Exception:
                    self.result.update(status='rollback_failed', installed=False,
                                       reason='manual_backup_restore_required')
                    self._save()
            elif self.result['status'] != 'installed':
                preserved = before is not None and self.app.is_dir() and snapshot(self.app) == before
                self.result.update(status='aborted_before_replace', reason='installation_not_started',
                                   local_app_preserved=preserved, replacement_started=False)
                self._save()
            else:
                raise  # Committed install but cleanup/report failure is not a rollback.
        finally:
            lease.close()
        return self._proof()
