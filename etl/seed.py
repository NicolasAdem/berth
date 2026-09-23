import json, re, datetime, collections
R=json.load(open('normalized.json'))
REG={v['name'].upper():v for v in json.load(open('registry.json'))}
d=datetime.date.fromisoformat
EPOCH=datetime.date(1997,1,1)

BERTHS=[
 dict(id='npw',name='North Pier West',len=410,type='linear'),
 dict(id='npe',name='North Pier East',len=240,type='linear'),
 dict(id='npf',name='North Pier Face',len=75,type='linear'),
 dict(id='inc',name='Inner Channel',len=55,type='linear'),
 dict(id='sfw',name='South Float West',len=90,type='linear'),
 dict(id='sfe',name='South Float East',len=90,type='linear'),
 dict(id='nfp',name='North Finger Piers',len=None,type='slips'),
 dict(id='scs',name='Small craft slips',len=None,type='slips'),
 dict(id='uns',name='Unassigned',len=None,type='none'),
]
BMAP={'North Pier West':'npw','North Pier East':'npe','North Pier Face':'npf',
 'Inner Channel':'inc','South Float West':'sfw','South Float East':'sfe',
 'North Finger Piers':'nfp','Small craft slips (institution boats)':'scs'}

# ---- vessels ----
sched_names=sorted({r['name'] for r in R if r['kind']=='vessel'})
vessels={}
for n in sched_names:
    reg=REG.get(n.upper())
    vessels[n]=dict(name=n, loa=reg['loa'] if reg else None,
        draft=reg['draft'] if reg else None,
        op=(reg['operator'] if reg else None),
        contact=(reg['contacts'][0] if reg and reg['contacts'] else None),
        email=(reg['emails'][0] if reg and reg['emails'] else None),
        src='registry' if reg else 'schedule')
# registry-only vessels (never scheduled) -> keep, they're part of the fleet file
for k,v in REG.items():
    if v['name'] not in vessels:
        vessels[v['name']]=dict(name=v['name'],loa=v['loa'],draft=v['draft'],op=v['operator'],
            contact=(v['contacts'][0] if v['contacts'] else None),
            email=(v['emails'][0] if v['emails'] else None), src='registry-only')
vlist=sorted(vessels.values(), key=lambda v:v['name'])
vidx={v['name']:i for i,v in enumerate(vlist)}
print('fleet size:',len(vlist),'with LOA:',sum(1 for v in vlist if v['loa']))

# ---- reservations ----
KIND={'vessel':0,'event':1,'closure':2,'note':3}
res=[]
for r in R:
    b = 'uns' if r['overflow'] or not r['berth'] else BMAP.get(r['berth'],'uns')
    s,e = d(r['start']), d(r['end'])
    vi = vidx[r['name']] if r['kind']=='vessel' else -1
    res.append([ KIND[r['kind']], vi, b, (s-EPOCH).days, (e-s).days,
                 '' if r['kind']=='vessel' else r['name'],
                 1 if r['overflow'] else 0 ])
# stitch same vessel+berth contiguous (undo the month-boundary split)
res.sort(key=lambda x:(x[2],x[1],x[5],x[3]))
out=[]; stitched=0
for x in res:
    if out:
        p=out[-1]
        if p[0]==x[0] and p[1]==x[1] and p[2]==x[2] and p[5]==x[5] and x[3]-(p[3]+p[4])<=1 and x[3]>=p[3]:
            p[4]=max(p[4], x[3]+x[4]-p[3]); stitched+=1; continue
    out.append(list(x))
print('reservations:',len(out),'(stitched',stitched,'month-boundary splits)')
print('by kind',collections.Counter(x[0] for x in out))
print('by berth',collections.Counter(x[2] for x in out))

seed=dict(
  epoch=EPOCH.isoformat(),
  berths=BERTHS,
  vessels=[[v['name'],v['loa'],v['draft'],v['op'],v['contact'],v['email'],v['src']] for v in vlist],
  res=out,
  meta=dict(source='Dock_Schedule_-_Synthetic_Sample.xlsx',
            sheets=23, first='1997-08-02', last='2019-12-31'))
json.dump(seed, open('seed.json','w'), separators=(',',':'))
import os; print('seed size', os.path.getsize('seed.json')//1024,'KB')
