"""Shared runtime vocabulary, adopted incrementally by production owners.

The verdict is not a task result, receipt, training label, or input grant.
Domain judges retain their own successor criteria. See Wiki1.2 and3.10.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Literal


@dataclass(frozen=True)
class FrameRef:
    """Identity of original capture bytes, not freshness or input authority.

    ``captured_at`` belongs to the canonical capture, not a later read event
    reusing identical pixels. Historical missing time stays explicitly unknown.
    Construction validates structure; native_evidence.frame_reference verifies
    the actual JSON/PNG bytes before returning this record to production.
    """

    frame_id: str
    record_path: str
    captured_at: str | None
    json_sha256: str
    png_sha256: str
    size: tuple[int, int]

    def __post_init__(self):
        if not isinstance(self.frame_id,str) or not re.fullmatch(r'frame-\d+',self.frame_id):
            raise ValueError('FrameRef requires a canonical frame id')
        if not isinstance(self.record_path,str) or not self.record_path.strip():
            raise ValueError('FrameRef requires its original record location')
        if not isinstance(self.size,tuple) or len(self.size)!=2 or any(
                type(n) is not int or n<=0 for n in self.size):
            raise ValueError('FrameRef dimensions must be an immutable positive pair')
        for value in (self.json_sha256,self.png_sha256):
            if not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{64}',value):
                raise ValueError('FrameRef requires exact JSON and PNG hashes')
        if self.captured_at is not None:
            if not isinstance(self.captured_at,str):
                raise ValueError('FrameRef capture time must be timezone-aware or unknown')
            stamp=datetime.fromisoformat(self.captured_at)
            if stamp.tzinfo is None:
                raise ValueError('FrameRef capture time must be timezone-aware or unknown')

    def as_dict(self):
        return dict(frame_id=self.frame_id,record_path=self.record_path,
                    captured_at=self.captured_at,json_sha256=self.json_sha256,
                    png_sha256=self.png_sha256,size=list(self.size))


@dataclass(frozen=True)
class TransitionVerdict:
    """An immutable result of judging one action's observed successor.

    ``expected`` is the original action's named successor contract, not a
    dynamically broadened list. Allowed waiting remains a domain judgement;
    the presence of a page in this tuple alone does not authorize acceptance.
    """

    outcome: Literal['accepted', 'rejected', 'unjudged']
    after: str | None
    expected: tuple[str, ...]
    reason: str

    def __post_init__(self):
        if self.outcome not in ('accepted', 'rejected', 'unjudged'):
            raise ValueError('Unknown transition verdict; use accepted/rejected/unjudged')
        if not isinstance(self.expected, tuple) or not all(
                isinstance(page, str) and page for page in self.expected):
            raise ValueError('Expected successors must be an immutable tuple of page names')
        if self.after is not None and not isinstance(self.after, str):
            raise ValueError('Observed successor must be a page name or None')
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError('Transition verdict requires its judgement reason')
        if self.outcome == 'accepted' and (not self.after or self.after not in self.expected):
            raise ValueError('Accepted successor must satisfy the original named contract')
