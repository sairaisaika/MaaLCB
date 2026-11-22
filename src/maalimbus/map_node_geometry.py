"""Independent map sprite/segment measurements; no controller or game state writes."""
from __future__ import annotations

import math


def _supported_path(masks,start,end,radius,*,square=False):
    """Measure an edge independently of its destination's outline colour.

    Keep each caller's original corridor width and require one colour mask to
    support70percent of the middle segment. A few bright chevrons or a union of
    two individually incomplete masks cannot manufacture a continuous edge.
    """
    import numpy as np
    height,width=next(iter(masks.values())).shape
    xs=np.linspace(start[0],end[0],101)[25:76].round().astype(int)
    ys=np.linspace(start[1],end[1],101)[25:76].round().astype(int)
    dx,dy=end[0]-start[0],end[1]-start[1]
    offsets=([(x,y) for y in range(-radius,radius+1) for x in range(-radius,radius+1)]
             if square else [(0,o) if abs(dx)>=abs(dy) else (o,0) for o in range(-radius,radius+1)])
    shares={}
    for name,mask in masks.items():
        supported=np.zeros(len(xs),bool)
        for ox,oy in offsets:
            supported|=mask[np.clip(ys+oy,0,height-1),np.clip(xs+ox,0,width-1)]
        shares[name]=float(supported.mean())
    # Prefer a qualifying legacy plane before the newly supported appearance,
    # preserving existing feature meaning when both glow layers support an edge.
    selected=next((name for name,share in shares.items() if share>=.70),None)
    if selected is None:return None
    return {selected:round(shares[selected],3),
            'path_support':{key:round(value,3) for key,value in shares.items()},
            'path_appearance':'bright_neutral' if selected=='bright_share' else 'warm_or_saturated'}


def gold_path_support(image, party, boxes):
    """Corroborate existing destinations by a narrow gold line on a darker board.

    Faded gold paths need a local contrast check. Uniform gold background,
    isolated badges and grey edges cannot meet the continuous stripe test.
    The measurement only ranks boxes the map reader already offered.
    """
    import cv2
    import numpy as np
    if not boxes or not party:
        return {}
    height, width = image.shape[:2]
    hue, sat, value = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2HSV))
    gold = (hue >= 13) & (hue <= 31) & (sat >= 125) & (value >= 70)
    start = np.asarray(party, dtype=float)
    samples = np.linspace(.30, .70, 51)[:, None]
    support = {}
    for box in boxes:
        x, y, w, h = box
        delta = np.array([x+w/2, y+h/2])-start
        length = np.linalg.norm(delta)
        if length < .05*width:
            continue
        across = np.array([-delta[1], delta[0]])/length
        line = start+samples*delta
        radius = max(2, round(.09*length))
        flank = round(.17*length)
        offsets = np.arange(-flank, flank+1)
        points = (line[:, None, :]+offsets[None, :, None]*across).round().astype(int)
        xs, ys = points[:, :, 0], points[:, :, 1]
        if xs.min()<0 or xs.max()>=width or ys.min()<0 or ys.max()>=height:
            continue
        core = abs(offsets)<=radius
        sides = abs(offsets)>.12*length
        if not sides.any():
            continue
        pixels = value[ys, xs]
        peak = np.where(gold[ys, xs][:, core], pixels[:, core], 0).max(axis=1)
        share = float(np.mean(peak >= np.maximum(70, pixels[:, sides].mean(axis=1)+20)))
        if share >= .80:
            support[tuple(box)] = round(share, 3)
    return support


def train_body(image, *, include_right_edge=False):
    """Locate one clock body with aligned lamps and an independent flame above.

    Lamp spacing, unlike the animated flame's bounding box, measures sprite scale.
    The node sits about .4 lamp spacings below that horizontal pair. This is a
    measured sprite anchor, not an assertion that a destination is reachable.
    """
    import cv2
    import numpy as np
    if image is None or getattr(image, 'ndim', 0) != 3:
        return None
    height, width = image.shape[:2]
    scale = width / 1920.0
    b, g, r = [image[:, :, i].astype(np.int16) for i in range(3)]
    warm = ((r > 100) & (g > 80) & (g * 10 >= r * 7)
            & (r - g <= 70) & (b < 80)).astype(np.uint8)
    warm[:round(.10 * height)] = 0
    warm[round(.86 * height):] = 0
    warm[:, round((.98 if include_right_edge else .90) * width):] = 0
    count, _, stats, centres = cv2.connectedComponentsWithStats(warm, 8)
    lamps = []
    for k in range(1, count):
        x, y, w, h, area = map(int, stats[k])
        point = tuple(float(v) for v in centres[k])
        if (4 * scale <= w <= 30 * scale and 4 * scale <= h <= 30 * scale
                and area >= 17 * scale * scale):
            lamps.append((point, w, h))
    flame = (r > 180) & (g > 85) & (r - g > 25) & (b < 100)
    found = []
    for i, (left, lw, lh) in enumerate(lamps):
        for right, rw, rh in lamps[i + 1:]:
            a, z = sorted((left, right))
            gap = z[0] - a[0]
            if not (20 * scale <= gap <= 100 * scale
                    and abs(a[1] - z[1]) <= min(7 * scale, .10 * gap)
                    and .6 <= lw / rw <= 1.7 and .6 <= lh / rh <= 1.7):
                continue
            cx, cy = (a[0] + z[0]) / 2, (a[1] + z[1]) / 2
            # At the map's internal half zoom antialiasing splits the clock
            # into several warm components. Measure the body region in lamp
            # units rather than demanding a screen-sized connected component.
            bx0, bx1 = max(0, round(cx - .35 * gap)), min(width, round(cx + .35 * gap))
            by0, by1 = max(0, round(cy - .9 * gap)), max(0, round(cy - .1 * gap))
            clock_pixels = np.argwhere(warm[by0:by1, bx0:bx1])
            if len(clock_pixels) < .04 * gap * gap:
                continue
            x0, x1 = max(0, round(cx - .23 * gap)), min(width, round(cx + .23 * gap))
            y0, y1 = max(0, round(cy - 2 * gap)), max(0, round(cy - gap))
            if np.count_nonzero(flame[y0:y1, x0:x1]) < .012 * gap * gap:
                continue
            clock = clock_pixels.mean(axis=0)
            found.append(dict(party=[round(cx), round(cy + .4 * gap)],
                              lamps=[list(a), list(z)], lamp_gap=round(gap, 2),
                              clock=[round(bx0 + float(clock[1]), 2),
                                     round(by0 + float(clock[0]), 2)]))
    # Theme glow can form a second, wider lamp pair around the very same
    # central clock. That is one body with nested measurements, not two trains.
    # Keep the smaller (more restrictive) scale only when all clock centres
    # agree; genuinely separate clock bodies remain ambiguous.
    if not found:
        return None
    first=min(found,key=lambda row:row['lamp_gap'])
    if any(math.hypot(row['clock'][0]-first['clock'][0],
                      row['clock'][1]-first['clock'][1])>.10*first['lamp_gap']
           for row in found):
        return None
    return first


def occupied_node(image):
    """Read the unique train over its base, including a panned right edge.

    This is the occupied room, never a destination/connectivity measurement.
    Lamp, clock and flame geometry must agree before testing either visual base.
    """
    import numpy as np
    anchor = train_body(image, include_right_edge=True)
    if anchor is None:
        return None
    height, width = image.shape[:2]
    x, y = anchor['party']; gap = anchor['lamp_gap']
    x0, x1 = max(0, round(x-.8*gap)), min(width, round(x+.8*gap))
    y0, y1 = max(0, round(y-.15*gap)), min(height, round(y+.75*gap))
    crop = image[y0:y1, x0:x1].astype(np.int16)
    if not crop.size:
        return None
    b, g, r = (crop[:, :, i] for i in range(3))
    share = float(np.mean((r > 130) & (r > 2.5*g) & (r > 2.5*b)))
    half = max(2, round(.4*gap))
    if not (half <= x < width-half and half <= y < height-half):
        return None
    proof = dict(anchor, box=[x-half, y-half, 2*half, 2*half])
    if .15 <= share <= .85:
        return dict(proof, red_share=round(share, 3), source='unique_train_on_red_base')
    # The current M8 artwork can surround that same train with an amber
    # ring. Both flanks must be bright over most rows. A gold reward badge,
    # leg of a route line, or the flame above the train cannot answer both.
    import cv2
    gold = []
    for lo, hi in ((-1.4, -.9), (.9, 1.4)):
        left, right = round(x+lo*gap), round(x+hi*gap)
        top, bottom = round(y-.4*gap), round(y+.5*gap)
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            return None
        hue, sat, value = cv2.split(cv2.cvtColor(image[top:bottom, left:right], cv2.COLOR_BGR2HSV))
        pixels = (hue >= 12)&(hue <= 35)&(sat >= 180)&(value >= 180)
        if pixels.mean()<.28 or pixels.any(axis=1).mean()<.75:
            return None
        gold.append(round(float(pixels.mean()),3))
    return dict(proof, gold_flank_shares=gold, source='unique_train_on_gold_ring')


def connected_red_node(image):
    """Read a compact red node and an independently supported outgoing path.

    A grey return edge or a white chevron is insufficient. Distance is measured
    between independent sprite centres, never inferred from a clickable box.
    Ambiguous connected nodes leave the existing general reader in charge.
    """
    import cv2
    import numpy as np
    anchor = train_body(image)
    if anchor is None:
        return None
    height, width = image.shape[:2]
    scale = width / 1920.0
    b, g, r = [image[:, :, i].astype(np.int16) for i in range(3)]
    red = ((r > 110) & (g * 3 < r) & (b * 3 < r)).astype(np.uint8)
    red[:round(.10 * height)] = 0
    red[round(.86 * height):] = 0
    red[:, round(.90 * width):] = 0
    kernel = max(1, round(5 * scale))
    red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((kernel, kernel), np.uint8))
    count, labels, stats, centres = cv2.connectedComponentsWithStats(red, 8)
    warm = (r > 100) & (g > 45) & (r > g * 1.35) & (b < r * .4)
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    bright=(hsv[:,:,1]<=60)&(hsv[:,:,2]>=200)
    saturated=(hsv[:,:,1]>=100)&(hsv[:,:,2]>=120)
    px, py = anchor['party']
    found = []
    for k in range(1, count):
        x, y, w, h, area = map(int, stats[k])
        if not (35 * scale <= w <= 240 * scale and 30 * scale <= h <= 230 * scale
                and .7 <= w / h <= 1.8 and .08 <= area / (w * h) <= .65):
            continue
        cx, cy = (round(float(value)) for value in centres[k])
        distance = math.hypot(cx - px, cy - py)
        if not (1.4 * max(w, h) <= distance <= 3 * max(w, h)):
            continue
        # A half-zoom outline can touch its lower affinity badge. Its pixel
        # centroid is steadier than the resulting bounding-box centre. Sample
        # a narrow lamp-scaled corridor so subpixel translation cannot erase
        # the visible outgoing line; cold/grey edges still contribute zero.
        radius = max(1, round(.07 * anchor['lamp_gap']))
        path=_supported_path({'warm_share':warm,'saturated_share':saturated,'bright_share':bright},
                             (px,py),(cx,cy),radius)
        if path is None:
            continue
        # An outline surrounds its centre; a chevron does not. Reward badges
        # may break a ring, so allow a missing hexagonal sector rather than
        # requiring topological closure. Continuous angular coverage avoids
        # a chevron touching a few pixels in all six arbitrarily phased bins.
        yy,xx=np.mgrid[y:y+h,x:x+w]
        radius=np.hypot((xx-cx)/(w/2),(yy-cy)/(h/2))
        component=(labels[y:y+h,x:x+w]==k)&(radius>=.45)&(radius<=1.25)
        angles=np.sort(np.arctan2(yy[component]-cy,xx[component]-cx))
        if not len(angles):continue
        gap=float(np.diff(np.r_[angles,angles[0]+2*np.pi]).max())
        if gap>np.pi/3:continue
        outline_proof=dict(outline_max_gap_degrees=round(math.degrees(gap),3))
        found.append(dict(anchor, target=[cx - w // 2, cy - h // 2, w, h],
                          outline=[x, y, w, h], point=[cx, cy],
                          step=round(distance),**path,**outline_proof,analysis_reference_size=[width,height],
                          source='train_body_and_connected_red_outline'))
    return found[0] if len(found) == 1 else None


def _connected_white_outline(image,party,*,template=None,map_rows=None):
    """A neutral ring and supported corridor corroborate independently measured pitch.

    Shared map measurements supply columns and repeated rows at the current
    internal zoom. Ornaments are an alternative measurement, not a requirement
    on every destination. Proposals still need original ring/path pixels.
    """
    import cv2
    import numpy as np
    from . import map_vision
    anchor=train_body(image)
    if anchor is None or max(abs(a-b) for a,b in zip(anchor['party'],party))>12*image.shape[1]/1920:
        return None
    h,w=image.shape[:2]
    ornaments=[]
    for marker in map_vision.node_markers(image,template=template):
        x,y,bw,bh=marker.ornament;cx,cy=x+bw/2,y+bh/2
        # Under-node template badges are a different measurement. The bright
        # ornament lane places its seed above the corresponding node body.
        if cy<marker.node[1]+marker.node[3]/2:ornaments.append((cx,cy))
    rows=map_vision.map_clicks(image,template=template,player=party) if map_rows is None else map_rows
    badges=[r['box'] for r in rows if r.get('kind')=='gold_badge_node']
    columns=[x+bw/2 for x,y,bw,bh in badges]
    gaps=[abs(a-b) for i,a in enumerate(columns) for b in columns[i+1:]
          if .05*w<=abs(a-b)<=.25*w]
    basis='gold_badge_columns'
    if not gaps:
        columns=[point[0] for point in ornaments];basis='bright_ornament_columns'
        gaps=[abs(a-b) for i,a in enumerate(columns) for b in columns[i+1:]
              if .05*w<=abs(a-b)<=.25*w]
    if not gaps:return None
    pitch=min(gaps)
    measurement=dict(source=basis,column_centres=sorted(set(columns)))
    seeds=[]
    if basis=='gold_badge_columns':
        # Badge boxes may carry a constant vertical lift at this zoom. The
        # independently occupied train calibrates that phase; do not use the
        # shop's interior glyph as an above-node ornament with a fixed offset.
        groups=[]
        for value in sorted(y+bh/2 for x,y,bw,bh in badges):
            if groups and abs(value-sum(groups[-1])/len(groups[-1]))<.1*pitch:groups[-1].append(value)
            else:groups.append([value])
        levels=[sum(group)/len(group) for group in groups]
        nearby=[y for y in levels if abs(y-party[1])<.25*pitch]
        phase=(party[0]-columns[0])/pitch
        if (len(levels)>=2 and len(nearby)==1 and abs(phase-round(phase))<.12):
            shift=party[1]-nearby[0]
            calibrated=[y+shift for y in levels]
            seeds.extend((party[0]+pitch,y,'train_calibrated_lattice') for y in calibrated)
            measurement.update(row_centres=levels,row_phase_shift=shift,calibrated_rows=calibrated)
    seeds.extend((cx,cy+.18*pitch,'bright_ornament') for cx,cy in ornaments)
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    neutral=(hsv[:,:,1]<=60)&(hsv[:,:,2]>=120)
    bright=(hsv[:,:,1]<=60)&(hsv[:,:,2]>=200)
    saturated=(hsv[:,:,1]>=100)&(hsv[:,:,2]>=120)
    found=[]
    for cx,cy,seed_source in seeds:
        if not .10*h<=cy<.84*h or not .025*w<=cx<.90*w:continue
        dx,dy=cx-party[0],cy-party[1]
        if not .7*pitch<=dx<=1.35*pitch or abs(dy)>1.35*pitch:continue
        x0,x1=max(0,round(cx-.24*pitch)),min(w,round(cx+.24*pitch))
        y0,y1=max(0,round(cy-.24*pitch)),min(h,round(cy+.24*pitch))
        yy,xx=np.mgrid[y0:y1,x0:x1];radius=np.hypot(xx-cx,yy-cy)
        annulus=(radius>=.12*pitch)&(radius<=.23*pitch)
        interior=radius<.07*pitch
        if not interior.any() or float(hsv[y0:y1,x0:x1,2][interior].mean())>110:continue
        ring=neutral[y0:y1,x0:x1]&annulus
        if not .01<=float(ring.sum())/max(1,int(annulus.sum()))<=.30:continue
        sectors=((np.arctan2(yy-cy,xx-cx)+np.pi)*3/np.pi).astype(int)%6
        counts=[int(np.count_nonzero(ring&(sectors==i))) for i in range(6)]
        if sum(n>=max(8,round(.00005*pitch*pitch)) for n in counts)<5:continue
        path=_supported_path({'warm_share':saturated,'bright_share':bright},party,(cx,cy),
                             max(1,round(.015*pitch)))
        if path is None:continue
        cx,cy=round(cx),round(cy);side=max(12,round(.10*pitch))
        # Different measurements of one ring are not two destinations. Distinct
        # supported endpoints still withhold the shortcut, as before.
        if any(math.hypot(cx-r['point'][0],cy-r['point'][1])<.12*pitch for r in found):continue
        found.append(dict(party=list(anchor['party']),point=[cx,cy],
            target=[cx-side//2,cy-side//2,side,side],step=round(math.hypot(dx,dy)),
            measured_column_pitch=round(pitch,2),**path,
            ring_sector_pixels=counts,seed_source=seed_source,lattice_measurement=measurement,
            analysis_reference_size=[w,h],source='train_and_neutral_outline_on_bright_path'))
    return found[0] if len(found)==1 else None


def connected_ring_node(image, *, template=None):
    """Propose a unique lit ring joined to a train by a supported outgoing path.

    Grey return edges do not establish a forward connection. A separate neutral
    outline lane separately validates a locally complete neutral ring. Outline
    colour never chooses the outgoing path's eligible appearance.
    Pitch comes from
    distinct measured node columns, excluding the destination, rather than a
    badge box's size. This is a bounded navigation proposal, not room entry.
    """
    import cv2
    import numpy as np
    from . import map_vision
    if image is None or getattr(image,'ndim',0)!=3:return None
    if image.shape[1]<1920:
        factor=1920/image.shape[1]
        bigger=cv2.resize(image,(1920,round(image.shape[0]*factor)),interpolation=cv2.INTER_CUBIC)
        found=connected_ring_node(bigger,template=template)
        if found is None:return None
        found=dict(found)
        for key in ('party','target','point'):found[key]=[round(v/factor) for v in found[key]]
        found['step']=round(found['step']/factor)
        found['measured_column_pitch']=round(found['measured_column_pitch']/factor,2)
        found['analysis_reference_size']=[1920,bigger.shape[0]]
        return found
    party=map_vision.locomotive_marker(image)
    if party is None:return None
    h,w=image.shape[:2];scale=w/1920.0
    rows=map_vision.map_clicks(image,template=template,player=party)
    rings=[r for r in rows if r.get('kind')=='lit_ring']
    if not rings:return _connected_white_outline(image,party,template=template,map_rows=rows)
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    lit=(hsv[:,:,1]>=100)&(hsv[:,:,2]>=120)
    bright=(hsv[:,:,1]<=60)&(hsv[:,:,2]>=200)
    found=[]
    for ring in rings:
        x,y,bw,bh=map(int,ring['box']);cx,cy=x+bw/2,y+bh/2
        columns=[float(party[0])]
        for row in rows:
            if row.get('kind')!='gold_badge_node':continue
            bx,by,rw,rh=row['box'];nx,ny=bx+rw/2,by+rh/2
            if abs(nx-cx)<48*scale and abs(ny-cy)<96*scale:continue
            columns.append(nx)
        gaps=[abs(a-b) for i,a in enumerate(columns) for b in columns[i+1:]
              if .05*w<=abs(a-b)<=.25*w]
        if not gaps:continue
        pitch=min(gaps);distance=math.hypot(cx-party[0],cy-party[1])
        if not .7*pitch<=max(abs(cx-party[0]),abs(cy-party[1]))<=1.35*pitch:continue
        path=_supported_path({'warm_share':lit,'bright_share':bright},party,(cx,cy),
                             max(1,round(3*scale)),square=True)
        if path is None:continue
        found.append(dict(party=list(party),target=[x,y,bw,bh],point=[round(cx),round(cy)],
            step=round(distance),measured_column_pitch=round(pitch,2),**path,analysis_reference_size=[w,h],
            source=('locomotive_and_saturated_path_to_lit_ring' if 'warm_share' in path
                    else 'locomotive_and_neutral_path_to_lit_ring')))
    return (found[0] if len(found)==1 else
            _connected_white_outline(image,party,template=template,map_rows=rows) if not found else None)


def connected_compact_nodes(image):
    """Small coloured bodies need train/edge proof, not a screen-sized ring.

    Reuse the saturated component reader without reducing its brightness/chroma
    tests. Internal zoom changes body size; independent lamp spacing bounds the
    one-hop neighbourhood. The corridor follows the measured body's uncertainty,
    not a fixed room coordinate. These are alternatives, not inferred room types.
    """
    import cv2
    from . import map_vision
    if image is None or getattr(image,'ndim',0)!=3:return []
    # As in the existing ring reader, normalize small captures before the
    # shared component morphology. A fixed5px closing kernel at720p otherwise
    # joins the glyph to its surrounding glow and the whole path. Return all
    # measured pixel fields in the caller's native coordinate system.
    if image.shape[1]<1920:
        factor=1920/image.shape[1]
        # Linear normalization retains the filled cyan shop glyph on the
        # actual 1280px Floor 4 capture. The cubic halo fragmented it before
        # the unchanged body and continuous-path tests could see it.
        bigger=cv2.resize(image,(1920,round(image.shape[0]*factor)),interpolation=cv2.INTER_LINEAR)
        rows=connected_compact_nodes(bigger)
        for row in rows:
            for key in ('party','target','point','clock'):
                row[key]=[round(v/factor,2) if key=='clock' else round(v/factor) for v in row[key]]
            row['lamps']=[[round(v/factor,2) for v in point] for point in row['lamps']]
            row['lamp_gap']=round(row['lamp_gap']/factor,2)
            row['step']=round(row['step']/factor)
            row['body']=dict(row['body'])
            for key in ('point','box'):row['body'][key]=[round(v/factor) for v in row['body'][key]]
            row['body']['area']=round(row['body']['area']/(factor*factor))
        return rows
    anchor=train_body(image)
    if anchor is None:return []
    height,width=image.shape[:2];scale=width/1920
    px,py=anchor['party'];gap=anchor['lamp_gap']
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    saturated=(hsv[:,:,1]>=100)&(hsv[:,:,2]>=120)
    bright=(hsv[:,:,1]<=60)&(hsv[:,:,2]>=200)
    # Screen resolution and the map's internal zoom are independent. Retained
    # small/large views measure35/70px lamp gaps and27/95px glyphs. The same
    # body lane must scale with its independent train, not a70px screen cap.
    bodies=map_vision.lit_components(image,min_pixels=180*scale*scale,
        min_side=20*scale,max_side=2*gap,min_fill=.18,max_fill=.75,
        min_ratio=.4,max_ratio=2)
    found=[]
    for body in bodies:
        x,y,bw,bh=body['box'];cx,cy=body['point'];dx,dy=cx-px,cy-py
        if not (bw>=24*scale and bh>=20*scale and 4*gap<=dx<=8*gap
                and abs(dy)<=6*gap and math.hypot(dx,dy)<=8*gap):continue
        path=_supported_path({'saturated_share':saturated,'bright_share':bright},
            (px,py),(cx,cy),max(1,round(.5*max(bw,bh))),square=True)
        if path is None:continue
        found.append(dict(anchor,target=list(body['box']),point=[cx,cy],
            step=round(math.hypot(dx,dy)),body=dict(body),**path,
            analysis_reference_size=[width,height],
            candidate_kind='lit_icon',
            source='train_body_and_supported_compact_glyph'))
    return found


def connected_hexagons(image,*,template=None):
    """Lit hexagons one column ahead, read from the hexagon alone (map_hexagons).

    The other lanes need a ring, path or glyph in a colour they know. A node the game
    lights in pale cream (the super shop of live ``-141507``, hue 16, saturation 80)
    falls between their masks, and the planner then fell back to badge nodes behind
    the party. This lane reads the outer hexagon's state and leaves the icon apart.
    """
    from . import map_hexagons, map_vision
    if image is None or getattr(image,'ndim',0)!=3:return []
    party=map_vision.locomotive_marker(image)
    if party is None:return []
    rows=map_vision.map_clicks(image,template=template,player=party)
    boxes=[r['box'] for r in rows if r.get('kind') in ('gold_badge_node','lattice_step')]
    measured=map_hexagons.column_pitch(party,boxes,image.shape[1])
    _,nodes=map_hexagons.lit_neighbours(image,party,measured)
    return nodes


def connected_nodes(image,*,template=None):
    """Existing red/ring precedence; then compact alternatives; then lit hexagons."""
    legacy=connected_red_node(image) or connected_ring_node(image,template=template)
    if legacy is not None:return [legacy]
    return connected_compact_nodes(image) or connected_hexagons(image,template=template)


def connected_node(image,*,template=None):
    """Compatibility: a single measurement never silently chooses alternatives."""
    found=connected_nodes(image,template=template)
    return found[0] if len(found)==1 else None
