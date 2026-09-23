import json, datetime, collections, itertools, re
R=json.load(open('normalized.json'))
reg=json.load(open('registry_probe.json'))['loa']
d=datetime.date.fromisoformat
occ=[r for r in R if r['kind'] in ('vessel','event') and not r['overflow'] and r['berth']]
# stitch same vessel/berth contiguous
occ.sort(key=lambda r:(r['berth'], r['name'], r['start']))
stays=[]
for r in occ:
    if stays and stays[-1]['name']==r['name'] and stays[-1]['berth']==r['berth'] and (d(r['start'])-d(stays[-1]['end'])).days<=1:
        stays[-1]['end']=max(stays[-1]['end'],r['end']); continue
    stays.append(dict(r))
print('occupancy stays:',len(stays))

byberth=collections.defaultdict(list)
for s in stays: byberth[s['berth']].append(s)
conf=[]
for b,lst in byberth.items():
    lst.sort(key=lambda r:r['start'])
    for i in range(len(lst)):
        for j in range(i+1,len(lst)):
            a,c=lst[i],lst[j]
            if d(c['start'])>d(a['end']): break
            if a['name']==c['name']: continue
            ov=(min(d(a['end']),d(c['end']))-max(d(a['start']),d(c['start']))).days+1
            conf.append(dict(berth=b,a=a['name'],b=c['name'],start=max(a['start'],c['start']),
                             end=min(a['end'],c['end']),days=ov,year=a['year'],
                             arow=a['row'],brow=c['row'],sheet=a['sheet']))
print('DOUBLE BOOKINGS:',len(conf))
print('by year',sorted(collections.Counter(c['year'] for c in conf).items()))
print('by berth',collections.Counter(c['berth'] for c in conf).most_common())
print('total conflict-days',sum(c['days'] for c in conf))
for c in conf[:12]: print('  ',c['year'],c['berth'],'|',c['a'],'VS',c['b'],c['start'],'->',c['end'],f"({c['days']}d)")

# closures overlapped by bookings
clos=[r for r in R if r['kind']=='closure' and r['berth'] and not r['overflow']]
cc=0; ex=[]
for cl in clos:
    for s in byberth.get(cl['berth'],[]):
        if d(s['start'])<=d(cl['end']) and d(s['end'])>=d(cl['start']):
            cc+=1; ex.append((cl['year'],cl['berth'],cl['name'],s['name'],s['start']))
print('\nBOOKINGS DURING CLOSURES:',cc)
for e in ex[:8]: print('   ',e)

# fit check
known={}; unknown=set()
for s in stays:
    if s['kind']!='vessel': continue
    L=reg.get(s['name'].upper())
    if L: known[s['name']]=L
    else: unknown.add(s['name'])
print('\nvessels w/ known LOA:',len(known),' unknown:',len(unknown))
over=[s for s in stays if s['kind']=='vessel' and s['berth_len'] and reg.get(s['name'].upper()) and reg[s['name'].upper()]>s['berth_len']]
print('OVERSIZE (known LOA > berth):',len(over))
for o in over[:10]: print('   ',o['year'],o['name'],reg[o['name'].upper()],"' in",o['berth'],o['berth_len'],"'")
verifiable=sum(1 for s in stays if s['kind']=='vessel' and s['berth_len'] and reg.get(s['name'].upper()))
tot=sum(1 for s in stays if s['kind']=='vessel' and s['berth_len'])
print(f'fit-verifiable stays: {verifiable}/{tot} = {100*verifiable/tot:.1f}%')
json.dump(dict(conflicts=conf,stays=stays),open('conflicts.json','w'))
