# Berth — dock scheduling for Harborview Marine Research Center

A scheduling system that treats every berth as **linear feet of quay**, not a row in a grid.
It ships with 23 years of bookings (Aug 1997 – Dec 2019) imported from the facility's
spreadsheet, plus an audit of everything the import found wrong with it.

**Live demo:** `https://<your-username>.github.io/berth/`, once GitHub Pages is on (see below).

---

## Try it in 60 seconds

1. **The day board** across the top: alongside now, arriving and departing in the next week.
2. **Quay:** the whole waterfront drawn to one scale, feet down the page and days across it.
   North Pier West really is seven times the depth of the Inner Channel. On the opening view three
   vessels lie alongside the 410&prime; pier at once — 145&prime;, 120&prime; and 100&prime;, using 402 of its 410 feet.
   Use ← → to change month, or **Jump to…** for any year back to 1997.
3. **New reservation** (or press `N`), or click any patch of open water in a berth lane. Give it a
   vessel and dates and it answers for *every* berth at once — fits, too short, closed, taken, or
   no size check — with the free feet on each. Pick from what works.
4. **Hatched blocks** are vessels with no recorded length. The system won't guess, so it holds the
   whole berth. Click one and choose **Record length**: every stay that vessel ever had redraws as a
   real hull, and others can then berth alongside it.
5. **Fleet** ranks the vessels to measure first by how much of the record each one unlocks.
6. **Import audit** lists what 23 years of the grid got wrong.

Two sets of bookings are loaded. The **example season** around today is invented so the waterfront
isn't empty — though every length in it is real, taken from the register tabs — and the switch in the
toolbar turns it off. Behind it is the **imported archive**, 1997–2019, which is the real thing.

Anything you book or measure is saved in your own browser (localStorage). Nobody else sees it.

---

## What the import found

| Finding | Number |
|---|---|
| Grid entries reconstructed | 2,473 → 2,244 reservations |
| Distinct vessels in the schedule | 486 (20 have a length on the register) |
| Berth-time that can be checked for fit | **~2%** |
| Checkable vessels put in a berth shorter than the vessel | **6 of 20** |
| Entries written into unlabelled spacer rows (no berth) | 252 |
| Stays split in two at month boundaries | 229 |
| Vessels spelled two ways (`Barge SALT DORY` / `Barge Salt Dory`) | 28 |
| Grid cells that are notes, not bookings (`ETA 1200`, `Fuel truck`) | 117 |
| Share of all berth-time taken by just 5 vessels, none with a recorded length | 52% |

## Design decisions

- **Continuous berth allocation.** A reservation holds a range of feet for a range of days, and
  a conflict is two such rectangles overlapping. Two vessels on a 410′ pier at the same time is fine
  if they fit side by side.
- **10% clearance.** Each vessel reserves its LOA + 10% (minimum 8 ft), half on each side. This
  follows the rule of thumb that a berth should be about 10% longer than the vessel lying at it.
- **First-fit placement.** Earliest arrival is placed first, as far shoreward as it will go. A
  vessel keeps one position for its whole stay; nothing gets moved along the quay to fit a later
  arrival.
- **Unknown is not the same as fine.** A vessel with no recorded length holds the whole berth.
  The system never shows a green check it can't back up.
- **Closures take priority.** A berth closed for repair, crane work, etc. refuses any booking
  for those dates.
- **Notes aren't bookings.** They're drawn as small ticks and take up no space.

### Assumptions to confirm with the dock coordinator
- The spacer-row entries were overflow, not a hidden extra berth.
- "North Finger Piers" and "Small craft slips" are groups of slips with no measured length to
  check against.
- A vessel doesn't get shifted along the quay partway through its stay.

### Known limits
- Data is saved per browser. A real deployment needs a shared database and login.
- Imported bookings are read-only; only bookings made in the app, and the example season, can be cancelled.
- Draft and water depth aren't checked yet. Only 4 vessels have a recorded draft.

---

## Tests

```bash
npm install                      # playwright, for the browser tests
npx playwright install chromium
npm test                         # 30 engine + 36 browser tests
```

`tests/engine.test.mjs` runs the scheduling maths headless: clearance, fit, first-fit placement,
several vessels alongside one pier, unknown lengths, closures, events, slip groups, date edges, and
invariants over the shipped data — including that the system never accepts a booking it would then
flag as a conflict.

`tests/browser.test.mjs` drives the real page: the availability board, confirming and persisting a
booking, refusing one that doesn't fit, recording a length, the archive, the day board, dark mode,
phone width, a first-time visitor, and a browser with storage blocked. Any uncaught page error fails
the run.

## Repo layout

```
index.html              built app: open it directly, or serve it with GitHub Pages
build.py                assembles index.html (and dist-artifact.html) from src/ + data/seed.json
tests/                  engine and browser test suites
src/                    app source (CSS/markup in head/body, engine in js.html, chart in chart.html …)
data/
  Dock_Schedule_-_Synthetic_Sample.xlsx   the source workbook (synthetic sample data)
  seed.json             compact import embedded in the app
etl/
  import_dock_schedule.py   standalone importer, one file
  gen_example.py            builds the example season; refuses to write a season with a clash
  run_pipeline.sh           rebuilds data/seed.json exactly
  extract.py normalize.py registry.py seed.py   pipeline steps
  regprobe.py conflicts.py infer.py overflow.py stats.py   analysis behind the audit numbers
```

## Develop

```bash
# run locally
python3 -m http.server 8000        # then open http://localhost:8000

# after editing anything in src/
python3 build.py

# re-import the workbook (needs: pip install openpyxl)
./etl/run_pipeline.sh && python3 build.py

# reproduce the audit numbers
cd etl && ./run_pipeline.sh && python3 regprobe.py && python3 conflicts.py && python3 infer.py && python3 overflow.py && python3 stats.py
```

The app itself has no dependencies and no build tools beyond Python's standard library.
