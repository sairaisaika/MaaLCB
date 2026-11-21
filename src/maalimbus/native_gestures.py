"""Pure Maa 5.12.2 pipeline gestures in screenshot coordinates.

Keep routing in MaaDevice and successor judgement in the domain owner. A native
MultiSwipe owns the two contact lifetimes; Python never retries a partial pinch.
"""
import math


def frame_coordinates(values,size):
    """Compatibility entry; capture_geometry owns the shared coordinate contract."""
    from .capture_geometry import frame_coordinates as convert
    return convert(values,size)


def map_pinch(size):
    return frame_coordinates((960,540),size),round(320*min(size[0]/1920,size[1]/1080))


def pinch_node(centre, radius, factor, seconds, *, post_delay=150):
    values = (*centre, radius, factor, seconds)
    if len(centre) != 2 or not all(math.isfinite(float(v)) for v in values):
        raise ValueError('Pinch requires finite two-dimensional geometry')
    if radius <= 0 or not 0 < factor < 1 or not 0 < seconds <= 3:
        raise ValueError('Pinch exceeds bounded zoom-out geometry')
    cx, cy = map(int, centre)
    reach = max(1, int(radius)); target = max(1, int(reach * factor))
    swipes = [dict(begin=[cx + sign * reach, cy, 1, 1],
                   end=[cx + sign * target, cy, 1, 1],
                   duration=max(1, round(seconds * 1000)), starting=0, contact=contact)
              for contact, sign in enumerate((-1, 1))]
    if any(v < 0 for swipe in swipes for key in ('begin', 'end') for v in swipe[key][:2]):
        raise ValueError('Pinch endpoints must remain inside the captured viewport')
    return dict(recognition='DirectHit', action='MultiSwipe', swipes=swipes,
                next=[], pre_delay=0, post_delay=int(post_delay))
