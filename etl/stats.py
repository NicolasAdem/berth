import json, datetime, collections
R=json.load(open('normalized.json'))
d=datetime.date.fromisoformat
BL={'North Pier West':410,'North Pier East':240,'North Pier Face':75,'Inner Channel':55,
    'South Float West':90,'South Float East':90}
occ=[r for r in R if r['kind'] in ('vessel','event') and r['berth'] in BL and not r['overflow']]
byy=collections.defaultdict(lambda: collections.defaultdict(set))
for r in occ:
    s,e=d(r['start']),d(r['end'])
    for i in range((e-s).days+1):
        byy[r['year']][r['berth']].add(s+datetime.timedelta(days=i))
print('Berth-day occupancy % by year (days occupied / days in year):')
print(f"{'year':6s}"+''.join(f'{k[:11]:>13s}' for k in BL))
tot=collections.Counter()
for y in sorted(byy):
    n=366 if y%4==0 else 365
    line=f'{y:<6d}'
    for k in BL:
        c=len(byy[y][k]); tot[k]+=c
        line+=f'{100*c/n:12.0f}%'
    print(line)
print()
grand=sum(tot.values()); yrs=len(byy)
print('23-yr average occupancy per berth:')
for k in BL:
    print(f'  {k:20s} {BL[k]:4d}ft  {100*tot[k]/(yrs*365):5.1f}% of days')
print()
print(f'Facility: {sum(BL.values())} linear feet across {len(BL)} berths')
print('Peak simultaneous berths in use:')
allday=collections.Counter()
for r in occ:
    s,e=d(r['start']),d(r['end'])
    for i in range((e-s).days+1): allday[s+datetime.timedelta(days=i)]+=1
print(collections.Counter(allday.values()))
print('busiest days:',allday.most_common(5))
print()
print('date span:',min(r['start'] for r in R),'->',max(r['end'] for r in R))
print('total rows extracted:',len(R))
