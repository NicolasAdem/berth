#!/usr/bin/env python3
"""
import_dock_schedule.py — read the Harborview dock-schedule workbook into
normalised reservations.

The workbook stores 23 years of bookings as painted calendar grids, one block
per month, one row per berth. A reservation is not a record: it is a run of
same-coloured cells with a vessel name in the first one. Layouts drift across
the years (the date row sits above the day-of-week row in 1997 and below it
from 2005; the first day starts in column B or C; month headings are
"AUGUST 1997", "JANUARY 2005" or just "January"), so nothing here is
hard-coded to a year — blocks are found by looking for a run of 1..28-31.

Usage:  python3 import_dock_schedule.py Dock_Schedule.xlsx -o seed.json
Needs:  pip install openpyxl
"""
import argparse, calendar, collections, datetime, json, re, sys
import openpyxl

PREFIX = r"(?:R/V|M/V|M/Y|S/V|S/Y|F/V|OS/V|OSV|Tug|Barge)"
MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_name) if m}
NEUTRAL = {"", "NONE", "00000000", "FFFFFFFF", "FFFFFF"}
DOW = {"M", "T", "W", "TR", "F", "S", "TH", "SU", "SA"}

# Entries that look like bookings but are working notes: they occupy a cell in
# a berth row while reserving nothing.
NOTE_RE = [r"^(eta|etd|arriv|depart|returns|delayed|touch and go)\b", r"^\w+ \d{3,4}$",
           r"^(fuel|bunker|provision|load|wire spool|water/slops)", r"^holiday$"]
CLOSURE_WORDS = ["repair", "closed", "maintenance", "rebuild", "no docking", "no usage",
                 "restricted", "inspection", "bollard", "utility work", "concrete",
                 "paving", "ultrasonic", "road race", "crane access"]
EVENT_WORDS = ["sail day", "open house", "reception", "tour", "stroll", "training",
               "drill", "film crew", "campus event", "regatta", "ceremony", "class"]


# ── cell helpers ──────────────────────────────────────────────────────────
def rgb(cell):
    f = cell.fill
    if not f or not f.patternType:
        return ""
    try:
        c = f.fgColor
        if c.type == "rgb" and isinstance(c.rgb, str):
            return c.rgb.upper()
        if c.type == "theme":
            return f"THEME{c.theme}:{round(c.tint, 3)}"
        if c.type == "indexed":
            return f"IDX{c.indexed}"
    except Exception:
        pass
    return ""


def painted(cell):
    return rgb(cell) not in NEUTRAL


def text(ws, wsv, r, c):
    v = wsv.cell(r, c).value
    if v is None:
        v = ws.cell(r, c).value
    if isinstance(v, str):
        v = v.replace("\n", " ").strip()
        return None if (not v or v.startswith("=")) else v
    return None


def number(ws, wsv, r, c):
    for src in (wsv, ws):
        v = src.cell(r, c).value
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
    return None


# ── find the month blocks in a year sheet ─────────────────────────────────
def month_blocks(ws, wsv, sheet_year, maxc):
    blocks = []
    for r in range(1, ws.max_row + 1):
        head = None
        for rr in (r, r - 1):
            if rr < 1:
                continue
            for cc in (1, 2):
                t = text(ws, wsv, rr, cc)
                if not t:
                    continue
                m = re.match(r"^([A-Za-z]+)\s*(\d{4})?$", t.strip())
                if m and m.group(1).upper() in MONTHS:
                    head = (MONTHS[m.group(1).upper()],
                            int(m.group(2)) if m.group(2) else sheet_year, rr)
                    break
            if head:
                break
        if not head:
            continue
        month, year, labrow = head
        ndays = calendar.monthrange(year, month)[1]
        found = None
        for dr in (r, r + 1, r + 2):                       # the date row moved over the years
            cols = {c: n for c in range(2, maxc + 1)
                    if (n := number(ws, wsv, dr, c)) is not None and 1 <= n <= 31}
            if len(cols) < 5:                              # 1997: dates are =SUM(prev+1) with no cache
                start = next((c for c in range(2, maxc + 1) if ws.cell(dr, c).value == 1), None)
                if start:
                    seq, d = {}, 1
                    for c in range(start, maxc + 1):
                        raw = ws.cell(dr, c).value
                        if raw is None or (isinstance(raw, str) and not raw.startswith("=")):
                            break
                        seq[c] = d
                        d += 1
                        if d > ndays + 1:
                            break
                    if len(seq) > len(cols):
                        cols = seq
            if len(cols) >= 20:
                run, expect = {}, 1
                for c, n in sorted(cols.items()):
                    if n == expect:
                        run[n] = c
                        expect += 1
                run = {d: c for d, c in run.items() if d <= ndays}
                if len(run) >= ndays - 1:
                    found = (dr, run)
                    break
        if found and (not blocks or blocks[-1]["daterow"] != found[0]):
            blocks.append(dict(month=month, year=year, daterow=found[0],
                               daycols=found[1], labrow=labrow))
    return blocks


def berth_rows(ws, wsv, blocks, i, daycols):
    """Rows under a month header, including the unlabelled spacer rows that
    bookings were written into when a berth row was already full."""
    b = blocks[i]
    start = b["daterow"] + 1
    end = min(blocks[i + 1]["labrow"] - 1 if i + 1 < len(blocks) else ws.max_row, start + 14)
    rows, probe = [], list(daycols.values())[:8]
    for r in range(start, end + 1):
        lab = text(ws, wsv, r, 1)
        if lab and lab.split()[0].upper() in MONTHS:
            break
        if not lab and sum(1 for c in probe if text(ws, wsv, r, c) in DOW) >= 5:
            continue                                        # day-of-week row
        rows.append((r, lab))
    return rows


BERTH_RE = re.compile(r"^(.*?)\s*-\s*(\d+)\s*'?\s*$")


def split_berth(lab):
    lab = (lab or "").strip().rstrip(":").strip()
    m = BERTH_RE.match(lab)
    return (m.group(1).strip(), int(m.group(2))) if m else (lab or None, None)


# ── classify and canonicalise labels ──────────────────────────────────────
def classify(label):
    low = label.strip().lower()
    if re.match(PREFIX + r"\b", label, re.I):
        return "vessel"
    if any(re.search(p, low) for p in NOTE_RE):
        return "note"
    if any(w in low for w in CLOSURE_WORDS):
        return "closure"
    if any(w in low for w in EVENT_WORDS):
        return "event"
    return "note"


def canon_vessel(label):
    """'Barge SALT DORY' and 'Barge Salt Dory' are one barge. OS/V is OSV."""
    s = re.sub(r"\s+", " ", label.strip())
    s = re.sub(r"^OS/V\b", "OSV", s, flags=re.I)
    m = re.match(r"^(" + PREFIX + r")\s+(.*)$", s, re.I)
    if not m:
        return s
    pre = m.group(1).upper()
    pre = {"OSV": "OSV", "TUG": "Tug", "BARGE": "Barge"}.get(pre, pre)
    rest = re.sub(r"\s*\d{2,3}\s*'\s*$", "", m.group(2)).strip()
    return pre + " " + " ".join(w.capitalize() for w in rest.split())


# ── the reader ────────────────────────────────────────────────────────────
def read_schedule(wb, wbv):
    out = []
    for sheet in [s for s in wb.sheetnames if re.fullmatch(r"\d{4}", s)]:
        ws, wsv = wb[sheet], wbv[sheet]
        maxc = min(ws.max_column, 60)
        merged = {}
        for rng in ws.merged_cells.ranges:                  # 2009+ merge multi-day stays
            for c in range(rng.min_col, rng.max_col + 1):
                merged[(rng.min_row, c)] = rng.max_col
        blocks = month_blocks(ws, wsv, int(sheet), maxc)
        for bi, blk in enumerate(blocks):
            ndays = calendar.monthrange(blk["year"], blk["month"])[1]
            cols = [blk["daycols"][d] for d in sorted(blk["daycols"])]
            col2day = {c: d for d, c in blk["daycols"].items()}
            berth = length = None
            for r, lab in berth_rows(ws, wsv, blocks, bi, blk["daycols"]):
                overflow = lab is None
                if lab:
                    berth, length = split_berth(lab)
                i = 0
                while i < len(cols):
                    c = cols[i]
                    cell, label = ws.cell(r, c), text(ws, wsv, r, c)
                    if not label:
                        if painted(cell):                   # paint with no owner: skip the run
                            col = rgb(cell)
                            while i < len(cols) and rgb(ws.cell(r, cols[i])) == col \
                                    and not text(ws, wsv, r, cols[i]):
                                i += 1
                            continue
                        i += 1
                        continue
                    end = c
                    if (r, c) in merged:
                        end = min(merged[(r, c)], cols[-1])
                    elif painted(cell):                     # run of one colour = one stay
                        col, j = rgb(cell), i + 1
                        while j < len(cols) and rgb(ws.cell(r, cols[j])) == col \
                                and not text(ws, wsv, r, cols[j]):
                            j += 1
                        end = cols[j - 1]
                    d1, d2 = col2day.get(c), min(col2day.get(end, col2day.get(c)), ndays)
                    if d1:
                        kind = classify(label)
                        out.append(dict(
                            kind=kind,
                            name=canon_vessel(label) if kind == "vessel" else re.sub(r"\s+", " ", label.strip()),
                            berth=berth, berth_len=length, overflow=overflow,
                            start=datetime.date(blk["year"], blk["month"], d1).isoformat(),
                            end=datetime.date(blk["year"], blk["month"], d2).isoformat(),
                            sheet=sheet, row=r, raw=label))
                    i = cols.index(end) + 1 if end in cols else i + 1
    return out


def stitch(recs):
    """A stay from 28 Jan to 5 Feb is two coloured runs on two month blocks
    with nothing connecting them. Put them back together."""
    recs.sort(key=lambda r: (r["berth"] or "", r["name"], r["start"]))
    out, joined = [], 0
    for r in recs:
        if out:
            p = out[-1]
            same = p["name"] == r["name"] and p["berth"] == r["berth"] and p["overflow"] == r["overflow"]
            gap = (datetime.date.fromisoformat(r["start"]) - datetime.date.fromisoformat(p["end"])).days
            if same and 0 <= gap <= 1:
                p["end"] = max(p["end"], r["end"])
                joined += 1
                continue
        out.append(dict(r))
    return out, joined


def read_register(wb):
    """The register tabs are free-form: names carry their length ("R/V High
    Drift 120'"), contacts bleed across columns and continuation rows."""
    vessels, current = {}, None
    for sheet in ("Science", "Yachts"):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        for r in range(1, ws.max_row + 1):
            cells = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
            for v in cells:
                if isinstance(v, str) and re.match(PREFIX + r"\b", v.strip(), re.I):
                    current = canon_vessel(v)
                    rec = vessels.setdefault(current, dict(name=current, loa=None, draft=None,
                                                           operator=None, contacts=[], emails=[]))
                    m = re.search(r"(\d{2,3})\s*'", v)
                    if m and not rec["loa"]:
                        rec["loa"] = int(m.group(1))
                    break
            if not current:
                continue
            rec = vessels[current]
            for v in cells:
                if not isinstance(v, str) or re.match(PREFIX + r"\b", v.strip(), re.I):
                    continue
                v = v.strip()
                if (m := re.search(r"LOA:\s*(\d{2,3})\s*'", v)):
                    rec["loa"] = rec["loa"] or int(m.group(1))
                    if (dm := re.search(r"Draft:\s*(\d{1,2})\s*'", v)):
                        rec["draft"] = int(dm.group(1))
                elif "@" in v and "." in v:
                    rec["emails"].append(v)
                elif re.match(r"^(Cell|Work|Ph|Tel)\s*[:#]", v, re.I) or v.startswith("Capt."):
                    rec["contacts"].append(v)
                elif re.search(r"(University|Institute|Agency|Partners|Trust|Charters|Group|"
                               r"School|Foundation|Offshore|Services|Academy)", v):
                    rec["operator"] = rec["operator"] or v
    return vessels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workbook")
    ap.add_argument("-o", "--out", default="seed.json")
    a = ap.parse_args()
    wb = openpyxl.load_workbook(a.workbook)                  # styles: the fills ARE the data
    wbv = openpyxl.load_workbook(a.workbook, data_only=True)  # cached formula results

    raw = read_schedule(wb, wbv)
    recs, joined = stitch(raw)
    register = read_register(wb)

    kinds = collections.Counter(r["kind"] for r in recs)
    fleet = {r["name"] for r in recs if r["kind"] == "vessel"}
    with_loa = {n for n in fleet if n.upper() in {k.upper() for k in register}}
    print(f"  {len(raw):>6} grid entries read", file=sys.stderr)
    print(f"  {joined:>6} stays stitched back across month boundaries", file=sys.stderr)
    print(f"  {len(recs):>6} reservations " +
          ", ".join(f"{v} {k}" for k, v in kinds.most_common()), file=sys.stderr)
    print(f"  {len(fleet):>6} distinct vessels, {len(with_loa)} with a length on the register",
          file=sys.stderr)
    print(f"  {sum(1 for r in recs if r['overflow']):>6} entries written into unlabelled spacer rows",
          file=sys.stderr)

    json.dump(dict(reservations=recs, register=list(register.values())),
              open(a.out, "w"), separators=(",", ":"))
    print(f"  wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
