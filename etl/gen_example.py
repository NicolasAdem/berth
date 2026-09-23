#!/usr/bin/env python3
"""
gen_example.py — build a worked example season for the demo.

The imported archive stops on 31 Dec 2019, so an app opened "today" shows an
empty waterfront. This writes a current-dated season into seed.json under a
separate `demo` key so it is never confused with imported data.

Nothing here invents a vessel length. Every measured vessel in the season is
one that already carries a real LOA on the workbook's own register tabs
(Science / Yachts); a few vessels with no recorded length are included on
purpose, because that is the normal state of the fleet and the app has to
show it. Only the bookings themselves are made up, and the app labels them.

    python3 gen_example.py              # rewrites data/seed.json in place
"""
import datetime as dt
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = os.path.join(HERE, "..", "data", "seed.json")
EPOCH = dt.date(1997, 1, 1)
TODAY = dt.date(2026, 9, 22)          # the season is built around this
SEASON_START = dt.date(2026, 5, 1)
SEASON_END = dt.date(2027, 3, 31)
RNG = random.Random(20260922)          # deterministic


def clearance(loa):
    return max(8, round(loa * 0.10))


def footprint(loa):
    return loa + clearance(loa)


def n(d):
    return (d - EPOCH).days


def check(res, vessels, berths):
    """Replay the season through the same placement rules the app uses and
    refuse to write anything but the one clash that is there on purpose.
    An example that quietly contains a double-booking teaches the wrong thing."""
    KINDS = ["vessel", "event", "closure", "note"]
    problems = []
    closed_spans = [(r[2], r[3], r[3] + r[4]) for r in res if KINDS[r[0]] == "closure"]
    for bid, b in berths.items():
        L = b.get("len")
        if not L:
            continue
        items = sorted([r for r in res if r[2] == bid and KINDS[r[0]] != "note"],
                       key=lambda r: (r[3], -(r[4])))
        placed = []
        for r in items:
            kind = KINDS[r[0]]
            s0, e0 = r[3], r[3] + r[4]
            loa = vessels[r[1]][1] if (kind == "vessel" and r[1] >= 0) else None
            if loa is None or kind == "closure":
                placed.append((s0, e0, 0, L, r))
                continue
            need = footprint(loa)
            if need > L:
                problems.append(f"{vessels[r[1]][0]} ({loa}') does not fit {b['name']} ({L}')")
                placed.append((s0, e0, 0, L, r))
                continue
            bars = sorted([(p[2], p[3]) for p in placed if p[0] <= e0 and p[1] >= s0])
            y, fitted = 0, False
            for a, c in bars:
                if a - y >= need:
                    fitted = True
                    break
                y = max(y, c)
            if not fitted and L - y >= need:
                fitted = True
            if not fitted:
                under_closure = any(cb == bid and cs <= e0 and ce >= s0
                                    for cb, cs, ce in closed_spans)
                if not under_closure:
                    who = vessels[r[1]][0] if r[1] >= 0 else r[5]
                    problems.append(f"no room for {who} on {b['name']} "
                                    f"({(EPOCH + dt.timedelta(days=s0)).isoformat()})")
                placed.append((s0, e0, 0, min(need, L), r))
            else:
                placed.append((s0, e0, y, y + need, r))
    return problems


def main():
    seed = json.load(open(SEED))
    vessels = seed["vessels"]                      # [name, loa, draft, op, contact, email, src]
    idx = {v[0]: i for i, v in enumerate(vessels)}
    berths = {b["id"]: b for b in seed["berths"]}

    # Vessels carrying a real length on the register, grouped by length.
    measured = {}
    for i, v in enumerate(vessels):
        if v[1] and v[6] in ("registry", "registry-only"):
            measured.setdefault(v[1], []).append(i)
    for k in measured:
        RNG.shuffle(measured[k])

    used = set()

    def pick(loa):
        """A register vessel of exactly this length, not already in the season."""
        for i in measured.get(loa, []):
            if i not in used:
                used.add(i)
                return i
        return None

    # A few regulars from the archive that have never had a length recorded —
    # the hatched blocks are the point, not an oversight.
    unmeasured = [idx[nm] for nm in
                  ("R/V Golden Compass", "OSV Amber Reef", "Barge Salt Dory")
                  if nm in idx]

    # Kind is stored as an index into the app's KINDS list, exactly as the
    # imported reservations are — the app reads both through the same path.
    KINDS = ["vessel", "event", "closure", "note"]

    res = []   # [kindIndex, vid, berth, startday, lengthdays, label, unplaced]

    def add(kind, vid, berth, start, days, label=""):
        res.append([KINDS.index(kind), vid if vid is not None else -1, berth,
                    n(start), days - 1, label, 0])

    # ── North Pier West, 410 ft ───────────────────────────────────────────
    # The demonstration of the whole idea: three vessels alongside at once.
    # 145' + 120' + 100' reserve 160 + 132 + 110 = 402 ft of a 410 ft pier.
    add("vessel", pick(145), "npw", dt.date(2026, 9, 14), 24)
    add("vessel", pick(120), "npw", dt.date(2026, 9, 19), 12)
    add("vessel", pick(100), "npw", dt.date(2026, 9, 21), 7)
    add("vessel", pick(170), "npw", dt.date(2026, 10, 12), 16)
    add("vessel", pick(120), "npw", dt.date(2026, 10, 20), 9)
    add("vessel", pick(85), "npw", dt.date(2026, 11, 2), 11)
    add("vessel", pick(145), "npw", dt.date(2026, 11, 16), 21)
    add("vessel", unmeasured[0] if unmeasured else None, "npw",
        dt.date(2026, 8, 3), 19)
    add("vessel", pick(120), "npw", dt.date(2026, 6, 8), 14)
    add("vessel", pick(100), "npw", dt.date(2026, 6, 15), 10)
    add("vessel", pick(145), "npw", dt.date(2026, 7, 6), 18)
    add("vessel", pick(72), "npw", dt.date(2026, 7, 13), 9)
    add("vessel", pick(170), "npw", dt.date(2027, 1, 11), 20)
    add("vessel", pick(120), "npw", dt.date(2027, 2, 8), 15)

    # ── North Pier East, 240 ft ───────────────────────────────────────────
    add("vessel", pick(120), "npe", dt.date(2026, 9, 8), 15)
    add("vessel", pick(85), "npe", dt.date(2026, 9, 17), 10)
    add("vessel", pick(100), "npe", dt.date(2026, 10, 5), 12)
    add("vessel", pick(72), "npe", dt.date(2026, 10, 9), 8)
    add("vessel", unmeasured[1] if len(unmeasured) > 1 else None, "npe",
        dt.date(2026, 11, 9), 16)
    add("vessel", pick(120), "npe", dt.date(2026, 12, 7), 13)
    add("vessel", pick(85), "npe", dt.date(2026, 6, 22), 11)
    add("vessel", pick(100), "npe", dt.date(2026, 7, 20), 14)
    add("vessel", pick(65), "npe", dt.date(2026, 8, 17), 9)
    add("vessel", pick(120), "npe", dt.date(2027, 1, 19), 12)
    add("vessel", pick(85), "npe", dt.date(2027, 3, 2), 10)

    # ── North Pier Face, 75 ft ────────────────────────────────────────────
    for start, days, loa in [((2026, 9, 24), 5, 65), ((2026, 10, 15), 6, 46),
                             ((2026, 11, 20), 4, 65), ((2026, 7, 2), 6, 52),
                             ((2027, 2, 16), 5, 46)]:
        add("vessel", pick(loa), "npf", dt.date(*start), days)

    # ── Inner Channel, 55 ft ─────────────────────────────────────────────
    for start, days, loa in [((2026, 9, 28), 7, 46), ((2026, 10, 26), 5, 40),
                             ((2026, 8, 10), 8, 46), ((2027, 3, 9), 6, 40)]:
        add("vessel", pick(loa), "inc", dt.date(*start), days)

    # ── South Float West, 90 ft ──────────────────────────────────────────
    add("vessel", pick(72), "sfw", dt.date(2026, 9, 11), 9)
    add("vessel", pick(65), "sfw", dt.date(2026, 10, 2), 11)
    add("vessel", pick(52), "sfw", dt.date(2026, 6, 29), 12)
    add("vessel", pick(72), "sfw", dt.date(2026, 8, 24), 8)
    add("vessel", pick(65), "sfw", dt.date(2027, 2, 22), 9)

    # ── South Float East, 90 ft ──────────────────────────────────────────
    add("vessel", pick(52), "sfe", dt.date(2026, 9, 16), 10)
    add("vessel", pick(72), "sfe", dt.date(2026, 10, 19), 7)
    add("vessel", unmeasured[2] if len(unmeasured) > 2 else None, "sfe",
        dt.date(2026, 12, 1), 14)
    add("vessel", pick(46), "sfe", dt.date(2026, 8, 3), 9)
    add("vessel", pick(65), "sfe", dt.date(2027, 1, 5), 11)

    # ── small craft ──────────────────────────────────────────────────────
    for start, days, loa in [((2026, 9, 7), 21, 32), ((2026, 10, 12), 18, 24),
                             ((2026, 6, 1), 30, 32), ((2027, 2, 2), 24, 24)]:
        add("vessel", pick(loa), "scs", dt.date(*start), days)

    # ── events: the waterfront's other job ───────────────────────────────
    # Community sail days run most summer Saturdays off South Float East.
    d = dt.date(2026, 6, 6)
    while d <= dt.date(2026, 9, 5):
        add("event", None, "sfe", d, 1, "Community sail day")
        d += dt.timedelta(days=14)
    add("event", None, "sfw", dt.date(2026, 9, 26), 1, "Public open house")
    add("event", None, "npf", dt.date(2026, 10, 3), 1, "Student tour")
    add("event", None, "sfw", dt.date(2026, 10, 24), 2, "Donor reception")
    add("event", None, "sfe", dt.date(2026, 11, 7), 1, "Rescue drill")
    add("event", None, "npf", dt.date(2027, 3, 20), 1, "Science stroll")

    # ── closures ─────────────────────────────────────────────────────────
    add("closure", None, "inc", dt.date(2026, 11, 2), 12,
        "Bollard replacement - no docking")
    add("closure", None, "npf", dt.date(2027, 1, 12), 18,
        "Float rebuild - no usage permitted")
    # The one live conflict in the season, and a realistic one: facilities
    # scheduled a rebuild across South Float West after the bookings above
    # were already taken. The system flags it; a coordinator has to move
    # someone. Bookings are never allowed to create a clash — only a closure
    # dropped on top of existing bookings can.
    add("closure", None, "sfw", dt.date(2026, 10, 1), 9,
        "Deck resurfacing - berth closed")

    # ── notes: the things that were cluttering the old grid ──────────────
    add("note", None, "npw", dt.date(2026, 9, 19), 1, "ETA 1200")
    add("note", None, "npe", dt.date(2026, 9, 17), 1, "Bunkering 1000")
    add("note", None, "npw", dt.date(2026, 10, 12), 1, "Arrives AM")

    res = [r for r in res if r[1] != -1 or r[0] != KINDS.index("vessel")]
    res.sort(key=lambda r: r[3])
    seed["demo"] = res
    seed["demo_meta"] = {
        "today": TODAY.isoformat(),
        "from": SEASON_START.isoformat(),
        "to": SEASON_END.isoformat(),
    }
    problems = check(res, vessels, berths)
    if problems:
        raise SystemExit("example season is not clean:\n  " + "\n  ".join(problems))

    json.dump(seed, open(SEED, "w"), separators=(",", ":"))

    kinds = {}
    for r in res:
        kinds[KINDS[r[0]]] = kinds.get(KINDS[r[0]], 0) + 1
    named = sum(1 for r in res if r[1] >= 0 and vessels[r[1]][1])
    print(f"  {len(res)} example reservations "
          + ", ".join(f"{v} {k}" for k, v in sorted(kinds.items())))
    print(f"  {named} use a vessel with a real recorded length; "
          f"{sum(1 for r in res if r[1] >= 0 and not vessels[r[1]][1])} deliberately have none")
    print(f"  season {SEASON_START} .. {SEASON_END}")


if __name__ == "__main__":
    main()
