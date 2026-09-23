import json, collections, statistics
R=json.load(open('normalized.json'))
REG={v['name'].upper():v for v in json.load(open('registry.json'))}
BERTH_LEN={'North Pier West':410,'North Pier East':240,'North Pier Face':75,
           'Inner Channel':55,'South Float West':90,'South Float East':90}
V=[r for r in R if r['kind']=='vessel']
names=sorted({r['name'] for r in V})
hist=collections.defaultdict(list)
for r in V:
    L=BERTH_LEN.get(r['berth'])
    if L: hist[r['name']].append(L)

rows=[]
for n in names:
    reg=REG.get(n.upper())
    bound=min(hist[n]) if hist[n] else None
    maxb=max(hist[n]) if hist[n] else None
    rows.append(dict(name=n, loa=reg['loa'] if reg else None, bound=bound, maxberth=maxb, stays=len([r for r in V if r['name']==n])))
known=[r for r in rows if r['loa']]
print('scheduled vessels:',len(rows),' with registry LOA:',len(known))
print('with a berth-derived upper bound:',sum(1 for r in rows if r['bound']))
print('with neither:',sum(1 for r in rows if not r['loa'] and not r['bound']))
ok=[r for r in known if r['bound']]
viol=[r for r in ok if r['loa']>r['bound']]
print(f'\nvalidation: of {len(ok)} vessels with BOTH a true LOA and a berth bound, {len(viol)} violate the bound')
for r in viol: print('   ',r['name'],'LOA',r["loa"],"' but smallest berth used",r['bound'],"'")
print('\nslack on the rest (bound - loa):', sorted(r['bound']-r['loa'] for r in ok if r not in viol))
# how much of the fleet is CONSTRAINED usefully
tight=[r for r in rows if not r['loa'] and r['bound'] and r['bound']<=90]
print(f'\nvessels with no LOA but bounded <=90ft: {len(tight)}')
print('bound distribution:',collections.Counter(r['bound'] for r in rows if r['bound']))
json.dump(rows,open('vessel_inference.json','w'))
