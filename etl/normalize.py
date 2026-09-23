import json, re, datetime, collections, unicodedata
B=json.load(open('raw_bookings.json'))

PREF = r"(?:R/V|M/V|M/Y|S/V|S/Y|F/V|OS/V|OSV|TUG|BARGE)"
NOTE_PATTERNS = [
 r'^(eta|etd|arriv|depart|returns|delayed|touch and go)\b', r'^\w+ \d{3,4}$',
 r'^(fuel|bunker|provision|load|wire spool|water/slops)', r'^holiday$', r'^arrives\b', r'^departs\b',
]
EVENT_WORDS = ['sail day','open house','reception','tour','stroll','training','drill','film crew','campus event','regatta','festival','ceremony','class']
CLOSURE_WORDS = ['repair','closed','maintenance','rebuild','no docking','no usage','restricted','inspection','bollard','utility work','concrete','paving','ultrasonic','road race','crane access','survey work']

def classify(lbl):
    l = lbl.strip(); low = l.lower()
    if re.match(PREF+r"\b", l, re.I): return 'vessel'
    for p in NOTE_PATTERNS:
        if re.search(p, low): return 'note'
    if any(w in low for w in CLOSURE_WORDS): return 'closure'
    if any(w in low for w in EVENT_WORDS): return 'event'
    return 'note'

def canon_vessel(l):
    s = re.sub(r'\s+', ' ', l.strip())
    s = re.sub(r'^OS/V\b', 'OSV', s, flags=re.I)
    m = re.match(r'^('+PREF+r")\s+(.*)$", s, re.I)
    if not m: return s.title(), None
    pre, rest = m.group(1).upper(), m.group(2)
    pre = {'OSV':'OSV','TUG':'Tug','BARGE':'Barge'}.get(pre, pre)
    rest = re.sub(r"\s*\d{2,3}\s*'\s*$", '', rest).strip()
    name = ' '.join(w if (len(w)>1 and w.isupper() and not w.isalpha()) else w.capitalize() for w in rest.split())
    return f'{pre} {name}', pre

recs=[]
for b in B:
    kind = classify(b['label'])
    name, pre = canon_vessel(b['label']) if kind=='vessel' else (re.sub(r'\s+',' ',b['label'].strip()), None)
    try:
        s = datetime.date(b['year'], b['month'], b['d1']); e = datetime.date(b['year'], b['month'], b['d2'])
    except ValueError: continue
    recs.append(dict(kind=kind, name=name, prefix=pre, berth=b['berth'], berth_len=b['berth_len'],
                     overflow=b['overflow'], start=s.isoformat(), end=e.isoformat(),
                     year=b['year'], sheet=b['sheet'], row=b['row'], raw=b['label'], fill=b['fill']))

print('by kind', collections.Counter(r['kind'] for r in recs))
V=[r for r in recs if r['kind']=='vessel']
print('distinct canonical vessels', len({r['name'] for r in V}))
# how many raw variants collapsed
raw2canon=collections.defaultdict(set)
for r in V: raw2canon[r['name']].add(r['raw'])
multi={k:v for k,v in raw2canon.items() if len(v)>1}
print('vessels with >1 raw spelling:', len(multi))
for k,v in list(multi.items())[:8]: print('   ',k,'<-',sorted(v))

# cross-month stay stitching
V.sort(key=lambda r:(r['berth'] or '', r['name'], r['start']))
stitched=0
out=[]; 
for r in V:
    if out and out[-1]['name']==r['name'] and out[-1]['berth']==r['berth']:
        pe=datetime.date.fromisoformat(out[-1]['end']); ps=datetime.date.fromisoformat(r['start'])
        if (ps-pe).days<=1:
            out[-1]['end']=max(out[-1]['end'], r['end']); stitched+=1; continue
    out.append(dict(r))
print('cross-boundary stays stitched:', stitched)
json.dump(recs, open('normalized.json','w'))
