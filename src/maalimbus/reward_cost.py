"""Native currency/sign/cost evidence for the retained English reward layout.

Recognizing an offer does not authorize spending or establish received rewards.
"""
import re
from .vision import find

#: Where the currency icon and the deduction sign sit, by the number of digits in the
#: cost. The cost is right-aligned, so a second digit moves both six pixels left. The
#: one-digit row was measured on `window-20261008-144554/frame-0458` (6 modules, weekly
#: 1/3); the two-digit row on `pi-20261120-193352/frame-0269` (18 modules, weekly 3/3),
#: where the one-digit boxes cut the icon and its template scored 0.78, so the offer
#: read as unknown and a cleared run stopped without a quote. Each layout has templates
#: cropped from its own frame; neither pair fits inside the other layout's boxes.
LAYOUTS=(
    ('one_digit','reward/module-currency.png',(1370,786,65,63),
     'reward/deduction-sign.png',(1429,805,21,30)),
    ('two_digit','reward/module-currency-two-digit.png',(1364,786,65,63),
     'reward/deduction-sign-two-digit.png',(1423,805,21,30)))
DIGITS={'one_digit':r'[1-9]','two_digit':r'[1-9]\d'}


def page_anchors(records,size):
    gates=[(r'^Exploration Reward$',(.39,.12,.60,.20)),
           # Floor 5 on a cleared run. A run that was lost prints the floor it ended on
           # and how far it got there: `Floor 5 [HARD] 3/4` on pi-20261123-232359/frame-0004.
           (r'^Floor [1-5]$',(.24,.56,.31,.61)),
           (r'^\[(?:HARD|NORMAL)\]$',(.24,.59,.31,.64)),
           # The floor's own count, not a constant: 7/7 on the October runs, 4/4 on
           # pi-20261123-133044, whose stylised digits scored 0.82. Numerator and
           # denominator must be equal (the floor is finished). The same dialog reopened
           # from the dungeon list after a game restart scored 0.65 for the same 4/4
           # (pi-20261123-180315/frame-0032): the score follows what is behind the
           # modal, so the equal-count structure carries the identity, not the score.
           # A lost run's count is short of its floor (3/4); `floor_count` says which.
           (r'^\d{1,2}/\d{1,2}$',(.25,.62,.31,.69),.5),
           # 'To Window' right after the final victory; 'To List' when the dialog is
           # reopened from the dungeon list (same frame: [904,798,112,35]).
           (r'^To (?:Window|List)$',(.43,.72,.56,.79)),
           (r'^Claim$',(.62,.72,.71,.79)),
           (r'^Weekly$',(.22,.29,.31,.35)),
           (r'^Bonuses$',(.22,.33,.31,.38))]
    return all(len(find(records,gate[0],gate[1],size,gate[2] if len(gate)>2 else .9))==1 for gate in gates)

def floor_count(records,size):
    """``(floor, done, of)`` as the reward dialog prints them, or ``None``.

    ``done == of`` on floor 5 is a cleared dungeon; anything else is a run that ended
    early. The dialog is the only place this is still readable once it covers the summary.
    """
    floor=find(records,r'^Floor [1-5]$',(.24,.56,.31,.61),size,.9)
    count=find(records,r'^\d{1,2}/\d{1,2}$',(.25,.62,.31,.69),size,.5)
    if len(floor)!=1 or len(count)!=1:return None
    done,of=(int(part) for part in count[0].text.split('/'))
    if not 0<=done<=of or of<1:return None
    return int(floor[0].text.split()[1]),done,of


def combine_evidence(readings):
    """All independently gated native results must be unique and agree.

    The icon and the sign name the layout they were found in, and the cost has to have
    that layout's number of digits: a two-digit cost read beside a one-digit icon is two
    readings that disagree about where the row is, not an offer.
    """
    digits=[];layouts=[]
    for purpose in ('currency','deduction','cost_digit_a','cost_digit_b','weekly_count'):
        rows=[r for r in readings if r['purpose']==purpose]
        if len(rows)!=1 or len(rows[0]['results'])!=1:return None
        result=rows[0]['results'][0]
        if result['score']<(.95 if purpose in ('currency','deduction') else .9):return None
        if purpose in ('currency','deduction'):
            layouts.append(rows[0].get('layout','one_digit'))
        elif purpose.startswith('cost_digit'):
            text=result.get('text','').strip()
            if not re.fullmatch(r'[1-9]\d?',text):return None
            digits.append(text)
        elif purpose=='weekly_count':
            match=re.fullmatch(r'([0-3])/3',result.get('text','').strip())
            if not match:return None
            weekly=int(match[1])
    if digits[0]!=digits[1] or layouts[0]!=layouts[1]:return None
    if layouts[0] not in DIGITS or not re.fullmatch(DIGITS[layouts[0]],digits[0]):return None
    return dict(currency='enkephalin_modules',cost=int(digits[0]),weekly=weekly)

def crops_of(purpose,own):
    """The layout's own crop first, then the other layout's crop of the same mark."""
    index=1 if purpose=='currency' else 3
    return [own]+[layout[index] for layout in LAYOUTS if layout[index]!=own]


def observe_native(context,image,records):
    from maa.pipeline import JOCR,JRecognitionType,JTemplateMatch
    size=(image.shape[1],image.shape[0])
    if size!=(1920,1080) or not page_anchors(records,size):return None,[]
    attempts=[]
    for layout,currency,currency_roi,sign,sign_roi in LAYOUTS:
        rows=[]
        for purpose,template,roi in (('currency',currency,currency_roi),('deduction',sign,sign_roi)):
            # Both retained crops of a mark are the same mark; which layout it is in is
            # decided by the box, not by the crop. On pi-20261123-133044/frame-0548 (5
            # modules, weekly 0/3) the one-digit crop scored 0.946 in the one-digit box
            # and the other crop of the same icon 0.974 there, so an authorised claim
            # stopped on a threshold. The best single crop in the box is the reading.
            best=None
            for crop in crops_of(purpose,template):
                detail=context.run_recognition_direct(JRecognitionType.TemplateMatch,
                    JTemplateMatch(template=[crop],roi=roi,threshold=[.95]),image)
                results=detail.filtered_results if detail is not None and detail.hit else []
                if len(results)==1 and (best is None or results[0].score>best[1]):
                    best=(crop,results[0].score)
            rows.append(dict(purpose=purpose,layout=layout,roi=list(roi),
                template=best[0] if best else template,
                results=[dict(score=best[1])] if best else []))
        attempts.append(rows)
    # One layout at most can show both marks. With none, the one-digit attempt is kept
    # as the record of what was looked for, which is what earlier frames carry.
    evidence=next((rows for rows in attempts if all(len(r['results'])==1 for r in rows)),attempts[0])
    for purpose,roi,expected in (
        ('cost_digit_a',(1448,793,28,45),r'^[1-9]\d?$'),
        ('cost_digit_b',(1444,790,36,50),r'^[1-9]\d?$'),
        ('weekly_count',(650,340,88,72),r'^[0-3]/3$')):
        detail=context.run_recognition_direct(JRecognitionType.OCR,
            JOCR(roi=roi,only_rec=True,expected=[expected],threshold=.9),image)
        results=detail.filtered_results if detail is not None and detail.hit else []
        evidence.append(dict(purpose=purpose,roi=list(roi),only_rec=True,
            results=[dict(text=r.text,score=r.score) for r in results]))
    return combine_evidence(evidence),evidence
