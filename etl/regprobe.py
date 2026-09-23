import openpyxl, re, json, collections
import os; P=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data','Dock_Schedule_-_Synthetic_Sample.xlsx')
wb=openpyxl.load_workbook(P,data_only=True)
PREF=r"(?:R/V|M/V|M/Y|S/V|S/Y|F/V|OS/V|OSV|Tug|Barge)"
vnames=collections.Counter(); loa={}
cells=collections.Counter()
for sh in ['Science','Yachts']:
    ws=wb[sh]
    for row in ws.iter_rows():
        for c in row:
            v=c.value
            if not isinstance(v,str): continue
            v=v.strip()
            if not v: continue
            if re.match(PREF+r"\b", v, re.I):
                m=re.search(r"(\d{2,3})\s*'", v)
                nm=re.sub(r"\s*\d{2,3}\s*'\s*$",'',v).strip()
                vnames[nm]+=1
                if m: loa.setdefault(nm.upper(),int(m.group(1)))
            elif re.match(r"^(LOA|Cell|Ph|Tel)", v, re.I): cells['contactish']+=1
            elif '@' in v: cells['email']+=1
            else: cells['other:'+v[:28]]+=1
print('registry vessels:',len(vnames),'with LOA:',len(loa))
print(list(vnames.items())[:20])
print()
print('LOA sample',list(loa.items())[:15])
print()
print('other cell kinds:',[k for k,_ in cells.most_common(40)])
# overlap with grid
B=json.load(open('raw_bookings.json'))
grid=collections.Counter()
for b in B:
    if re.match(PREF+r"\b", b['label'], re.I):
        grid[re.sub(r"\s+",' ',b['label']).upper()]+=1
print()
print('grid vessel-like distinct:',len(grid))
reg=set(loa)|{k.upper() for k in vnames}
inter=set(grid)&reg
print('overlap:',len(inter)); print(sorted(inter)[:20])
json.dump({'reg_vessels':dict(vnames),'loa':loa},open('registry_probe.json','w'))
