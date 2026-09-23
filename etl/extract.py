import openpyxl, re, json, calendar, datetime, unicodedata
from collections import defaultdict, Counter
from openpyxl.utils import get_column_letter as gl

import os; P=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data','Dock_Schedule_-_Synthetic_Sample.xlsx')
wb  = openpyxl.load_workbook(P)             # styles + formulas
wbv = openpyxl.load_workbook(P, data_only=True)  # cached values

MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_name) if m}
NEUTRAL = {'', 'NONE', '00000000', 'FFFFFFFF', 'FFFFFF'}

def rgb(cell):
    f = cell.fill
    if not f or not f.patternType: return ''
    try:
        v = f.fgColor
        if v.type == 'rgb' and isinstance(v.rgb, str): return v.rgb.upper()
        if v.type == 'theme': return f'THEME{v.theme}:{round(v.tint,3)}'
        if v.type == 'indexed': return f'IDX{v.indexed}'
    except Exception: pass
    return ''

def is_paint(c):
    return rgb(c) not in NEUTRAL

def txt(ws, wsv, r, c):
    v = wsv.cell(r, c).value
    if v is None: v = ws.cell(r, c).value
    if isinstance(v, str):
        v = v.replace('\n', ' ').strip()
        if v.startswith('='): return None
        return v or None
    return None

def numval(ws, wsv, r, c):
    v = wsv.cell(r, c).value
    if isinstance(v, (int, float)) and not isinstance(v, bool): return int(v)
    v = ws.cell(r, c).value
    if isinstance(v, (int, float)) and not isinstance(v, bool): return int(v)
    return None

# ---------- locate month blocks ----------
def find_month_blocks(ws, wsv, sheetyear):
    """Return list of dicts: month,year,daterow,daycols{day:col},body_start"""
    blocks = []
    maxr, maxc = ws.max_row, min(ws.max_column, 60)
    for r in range(1, maxr + 1):
        # header text anywhere in col A..B of this row or the row above/below
        label = None
        for rr in (r, r - 1):
            if rr < 1: continue
            for cc in (1, 2):
                t = txt(ws, wsv, rr, cc)
                if not t: continue
                m = re.match(r'^([A-Za-z]+)\s*(\d{4})?$', t.strip())
                if m and m.group(1).upper() in MONTHS:
                    label = (MONTHS[m.group(1).upper()], int(m.group(2)) if m.group(2) else sheetyear, rr)
                    break
            if label: break
        if not label: continue
        month, year, labrow = label
        # find the date row: this row or next 2 rows containing a run of 1,2,3...
        best = None
        for dr in (r, r + 1, r + 2):
            cols = {}
            for c in range(2, maxc + 1):
                n = numval(ws, wsv, dr, c)
                if n is not None and 1 <= n <= 31: cols[c] = n
            # also handle formula date rows (=SUM(prev+1)) with no cache: seed from a literal 1
            if len(cols) < 5:
                startc = None
                for c in range(2, maxc + 1):
                    raw = ws.cell(dr, c).value
                    if raw == 1: startc = c; break
                if startc:
                    seq = {}
                    d = 1
                    for c in range(startc, maxc + 1):
                        raw = ws.cell(dr, c).value
                        if raw is None: break
                        if isinstance(raw, str) and not raw.startswith('='): break
                        seq[c] = d; d += 1
                        if d > calendar.monthrange(year, month)[1] + 1: break
                    if len(seq) > len(cols): cols = seq
            if len(cols) >= 20:
                # trim to a strictly increasing run starting at 1
                items = sorted(cols.items())
                run, expect = {}, 1
                for c, n in items:
                    if n == expect: run[n] = c; expect += 1
                ndays = calendar.monthrange(year, month)[1]
                run = {d: c for d, c in run.items() if d <= ndays}
                if len(run) >= ndays - 1:
                    best = (dr, run); break
        if not best: continue
        daterow, daycols = best
        if blocks and blocks[-1]['daterow'] == daterow: continue
        blocks.append(dict(month=month, year=year, daterow=daterow, daycols=daycols, labrow=labrow))
    return blocks

# ---------- berth rows for a block ----------
def block_rows(ws, wsv, blocks, i):
    b = blocks[i]
    start = b['daterow'] + 1
    end = (blocks[i + 1]['labrow'] - 1) if i + 1 < len(blocks) else ws.max_row
    end = min(end, start + 14)
    rows = []
    last_label = None
    for r in range(start, end + 1):
        lab = txt(ws, wsv, r, 1)
        if lab and re.match(r'^[A-Za-z]+\s*\d{0,4}$', lab.strip()) and lab.split()[0].upper() in MONTHS:
            break
        # skip the day-of-week row
        vals = [txt(ws, wsv, r, c) for c in list(b['daycols'].values())[:8]]
        dow = sum(1 for v in vals if v in ('M','T','W','TR','F','S','TH','SU','SA'))
        if dow >= 5 and not lab: continue
        rows.append((r, lab))
    return rows

BERTH_RE = re.compile(r"^(.*?)\s*-\s*(\d+)\s*'?\s*$")

def norm_berth(lab):
    if not lab: return None, None
    lab = lab.strip().rstrip(':').strip()
    m = BERTH_RE.match(lab)
    if m: return m.group(1).strip(), int(m.group(2))
    return lab, None

# ---------- main extraction ----------
bookings = []
anomalies = []
sheetyears = [s for s in wb.sheetnames if re.fullmatch(r'\d{4}', s)]

for sy in sheetyears:
    ws, wsv = wb[sy], wbv[sy]
    year = int(sy)
    blocks = find_month_blocks(ws, wsv, year)
    merged = {}
    for rng in ws.merged_cells.ranges:
        for c in range(rng.min_col, rng.max_col + 1):
            merged[(rng.min_row, c)] = (rng.min_col, rng.max_col)
    for bi, b in enumerate(blocks):
        ndays = calendar.monthrange(b['year'], b['month'])[1]
        col2day = {c: d for d, c in b['daycols'].items()}
        cols = [b['daycols'][d] for d in sorted(b['daycols'])]
        rows = block_rows(ws, wsv, blocks, bi)
        current_berth, current_len = None, None
        for (r, lab) in rows:
            if lab:
                nb, nl = norm_berth(lab)
                current_berth, current_len = nb, nl
                overflow = False
            else:
                overflow = True
            # segment this row
            segs = []   # (startcol, endcol, label)
            c_i = 0
            while c_i < len(cols):
                c = cols[c_i]
                cell = ws.cell(r, c)
                label = txt(ws, wsv, r, c)
                painted = is_paint(cell)
                if not label and not painted:
                    c_i += 1; continue
                if not label and painted:
                    # painted continuation with no owner -> orphan paint, skip run
                    col = rgb(cell); j = c_i
                    while j < len(cols) and rgb(ws.cell(r, cols[j])) == col and not txt(ws, wsv, r, cols[j]):
                        j += 1
                    c_i = j; continue
                # label present -> determine extent
                endc = c
                if (r, c) in merged:
                    _, mx = merged[(r, c)]
                    endc = min(mx, cols[-1])
                elif painted:
                    col = rgb(cell); j = c_i + 1
                    while j < len(cols) and rgb(ws.cell(r, cols[j])) == col and not txt(ws, wsv, r, cols[j]):
                        j += 1
                    endc = cols[j - 1]
                segs.append((c, endc, label))
                c_i = cols.index(endc) + 1 if endc in cols else c_i + 1
            for (sc, ec, label) in segs:
                d1 = col2day.get(sc); d2 = col2day.get(ec, d1)
                if d1 is None: continue
                d2 = min(d2 or d1, ndays)
                bookings.append(dict(
                    year=b['year'], month=b['month'], d1=d1, d2=d2,
                    berth=current_berth, berth_len=current_len, overflow=overflow,
                    label=label, sheet=sy, row=r, fill=rgb(ws.cell(r, sc))))

print('raw bookings', len(bookings))
print('years', Counter(x['year'] for x in bookings))
print('berths', Counter((x['berth'], x['berth_len']) for x in bookings).most_common(20))
print('overflow rows', sum(1 for x in bookings if x['overflow']))
json.dump(bookings, open('raw_bookings.json','w'))
