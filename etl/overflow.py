import json, datetime, collections
R=json.load(open('normalized.json'))
d=datetime.date.fromisoformat
ov=[r for r in R if r['overflow'] and r['kind'] in ('vessel','event')]
main=[r for r in R if not r['overflow'] and r['kind'] in ('vessel','event') and r['berth']]
print('overflow occupancy entries:',len(ov))
# Do overflow entries overlap in time with the berth row directly above them?
byb=collections.defaultdict(list)
for m in main: byb[m['berth']].append(m)
hits=0; tested=0
for o in ov:
    if not o['berth']: continue
    tested+=1
    for m in byb.get(o['berth'],[]):
        if d(m['start'])<=d(o['end']) and d(m['end'])>=d(o['start']) and m['name']!=o['name']:
            hits+=1; break
print(f'overflow entries that temporally collide with the berth row above: {hits}/{tested} ({100*hits/max(tested,1):.0f}%)')
print()
print('What kinds of things end up in overflow rows:')
print(collections.Counter(r['kind'] for r in [x for x in R if x['overflow']]))
names=collections.Counter(r['name'] for r in ov)
print('top overflow occupants:',names.most_common(10))
# how many distinct rows below each berth get used
print()
rows=collections.Counter((r['sheet'],r['row']) for r in R if r['overflow'])
print('distinct (sheet,row) used as overflow:',len(rows))
