/**
 * Engine tests — the scheduling maths, run without a browser.
 *
 * The app ships as one HTML file, so this pulls the engine script out of it
 * and runs it against a minimal DOM stub. If these pass, the placement, fit
 * and conflict rules are right; the browser tests cover the interface.
 *
 *     node tests/engine.test.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const seed = fs.readFileSync(path.join(ROOT, 'data', 'seed.json'), 'utf8');

// the engine is the first <script> block (src/js.html)
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const engineSrc = scripts.find(s => s.includes('function evaluate'));
if (!engineSrc) throw new Error('engine script not found in index.html');

const shim = `
  const document = { getElementById: () => ({ textContent: SEED_JSON }) };
  const localStorage = { getItem: () => null, setItem: () => {} };
`;
const factory = new Function('SEED_JSON', `${shim}\n${engineSrc}\n; return {
  clearanceFt, footprintFt, layout, conflictsIn, evaluate, availability,
  BERTHS, BERTH, LINEAR, VESSELS, VBYNAME, RES, DEMO, d2n, n2d, iso, loaOf, titleOf
};`);
const E = factory(seed);

/* ── tiny harness ──────────────────────────────────────────────────── */
let pass = 0, fail = 0;
const fails = [];
function t(name, fn) {
  try { fn(); pass++; }
  catch (e) { fail++; fails.push(`${name}\n      ${e.message}`); }
}
function eq(a, b, msg = '') {
  if (a !== b) throw new Error(`${msg} expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}
function ok(v, msg = '') { if (!v) throw new Error(msg || 'expected truthy'); }

const DAY = d => E.d2n(new Date(d + 'T00:00:00'));
const id = name => E.VBYNAME.get(name.toLowerCase())?.id;
const loaOfName = name => E.VBYNAME.get(name.toLowerCase())?.loa;

/* Build an isolated berth: swap RES for a controlled set, restore after. */
function withRes(list, fn) {
  const saved = E.RES.slice();
  E.RES.length = 0;
  list.forEach(r => E.RES.push(r));
  try { return fn(); } finally { E.RES.length = 0; saved.forEach(r => E.RES.push(r)); }
}
let uid = 0;
const stay = (berth, vesselName, from, to) => ({
  id: 'x' + (++uid), kind: 'vessel', vid: id(vesselName), berth,
  s: DAY(from), e: DAY(to), label: null, unplaced: false, src: 'test'
});
const other = (kind, berth, label, from, to) => ({
  id: 'x' + (++uid), kind, vid: null, berth, s: DAY(from), e: DAY(to),
  label, unplaced: false, src: 'test'
});

/* ── clearance ─────────────────────────────────────────────────────── */
t('clearance is 10% of LOA', () => {
  eq(E.clearanceFt(100), 10);
  eq(E.clearanceFt(145), 15);   // rounds
  eq(E.footprintFt(120), 132);
});
t('clearance never drops below 8 ft', () => {
  eq(E.clearanceFt(24), 8);
  eq(E.clearanceFt(40), 8);     // 4 would be too tight
  eq(E.footprintFt(24), 32);
});

/* ── the berths are the ones the workbook describes ────────────────── */
t('berth lengths match the workbook', () => {
  eq(E.BERTH.npw.len, 410); eq(E.BERTH.npe.len, 240); eq(E.BERTH.npf.len, 75);
  eq(E.BERTH.inc.len, 55); eq(E.BERTH.sfw.len, 90); eq(E.BERTH.sfe.len, 90);
  eq(E.LINEAR.reduce((t2, b) => t2 + b.len, 0), 960);
});

/* ── fit ───────────────────────────────────────────────────────────── */
t('a vessel longer than the berth is refused', () => {
  const v = E.VESSELS.find(x => x.loa === 120);
  const r = withRes([], () => E.evaluate(
    { kind: 'vessel', berth: 'npf', loa: v.loa, s: DAY('2026-09-24'), e: DAY('2026-09-26') }, true));
  eq(r.status, 'blocked');
  ok(/longer than the berth/i.test(r.title), r.title);
});
t('a vessel that only fits without clearance is still refused', () => {
  // 85 ft hull + 9 ft clearance = 94 ft, and South Float East is 90 ft.
  const r = withRes([], () => E.evaluate(
    { kind: 'vessel', berth: 'sfe', loa: 85, s: DAY('2026-09-24'), e: DAY('2026-09-26') }, true));
  eq(r.status, 'blocked');
});
t('the largest vessel that does fit is accepted', () => {
  // 80 ft + 8 = 88 <= 90
  const r = withRes([], () => E.evaluate(
    { kind: 'vessel', berth: 'sfe', loa: 80, s: DAY('2026-09-24'), e: DAY('2026-09-26') }, true));
  eq(r.status, 'ok');
});

/* ── the whole point: several vessels alongside one pier ───────────── */
t('three vessels lie alongside a 410 ft pier at once', () => {
  const a = E.VESSELS.find(v => v.loa === 145), b = E.VESSELS.find(v => v.loa === 120),
        c = E.VESSELS.find(v => v.loa === 100);
  const list = [stay('npw', a.name, '2026-09-14', '2026-10-07'),
                stay('npw', b.name, '2026-09-19', '2026-09-30')];
  withRes(list, () => {
    const r = E.evaluate({ kind: 'vessel', berth: 'npw', loa: c.loa,
      s: DAY('2026-09-21'), e: DAY('2026-09-27') }, true);
    eq(r.status, 'ok', 'third vessel should fit: 160+132+110 = 402 of 410');
    eq(r.pos, 292, 'placed after the first two');
  });
});
t('a fourth vessel with no room left is refused, not silently stacked', () => {
  const a = E.VESSELS.find(v => v.loa === 145), b = E.VESSELS.find(v => v.loa === 120),
        c = E.VESSELS.filter(v => v.loa === 100)[1];
  const list = [stay('npw', a.name, '2026-09-14', '2026-10-07'),
                stay('npw', b.name, '2026-09-19', '2026-09-30'),
                stay('npw', c.name, '2026-09-21', '2026-09-27')];
  withRes(list, () => {
    const r = E.evaluate({ kind: 'vessel', berth: 'npw', loa: 40,
      s: DAY('2026-09-22'), e: DAY('2026-09-24') }, true);   // needs 48, only 8 left
    eq(r.status, 'conflict');
    ok(/no room/i.test(r.title), r.title);
  });
});
t('the free-space figure it reports is the real remaining gap', () => {
  const a = E.VESSELS.find(v => v.loa === 145);
  withRes([stay('npw', a.name, '2026-09-14', '2026-09-20')], () => {
    const av = E.availability({ kind: 'vessel', loa: 100, s: DAY('2026-09-15'), e: DAY('2026-09-18') });
    const npw = av.find(x => x.berth.id === 'npw');
    eq(npw.free, 410 - 160, '410 less the 145 ft vessel plus its clearance');
  });
});

/* ── unknown length ────────────────────────────────────────────────── */
t('a vessel with no recorded length holds the whole berth', () => {
  const r = withRes([], () => E.evaluate(
    { kind: 'vessel', berth: 'npw', loa: null, s: DAY('2026-09-24'), e: DAY('2026-09-26') }, true));
  eq(r.status, 'unverified');
  ok(/held whole/i.test(r.detail), r.detail);
});
t('nothing can be placed beside a vessel of unknown length', () => {
  const unknown = E.VESSELS.find(v => !v.loa && v.name.startsWith('R/V'));
  withRes([stay('npw', unknown.name, '2026-09-14', '2026-09-20')], () => {
    const r = E.evaluate({ kind: 'vessel', berth: 'npw', loa: 60,
      s: DAY('2026-09-16'), e: DAY('2026-09-18') }, true);
    eq(r.status, 'conflict', 'a 60 ft vessel must not be squeezed in beside an unmeasured one');
  });
});
t('an unknown length is never reported as a clean fit', () => {
  const r = withRes([], () => E.evaluate(
    { kind: 'vessel', berth: 'npw', loa: null, s: DAY('2026-09-24'), e: DAY('2026-09-26') }, true));
  ok(r.status !== 'ok', 'must not claim a fit it cannot verify');
});

/* ── dates ─────────────────────────────────────────────────────────── */
t('back-to-back stays do not clash', () => {
  const a = E.VESSELS.find(v => v.loa === 170);
  withRes([stay('npw', a.name, '2026-09-10', '2026-09-15')], () => {
    const r = E.evaluate({ kind: 'vessel', berth: 'npw', loa: 170,
      s: DAY('2026-09-16'), e: DAY('2026-09-20') }, true);
    eq(r.status, 'ok', 'the next vessel arrives the day after the last one left');
  });
});
t('a same-day turnaround that does not fit is caught', () => {
  const a = E.VESSELS.find(v => v.loa === 170);   // 187 ft of a 240 ft berth
  withRes([stay('npe', a.name, '2026-09-10', '2026-09-15')], () => {
    const r = E.evaluate({ kind: 'vessel', berth: 'npe', loa: 100,
      s: DAY('2026-09-15'), e: DAY('2026-09-18') }, true);  // needs 110, 53 left
    eq(r.status, 'conflict', 'both are alongside on the 15th');
  });
});
t('an end date before the start date is refused', () => {
  const r = withRes([], () => E.evaluate(
    { kind: 'vessel', berth: 'npw', loa: 60, s: DAY('2026-09-20'), e: DAY('2026-09-18') }, true));
  eq(r.status, 'blocked');
});
t('a one-day booking works', () => {
  const r = withRes([], () => E.evaluate(
    { kind: 'vessel', berth: 'npw', loa: 60, s: DAY('2026-09-20'), e: DAY('2026-09-20') }, true));
  eq(r.status, 'ok');
});

/* ── closures and events ───────────────────────────────────────────── */
t('a closure blocks the berth outright', () => {
  withRes([other('closure', 'sfw', 'Deck resurfacing', '2026-10-01', '2026-10-09')], () => {
    const r = E.evaluate({ kind: 'vessel', berth: 'sfw', loa: 40,
      s: DAY('2026-10-03'), e: DAY('2026-10-05') }, true);
    eq(r.status, 'blocked');
    ok(/closed/i.test(r.title), r.title);
  });
});
t('a closure outside the dates does not block', () => {
  withRes([other('closure', 'sfw', 'Deck resurfacing', '2026-10-01', '2026-10-09')], () => {
    const r = E.evaluate({ kind: 'vessel', berth: 'sfw', loa: 40,
      s: DAY('2026-10-10'), e: DAY('2026-10-12') }, true);
    eq(r.status, 'ok');
  });
});
t('an event occupies the berth like a vessel does', () => {
  withRes([other('event', 'sfe', 'Community sail day', '2026-09-26', '2026-09-26')], () => {
    const r = E.evaluate({ kind: 'vessel', berth: 'sfe', loa: 60,
      s: DAY('2026-09-26'), e: DAY('2026-09-28') }, true);
    eq(r.status, 'conflict', 'a sail day holds the berth');
  });
});
t('a closure can be booked over an existing stay — facilities wins', () => {
  const a = E.VESSELS.find(v => v.loa === 65);
  withRes([stay('sfw', a.name, '2026-10-02', '2026-10-06')], () => {
    const r = E.evaluate({ kind: 'closure', berth: 'sfw', label: 'Rebuild',
      s: DAY('2026-10-01'), e: DAY('2026-10-09') }, true);
    ok(r.status !== 'blocked', 'a closure is allowed to land on bookings; the clash is then flagged');
  });
});

/* ── slip groups ───────────────────────────────────────────────────── */
t('slip groups are tracked but not fit-checked', () => {
  const r = withRes([], () => E.evaluate(
    { kind: 'vessel', berth: 'scs', loa: null, s: DAY('2026-09-24'), e: DAY('2026-09-26') }, true));
  eq(r.status, 'unverified', 'a slip group can never report a checked fit');
  eq(r.reason, 'slips');
  ok(/no length or fit is checked/i.test(r.detail), r.detail);
});

/* ── availability board ────────────────────────────────────────────── */
t('a measured berth that fits always outranks a slip group', () => {
  withRes([], () => {
    const av = E.availability({ kind: 'vessel', loa: 145, s: DAY('2027-07-06'), e: DAY('2027-07-09') });
    eq(av[0].berth.type, 'linear', 'a 145 ft vessel must not be offered the finger piers first');
    eq(av[0].verdict.status, 'ok');
  });
});
t('availability answers for every berth, workable ones first', () => {
  withRes([], () => {
    const av = E.availability({ kind: 'vessel', loa: 120, s: DAY('2026-09-24'), e: DAY('2026-09-26') });
    eq(av.length, E.BERTHS.filter(b => b.type !== 'none').length);
    const ranks = av.map(a => a.verdict.status === 'ok' ? 0 : 1);
    eq(ranks.join(''), ranks.slice().sort().join(''), 'sorted best-first');
    eq(av.find(x => x.berth.id === 'npf').verdict.status, 'blocked', '120 ft cannot use a 75 ft berth');
    eq(av.find(x => x.berth.id === 'npw').verdict.status, 'ok');
  });
});
t('availability does not recurse forever when a berth is blocked', () => {
  withRes([other('closure', 'npw', 'Closed', '2026-09-20', '2026-09-30')], () => {
    const av = E.availability({ kind: 'vessel', loa: 120, s: DAY('2026-09-24'), e: DAY('2026-09-26') });
    ok(av.length > 0);
  });
});

/* ── invariants over the shipped data ──────────────────────────────── */
t('the example season contains no accidental clash', () => {
  // Exactly one conflict is seeded on purpose: a closure dropped on top of
  // existing bookings. Everything else must be clean.
  const demoOnly = E.DEMO.slice();
  const conflicts = withRes(demoOnly, () => {
    let out = [];
    for (const b of E.BERTHS) {
      if (b.type === 'none') continue;
      const items = E.layout(b.id, demoOnly.filter(r => r.berth === b.id).map(r => ({ ...r })));
      out = out.concat(E.conflictsIn(b.id, items));
    }
    return out;
  });
  const closureClashes = conflicts.filter(c => c.type === 'closed');
  const closedSpans = demoOnly.filter(r => r.kind === 'closure');
  const underClosure = c => closedSpans.some(k =>
    k.berth === c.berth && k.s <= c.a.e && k.e >= c.a.s);
  // a vessel that cannot be placed because a closure landed on it is part of
  // that same deliberate clash, not a separate mistake
  const accidental = conflicts.filter(c => c.type !== 'closed' && !underClosure(c));
  ok(closureClashes.length >= 1, 'the deliberate closure clash should be present');
  eq(accidental.length, 0, 'no unintended overlap, oversize or no-room in the example season: ' +
     accidental.map(c => `${c.type} ${E.titleOf(c.a)}`).join('; '));
});
t('every example vessel booking is one the system would itself allow', () => {
  // Replay the season: each booking, checked against everything already
  // placed, must come back ok or unverified — never conflict or blocked.
  const placed = [];
  const bad = [];
  for (const r of E.DEMO.filter(x => x.kind === 'vessel').sort((a, b) => a.s - b.s)) {
    const v = E.evaluate({ kind: 'vessel', berth: r.berth, loa: E.loaOf(r), s: r.s, e: r.e, id: r.id },
      true, placed);
    withRes(placed, () => {
      const res = E.evaluate({ kind: 'vessel', berth: r.berth, loa: E.loaOf(r), s: r.s, e: r.e, id: r.id }, true);
      if (res.status === 'conflict' || res.status === 'blocked')
        bad.push(`${E.titleOf(r)} on ${r.berth}: ${res.title}`);
    });
    placed.push(r);
  }
  eq(bad.length, 0, bad.join('; '));
});
t('the imported archive still reports its known conflicts', () => {
  const imported = E.RES.filter(r => r.src === 'import');
  let out = [];
  withRes(imported, () => {
    for (const b of E.BERTHS) {
      if (b.type === 'none') continue;
      const items = E.layout(b.id, imported.filter(r => r.berth === b.id).map(r => ({ ...r })));
      out = out.concat(E.conflictsIn(b.id, items));
    }
  });
  const pairs = out.filter(c => c.b).length;
  const over = out.filter(c => c.type === 'oversize').length;
  ok(pairs >= 5, `expected the historic overlaps, found ${pairs}`);
  ok(over >= 7, `expected the oversize assignments, found ${over}`);
});
t('placement is deterministic', () => {
  const run = () => withRes(E.DEMO.slice(), () =>
    E.layout('npw', E.DEMO.filter(r => r.berth === 'npw').map(r => ({ ...r })))
      .map(x => `${x.id}:${x.y0}-${x.y1}`).join('|'));
  eq(run(), run());
});
t('a vessel keeps one position for its whole stay', () => {
  const a = E.VESSELS.find(v => v.loa === 100);
  const list = [stay('npw', a.name, '2026-09-10', '2026-09-30')];
  withRes(list, () => {
    const laid = E.layout('npw', list.map(r => ({ ...r })));
    eq(laid[0].y0, 0);
    eq(laid[0].y1, 110);
  });
});
t('no reservation is ever placed past the end of its berth', () => {
  for (const b of E.BERTHS) {
    if (b.type !== 'linear') continue;
    const items = E.layout(b.id, E.RES.filter(r => r.berth === b.id).map(r => ({ ...r })));
    for (const it of items) {
      if (it.note) continue;
      ok(it.y0 >= 0, `${E.titleOf(it)} placed before the start of ${b.name}`);
      ok(it.y1 <= b.len + 0.001 || it.oversize || it.noroom,
        `${E.titleOf(it)} runs past the end of ${b.name} without being flagged`);
    }
  }
});

/* ── report ────────────────────────────────────────────────────────── */
console.log(`\n  engine: ${pass} passed, ${fail} failed`);
if (fail) { console.log('\n  FAILURES:'); fails.forEach(f => console.log('    ✗ ' + f)); process.exit(1); }
