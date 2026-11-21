"""Pre-dispatch screenshot credit for the native evidence writer.

One existing controller owner uses this pool; it is not another controller lease
or a business transaction. Credit is a sized placeholder, so ordinary workspace
writers also see the reserved bytes. Two fixed-size, checksummed metadata slots
allow an interrupted resize to reconcile without guessing whether input landed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct

from . import capture_retention, workspace

SLOT_BYTES = 8192
STOP_BYTES = 2_000_000
METADATA_BYTES = 1_000_000
JOURNAL_HEADROOM = 2_000_000
FORMAT_VERSION = 1
CAPTURE_PROFILE = 'bgr8-json1mb-v1'
CAPTURE_CHANNELS = 3
MAX_CREDIT_BYTES = 256 * 1024 * 1024


def refresh_required(owner):
    """One storage-phase predicate for admission and the native cache producer."""
    return bool(owner.get('fresh_capture_required') or owner.get('purpose')=='refresh')


def validate_capture_image(frame):
    """The native producer and its future-byte reservation share one format."""
    if (getattr(frame,'dtype',None) is None or frame.dtype.kind!='u' or frame.dtype.itemsize!=1
            or len(frame.shape)!=3 or frame.shape[2]!=CAPTURE_CHANNELS
            or frame.shape[0]<1 or frame.shape[1]<1):
        raise ValueError('Native capture requires nonempty uint8 BGR three-channel image')


def validate_capture_metadata(body):
    if len(body)>METADATA_BYTES:
        raise ValueError('Complete native capture metadata exceeds bounded producer profile')


class EvidenceCapacityUnavailable(RuntimeError):
    reason = 'evidence_capacity_unavailable_before_input'


class FreshPlanningRequired(EvidenceCapacityUnavailable):
    """Maintenance succeeded and the proposed physical input was not sent."""


def _hash(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


class EvidenceCapacity:
    def __init__(self, application_root, *, live=False):
        self.root, _ = capture_retention.roots(application_root)
        self.live = live
        self.directory = self.root / 'evidence/runtime'
        self.credit = self.directory / '.capture-capacity.bin'
        self.slots = tuple(self.directory / ('.capture-capacity-%d.json' % i) for i in range(2))

    @property
    def exists(self):
        return any(path.exists() for path in (self.credit, *self.slots))

    def reserve_space(self, directory, amount, **options):
        if not self.live:
            return capture_retention.reserve(directory, amount, application_root=self.root, **options)
        return workspace.require_disk_space(self.root, amount)

    def _check_space(self, amount):
        if self.live:
            workspace.require_disk_space(self.root, amount)
        else:
            workspace.require_space(self.root, amount, budget=workspace.BUDGET_BYTES)

    def _safe(self):
        for path in (self.credit, *self.slots):
            capture_retention._plain(path, self.root)

    def _store(self, record):
        payload = _encoded(record)
        body = _encoded(dict(record=record, sha256=hashlib.sha256(payload).hexdigest()))
        if len(body) > SLOT_BYTES:
            raise ValueError('Evidence capacity metadata exceeds its fixed slot')
        target = self.slots[record['sequence'] % 2]
        with target.open('r+b') as handle:
            handle.seek(0)
            handle.write(body.ljust(SLOT_BYTES, b' '))
            handle.flush()
            os.fsync(handle.fileno())

    def _initialize(self):
        self._safe()
        if self.exists:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        for path in self.slots:
            with path.open('xb') as handle:
                handle.write(b' ' * SLOT_BYTES)
                handle.flush()
                os.fsync(handle.fileno())
        with self.credit.open('xb') as handle:
            handle.flush()
            os.fsync(handle.fileno())
        self._store(dict(version=FORMAT_VERSION, sequence=1, state='ready', bytes=0, owner=None))

    def load(self):
        self._safe()
        if not self.exists:
            return dict(version=FORMAT_VERSION, sequence=0, state='ready', bytes=0, owner=None)
        if not all(path.is_file() for path in (self.credit, *self.slots)):
            raise ValueError('Incomplete evidence capacity pool; preserve original files')
        valid = []
        for path in self.slots:
            try:
                if path.stat().st_size != SLOT_BYTES:
                    continue
                envelope = json.loads(path.read_bytes())
                record = envelope['record']
                if (record['version'] != FORMAT_VERSION or type(record['sequence']) is not int
                        or record['sequence'] < 1
                        or record['state'] not in ('ready', 'resizing')
                        or type(record['bytes']) is not int or record['bytes'] < 0
                        or record['bytes'] > MAX_CREDIT_BYTES
                        or envelope['sha256'] != hashlib.sha256(_encoded(record)).hexdigest()):
                    continue
                valid.append(record)
            except (OSError, ValueError, TypeError, KeyError):
                continue
        if not valid:
            raise ValueError('Evidence capacity metadata is unverified; preserve original files')
        record = max(valid, key=lambda item: item['sequence'])
        actual = self.credit.stat().st_size
        if record['state'] == 'resizing':
            before = record.get('before')
            if type(before) is not int or before < 0 or actual not in (before, record['bytes']):
                raise ValueError('Evidence capacity resize is ambiguous; preserve original files')
            record = dict(record, sequence=record['sequence'] + 1, state='ready', bytes=actual)
            record.pop('before', None)
            self._store(record)
        elif actual != record['bytes']:
            raise ValueError('Evidence capacity size changed; preserve original files')
        return record

    def _resize(self, amount, *, owner=None, consumer=None):
        if not 0 <= amount <= MAX_CREDIT_BYTES:
            raise ValueError('Evidence credit is larger than its supported range')
        previous = self.load()
        record = dict(previous, sequence=previous['sequence'] + 1, state='resizing',
                      before=previous['bytes'], bytes=amount)
        if owner is not None:
            record['owner'] = owner
        if consumer is not None:
            record['consumer'] = consumer
        self._store(record)
        with self.credit.open('r+b') as handle:
            handle.truncate(amount)
            handle.flush()
            os.fsync(handle.fileno())
        record.update(sequence=record['sequence'] + 1, state='ready')
        record.pop('before')
        self._store(record)
        return record

    def admit(self, frame_path, *, kind, payload, scope=None,successor_size=None):
        """Stage a read-only refresh, then independently fund both input successors."""
        frame_path = capture_retention._plain(Path(frame_path), self.root)
        picture = frame_path.with_suffix('.png')
        capture_retention._plain(picture, self.root)
        record = json.loads(frame_path.read_text(encoding='utf-8'))
        if record.get('image_sha256') != _hash(picture):
            raise ValueError('Before-input capture hash changed; no capacity admission')
        with picture.open('rb') as handle:
            header = handle.read(29)
        if header[:8] != b'\x89PNG\r\n\x1a\n' or header[12:16] != b'IHDR':
            raise ValueError('Before-input capture is not a verified native PNG')
        width, height = struct.unpack('>II', header[16:24])
        if width < 1 or height < 1 or record.get('size') != [width, height]:
            raise ValueError('Before-input capture dimensions disagree')
        if len(header)!=29 or header[24:26]!=bytes((8,2)):
            raise ValueError('Before-input PNG differs from native BGR8 capture profile')
        validate_capture_metadata(frame_path.read_bytes())
        if successor_size is not None:
            if (not isinstance(successor_size,(tuple,list)) or len(successor_size)!=2
                    or any(type(v) is not int or v<=0 for v in successor_size)):
                raise ValueError('Invalid declared successor capture size')
            width,height=max(width,successor_size[0]),max(height,successor_size[1])
        # RGB scanlines + filter bytes, conservative zlib/chunk overhead and the
        # complete JSON limit enforced by Journal.frame, not a percentile guess.
        pair_bound = ((width * CAPTURE_CHANNELS + 1) * height * 101 // 100
                      + 65_536 + METADATA_BYTES)
        target = 2 * pair_bound + STOP_BYTES
        previous = self.load()
        previous_owner = previous.get('owner') or {}
        if not isinstance(previous_owner,dict) or previous_owner.get('purpose','input') not in ('input','refresh'):
            raise ValueError('Evidence capacity owner purpose is unverified')
        if previous_owner.get('purpose')=='refresh' and previous_owner.get('successor_pairs')!=0:
            raise ValueError('Refresh credit cannot declare funded input successors')
        if refresh_required(previous_owner) and (
                str(frame_path.relative_to(self.root)) == previous_owner.get('frame')
                or _hash(frame_path) == previous_owner.get('json_sha256')):
            raise ValueError('Fresh capture required after storage maintenance; stale proof retained')
        refresh_completed=refresh_required(previous_owner)
        growth = max(0, target - previous['bytes'])
        released = 0
        maintenance = False
        reservation = None
        reobserve_pairs = 0
        funded_refresh = 0
        relative = str(frame_path.parent.relative_to(self.root))
        owns_pool = relative in ((previous.get('owner') or {}).get('directory'),previous.get('consumer'))
        pressured = (not self.live and (growth or not self.exists) and workspace.size(self.root)+growth
                     +JOURNAL_HEADROOM+(0 if self.exists else 2*SLOT_BYTES)>workspace.BUDGET_BYTES)
        refresh_only = str(kind)=='plan' and pressured and not refresh_completed
        if pressured and previous['bytes'] and owns_pool:
            # No new input has been dispatched. The one synchronous Journal
            # writer may return its unspent placeholders so protected retention
            # can stage a rewrite. Fund the current storage phase below; the
            # physical door must separately readmit both input successors.
            released=previous['bytes']
            previous=self._resize(0)
            growth=target
        if refresh_only:
            # No physical action can use this phase. Reserve one bounded fresh
            # read now; only its independently recorded actual pair can support
            # the later, full two-successor input admission.
            target=pair_bound+STOP_BYTES
            reobserve_pairs=1
            growth=max(0,target-previous['bytes'])
        if growth or not self.exists:
            request=growth+JOURNAL_HEADROOM+(0 if self.exists else 2*SLOT_BYTES)
            preferred=({'prefer_extra':pair_bound}
                       if str(kind)=='plan' and refresh_completed and owns_pool and pressured else {})
            reservation=self.reserve_space(frame_path.parent, request, **preferred)
            maintenance=bool(isinstance(reservation,dict) and reservation.get('storage_maintenance'))
            if maintenance and str(kind)=='plan':
                # Maintenance after an earlier refresh has already funded the
                # full input target. Keep that physical headroom through the new
                # read instead of releasing it and forcing the same reclaim again.
                if refresh_completed and owns_pool:
                    funded_refresh=target+max(0,reservation.get('additional_bytes',request)-request)
                refresh_only=True
                target=pair_bound+STOP_BYTES
                reobserve_pairs=1
        else:
            # The main plan already admitted its diagnostic margin. Domain intent
            # writes may use part of it before the device's second check; do not
            # charge that same headroom again while successor credit is intact.
            self._check_space(0)
        self._initialize()
        owner = dict(directory=str(frame_path.parent.relative_to(self.root)),
                     frame=str(frame_path.relative_to(self.root)),
                     json_sha256=_hash(frame_path), image_sha256=record['image_sha256'],
                     kind=str(kind), payload=list(payload), scope=scope,
                     purpose='refresh' if refresh_only else 'input',
                     successor_pairs=0 if refresh_only else 2,
                     pair_bound=pair_bound,capture_profile=CAPTURE_PROFILE)
        owner['successor_size']=[width,height]
        if maintenance or released or refresh_only:
            owner['fresh_capture_required'] = True
        if reobserve_pairs:
            owner['reobserve_pairs'] = reobserve_pairs
        allocated=target if refresh_only and owns_pool else max(target,previous['bytes'])
        admitted = self._resize(max(allocated,funded_refresh), owner=owner)
        result = dict(reserved_bytes=admitted['bytes'], capacity_sequence=admitted['sequence'],
                    before_frame=owner['frame'], before_image_sha256=owner['image_sha256'],
                    before_json_sha256=owner['json_sha256'],
                    purpose=owner['purpose'],successor_pairs=owner['successor_pairs'], input_sent=False)
        if released:result['storage_credit_handoff_bytes']=released
        if reobserve_pairs:
            result.update(reobserve_pairs=reobserve_pairs,reobserve_pair_bound=pair_bound)
        if maintenance or released or refresh_only:result['storage_maintenance']=True
        for key in ('vault_containers','vault_project_bytes_freed','vault_unavailable'):
            if isinstance(reservation,dict) and key in reservation:
                result[key]=reservation[key]
        return result

    def consume_capture(self, directory, amount):
        """Replace existing placeholder bytes with this exact JSON/PNG pair."""
        if not Path(directory).resolve().is_relative_to(self.root) or not self.exists:
            return False
        if type(amount) is not int or amount < 0:
            raise ValueError('Capture size must be a nonnegative byte count')
        current = self.load()
        target = max(current['bytes'], amount + STOP_BYTES)
        if target > current['bytes']:
            self.reserve_space(directory, target - current['bytes'] + JOURNAL_HEADROOM)
            current = self._resize(target)
        self._resize(current['bytes'] - amount,
                     consumer=str(Path(directory).resolve().relative_to(self.root)))
        try:
            self._check_space(amount)
        except ValueError:
            # Native host logs/diagnostics may grow between admission and the
            # next read. Consume the existing credit first, then run the same
            # protected retention policy before allocating this exact pair.
            self.reserve_space(directory, amount + JOURNAL_HEADROOM)
            self._check_space(amount)
        return True

    def release_for_result(self, directory):
        """Release only this capture session's pool at its terminal result writer.

        This is storage accounting. It neither resolves a game pending action nor
        records whether a physical input was sent, successful, or repeatable.
        """
        if not Path(directory).resolve().is_relative_to(self.root) or not self.exists:
            return False
        current = self.load()
        relative = str(Path(directory).resolve().relative_to(self.root))
        if relative not in ((current.get('owner') or {}).get('directory'), current.get('consumer')):
            return False
        self._resize(0)
        return True
