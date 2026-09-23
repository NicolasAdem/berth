/**
 * Browser tests — every flow a coordinator actually uses.
 *
 *     npx playwright install chromium     (once)
 *     node tests/browser.test.mjs
 *
 * Serves the repo on a local port and drives the real page. Any uncaught
 * page error at any point fails the run.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const PORT = 8791;
const TYPES = { '.html': 'text/html', '.json': 'application/json', '.js': 'text/javascript' };

const server = http.createServer((req, res) => {
  const f = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]) === '/' ? '/index.html' : req.url.split('?')[0]);
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(PORT, r));
const URL_ = `http://127.0.0.1:${PORT}/index.html`;

let pass = 0, fail = 0; const fails = [];
let current = null;                 // page under test, for cleanup
async function t(name, fn) {
  try { await fn(); pass++; process.stdout.write('.'); }
  catch (e) { fail++; fails.push(`${name}\n      ${e.message.split('\n')[0]}`); process.stdout.write('x'); }
  finally {
    // a failed test must not leave a modal open and fail every test after it
    try {
      if (current && !current.isClosed()) {
        await current.evaluate(() => {
          const d = document.getElementById('drawerhost'); if (d) d.innerHTML = '';
          const q = document.getElementById('pophost'); if (q) q.innerHTML = '';
        });
      }
    } catch {}
  }
}
const ok = (v, m = 'expected truthy') => { if (!v) throw new Error(m); };
const eq = (a, b, m = '') => { if (a !== b) throw new Error(`${m} expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); };

// PW_CHROMIUM lets a sandbox point at a pre-installed browser; normally
// `npx playwright install chromium` puts one where Playwright expects it.
const browser = await chromium.launch({
  ...(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {}),
  args: ['--disable-background-networking', '--no-first-run', '--no-default-browser-check',
         '--disable-component-update', '--disable-sync']
});
const errors = [];

async function newPage(opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 1000 }, ...opts });
  // the page must work without its webfonts; blocking them also keeps the
  // suite offline and fast
  await ctx.route('**/*', r => r.request().url().includes('127.0.0.1') ? r.continue() : r.abort());
  const p = await ctx.newPage();
  p.on('pageerror', e => errors.push(`${opts.tag || 'page'}: ${e.message}`));
  p.on('console', m => {
    if (m.type() !== 'error') return;
    // font and other third-party fetches are not app errors; local ones are
    const where = m.location()?.url || '';
    if (/fonts\.(googleapis|gstatic)/.test(where) || /Failed to load resource/.test(m.text()) && !where.includes('127.0.0.1')) return;
    errors.push('console: ' + m.text() + ' @ ' + where);
  });
  p.on('response', r => { if (r.status() >= 400 && r.url().includes('127.0.0.1')) errors.push('http ' + r.status() + ' ' + r.url()); });
  await p.goto(URL_);
  await p.waitForSelector('#chart svg, #chart', { timeout: 10000 });
  await p.waitForTimeout(600);
  current = p;
  return p;
}

/* ── first load ────────────────────────────────────────────────────── */
let p = await newPage();

await t('the waterfront is not empty on first load', async () => {
  const blocks = await p.$$eval('#chart .blk', n => n.length);
  ok(blocks > 5, `only ${blocks} blocks drawn`);
});
await t('it opens on the current month', async () => {
  const now = new Date();
  const label = await p.textContent('#monthlabel');
  ok(label.includes(String(now.getFullYear())), `opened on ${label}`);
});
await t('the day board reports real counts', async () => {
  const txt = await p.$$eval('#dayboard h4 b', n => n.map(x => +x.textContent));
  eq(txt.length, 3);
  ok(txt[0] > 0, 'nothing shown alongside now');
});
await t('vessels with a length render as measured hulls, not held berths', async () => {
  const solid = await p.$$eval('#chart .blk rect',
    n => n.filter(r => (r.getAttribute('style') || '').includes('hull-fill')).length);
  ok(solid > 3, `only ${solid} measured hulls drawn — lengths are not reaching the chart`);
});
await t('the scale runs to the real berth lengths', async () => {
  const txt = await p.textContent('#chart');
  for (const ft of ['410′', '240′', '75′', '55′', '90′']) ok(txt.includes(ft), `missing ${ft} label`);
});
await t('three vessels are shown alongside the 410 ft pier', async () => {
  // the seeded demonstration: distinct hulls stacked down one lane on one day
  const n = await p.$$eval('#chart .blk rect', rs => {
    const solid = rs.filter(r => (r.getAttribute('style') || '').includes('hull-fill'));
    const top = solid.filter(r => +r.getAttribute('y') < 260);
    return new Set(top.map(r => r.getAttribute('y'))).size;
  });
  ok(n >= 3, `expected several hulls stacked on North Pier West, saw ${n}`);
});

/* ── booking, availability first ───────────────────────────────────── */
// each test opens its own drawer, so one failure cannot cascade
async function openBooking({ vessel, loa, kind, label, from, to }) {
  await p.click('#newres');
  await p.waitForSelector('.drawer');
  if (kind) await p.selectOption('#f-kind', kind);
  if (vessel) await p.fill('#f-vessel', vessel);
  if (label) await p.fill('#f-label', label);
  await p.fill('#f-s', from); await p.fill('#f-e', to);
  if (loa) await p.fill('#f-loa', String(loa));
  await p.waitForTimeout(400);
}
const availRows = () => p.$$eval('.availrow', rs => rs.map(r => ({
  name: r.querySelector('.ab-name').textContent.trim(),
  free: r.querySelector('.ab-free').textContent.trim(),
  chip: r.querySelector('.chip').textContent.trim(),
  on: r.classList.contains('on')
})));

await t('the booking drawer lists every berth with a verdict', async () => {
  await openBooking({ vessel: 'M/V Iron Sound', from: '2027-07-06', to: '2027-07-10' });
  const rows = await availRows();
  eq(rows.length, 8, 'six measured berths plus the two slip groups');
  ok(rows.every(r => r.chip.length > 0), 'every berth must carry a verdict');
});
await t('berths too short for the vessel are marked, not hidden', async () => {
  await openBooking({ vessel: 'M/V Iron Sound', from: '2027-07-06', to: '2027-07-10' });
  const rows = await availRows();
  eq(rows.find(r => r.name.includes('North Pier Face')).chip, 'Too short',
     'a 145 ft vessel must be refused by the 75 ft berth');
});
await t('workable berths are offered first and one is preselected', async () => {
  await openBooking({ vessel: 'M/V Iron Sound', from: '2027-07-06', to: '2027-07-10' });
  const rows = await availRows();
  eq(rows[0].chip, 'Fits');
  ok(rows[0].on, 'the first workable berth should be selected');
});
await t('free feet are reported for measured berths', async () => {
  await openBooking({ vessel: 'M/V Iron Sound', from: '2027-07-06', to: '2027-07-10' });
  const rows = await availRows();
  ok(/^\d+′ free$/.test(rows[0].free), `got "${rows[0].free}"`);
});
await t('a measured berth is chosen over a slip group by default', async () => {
  // regression: a 145 ft vessel was once defaulted into the small-craft slips
  await openBooking({ vessel: 'M/V Iron Sound', from: '2027-08-03', to: '2027-08-06' });
  const rows = await availRows();
  ok(!/slips|Finger/i.test(rows[0].name), `offered ${rows[0].name} first`);
  ok(rows[0].on);
});
await t('a slip group never claims a checked fit', async () => {
  await openBooking({ vessel: 'M/V Iron Sound', from: '2027-08-03', to: '2027-08-06' });
  const rows = await availRows();
  for (const r of rows.filter(x => /slips|Finger/i.test(x.name)))
    eq(r.chip, 'No size check', r.name);
});
await t('a confirmed booking is stored and survives a reload', async () => {
  await openBooking({ vessel: 'M/V Iron Sound', from: '2027-07-06', to: '2027-07-10' });
  eq(await p.$eval('#dsave', b => b.disabled), false);
  await p.click('#dsave'); await p.waitForTimeout(600);
  eq(await p.evaluate(() => JSON.parse(localStorage.getItem('berth.hmrc.v1')).added.length), 1);
  await p.reload(); await p.waitForTimeout(900);
  eq(await p.evaluate(() => JSON.parse(localStorage.getItem('berth.hmrc.v1')).added.length), 1,
     'the booking did not survive the reload');
});
await t('the system never accepts a booking it then flags as a conflict', async () => {
  await p.evaluate(() => { document.getElementById('yearjump').value = '2027'; });
  const rows = await p.$$eval('#conflicttable tbody tr', rs =>
    rs.map(r => r.textContent).filter(x => x.includes('Iron Sound')));
  eq(rows.length, 0);
});
await t('a vessel too long for the berth cannot be confirmed', async () => {
  await openBooking({ vessel: 'M/V High Current', from: '2027-04-06', to: '2027-04-08' });
  await p.click('.availrow:has-text("North Pier Face")');
  await p.waitForTimeout(300);
  eq(await p.$eval('#dsave', b => b.disabled), true, 'a refused berth must not be confirmable');
  ok(/longer than the berth/i.test(await p.textContent('#verdicthost .vh')));
});
await t('a closed berth is labelled closed, not too short', async () => {
  await openBooking({ vessel: 'M/V Grey Tern', from: '2026-11-03', to: '2026-11-06' });
  const rows = await availRows();
  eq(rows.find(r => r.name.includes('Inner Channel')).chip, 'Closed',
     'a berth shut for bollard replacement must not be reported as too short');
});
await t('a closed berth refuses bookings for those dates', async () => {
  await openBooking({ vessel: 'M/V Grey Tern', from: '2026-10-03', to: '2026-10-06' });
  await p.click('.availrow:has-text("South Float West")');
  await p.waitForTimeout(300);
  ok(/closed/i.test(await p.textContent('#verdicthost .vh')));
  eq(await p.$eval('#dsave', b => b.disabled), true);
});
await t('an event can be booked onto a berth', async () => {
  await openBooking({ kind: 'event', label: 'Community sail day', from: '2027-05-08', to: '2027-05-08' });
  eq(await p.$eval('#dsave', b => b.disabled), false);
  await p.click('#dsave'); await p.waitForTimeout(600);
  eq(await p.evaluate(() => JSON.parse(localStorage.getItem('berth.hmrc.v1')).added.length), 2);
});
await t('a closure can be booked and then blocks that berth', async () => {
  await openBooking({ kind: 'closure', label: 'Crane access', from: '2027-05-20', to: '2027-05-24' });
  await p.click('#dsave'); await p.waitForTimeout(600);
  await openBooking({ vessel: 'M/V Grey Tern', from: '2027-05-21', to: '2027-05-22' });
  const rows = await availRows();
  ok(rows.some(r => r.chip === 'Too short' || r.chip === 'Taken') ||
     rows.filter(r => r.chip === 'Fits').length < 6, 'the new closure had no effect');
});
await t('a new vessel is added with its length at booking time', async () => {
  await openBooking({ vessel: 'R/V Test Cutter', from: '2027-06-01', to: '2027-06-04', loa: 88 });
  eq(await p.$eval('#wrap-loa', e => e.hidden), false, 'should ask for a length');
  await p.click('#dsave'); await p.waitForTimeout(600);
  const store = await p.evaluate(() => localStorage.getItem('berth.hmrc.v1'));
  ok(store.includes('Test Cutter') && store.includes('88'), 'the new vessel kept its length');
});
await t('a booking with the dates reversed cannot be confirmed', async () => {
  await openBooking({ vessel: 'M/V Grey Tern', from: '2027-09-10', to: '2027-09-05' });
  eq(await p.$eval('#dsave', b => b.disabled), true);
});

/* ── chart as an input ─────────────────────────────────────────────── */
await t('clicking open water starts a booking there', async () => {
  await p.click('#chart', { position: { x: 700, y: 620 } });
  await p.waitForTimeout(400);
  ok(await p.$('.drawer'), 'no drawer opened');
  await p.keyboard.press('Escape');
});
await t('clicking a reservation opens its detail', async () => {
  await p.click('#chart .blk');
  await p.waitForTimeout(350);
  ok(await p.$('.popover'), 'no detail popover');
  await p.click('#pop-close');
});

/* ── recording a length ────────────────────────────────────────────── */
await t('recording a length turns a held berth into a measured hull', async () => {
  await p.click('#tab-fleet'); await p.waitForTimeout(500);
  const before = await p.$$eval('#queuetable tbody tr', r => r.length);
  ok(before > 0, 'measure-up queue is empty');
  const name = await p.$eval('#queuetable tbody tr .vname', n => n.textContent);
  await p.click('#queuetable tbody tr button[data-measure]');
  await p.waitForTimeout(350);
  await p.fill('#m-loa', '132');
  await p.click('#msave'); await p.waitForTimeout(600);
  const stored = await p.evaluate(() => JSON.parse(localStorage.getItem('berth.hmrc.v1')).loa);
  eq(stored[name], 132, 'the length was not saved against the vessel');
});
await t('fleet search narrows the register', async () => {
  await p.click('#tab-fleet'); await p.waitForTimeout(400);
  await p.fill('#fleetsearch', 'Golden Compass'); await p.waitForTimeout(350);
  const rows = await p.$$eval('#fleettable tbody tr', r => r.length);
  ok(rows >= 1 && rows < 20, `${rows} rows after searching`);
  await p.fill('#fleetsearch', ''); await p.waitForTimeout(300);
});

/* ── audit ─────────────────────────────────────────────────────────── */
await t('the import audit reports its findings', async () => {
  await p.click('#tab-audit'); await p.waitForTimeout(600);
  const stats = await p.$$eval('#auditstats .v', n => n.map(x => x.textContent.trim()));
  eq(stats[0], '2,244', 'reservation count changed');
  ok(await p.$$eval('#dbltable tbody tr', r => r.length) >= 5, 'historic overlaps missing');
  ok(await p.$$eval('#overtable tbody tr', r => r.length) >= 5, 'oversize assignments missing');
});
await t('the audit counts only imported data, not the example season', async () => {
  const stats = await p.$$eval('#auditstats .v', n => n.map(x => x.textContent.trim()));
  eq(stats[1], '486', 'the example season leaked into the archive figures');
});

/* ── navigation ────────────────────────────────────────────────────── */
await t('the archive is reachable and populated', async () => {
  await p.click('#tab-quay'); await p.waitForTimeout(400);
  await p.selectOption('#yearjump', '2010'); await p.waitForTimeout(600);
  ok((await p.textContent('#monthlabel')).includes('2010'));
  ok(await p.$$eval('#chart .blk', n => n.length) > 3, '2010 looks empty');
});
await t('arrow keys step through months', async () => {
  const before = await p.textContent('#monthlabel');
  await p.keyboard.press('ArrowRight'); await p.waitForTimeout(400);
  ok(await p.textContent('#monthlabel') !== before);
});
await t('the quarter view renders', async () => {
  await p.click('[data-zoom="quarter"]'); await p.waitForTimeout(600);
  ok(await p.$$eval('#chart .blk', n => n.length) > 3);
  await p.click('[data-zoom="month"]'); await p.waitForTimeout(400);
});
await t('switching the example season off still leaves a populated view', async () => {
  await p.click('#today'); await p.waitForTimeout(400);
  await p.uncheck('#demotoggle'); await p.waitForTimeout(800);
  ok(await p.$$eval('#chart .blk', n => n.length) >= 1,
     'nothing at all after turning the example off');
  // and a visitor who never had the example on still lands somewhere populated
  const ap = await newPage({ tag: 'archive-only' });
  await ap.evaluate(() => localStorage.setItem('berth.hmrc.v1.demo', '0'));
  await ap.reload(); await ap.waitForTimeout(900);
  ok(await ap.$$eval('#chart .blk', n => n.length) > 3,
     'archive-only visitor lands on an empty month');
  await ap.context().close(); current = p;
  await p.check('#demotoggle'); await p.waitForTimeout(600);
});

/* ── presentation ──────────────────────────────────────────────────── */
await t('no horizontal page scroll at phone width', async () => {
  await p.setViewportSize({ width: 390, height: 820 });
  await p.waitForTimeout(700);
  const over = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  ok(over <= 0, `${over}px of horizontal overflow`);
  await p.setViewportSize({ width: 1400, height: 1000 }); await p.waitForTimeout(500);
});
await t('dark mode paints its own background and readable text', async () => {
  const dp = await newPage({ colorScheme: 'dark', tag: 'dark' });
  const bg = await dp.evaluate(() => getComputedStyle(document.body).backgroundColor);
  ok(bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent', 'body has no background in dark mode');
  const nums = bg.match(/\d+/g).map(Number);
  ok(nums[0] < 90 && nums[1] < 90, `dark mode body is not dark: ${bg}`);
  ok(await dp.$$eval('#chart .blk', n => n.length) > 5, 'chart empty in dark mode');
  await dp.context().close(); current = p;
});
await t('a fresh visitor with no stored data gets a working page', async () => {
  const fp = await newPage({ tag: 'fresh' });
  ok(await fp.$$eval('#chart .blk', n => n.length) > 5);
  eq(await fp.$eval('#dayboard', e => e.children.length), 3);
  await fp.context().close(); current = p;
});
await t('the page still works when storage throws', async () => {
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 900 } });
  await ctx.route('**/*', r => r.request().url().includes('127.0.0.1') ? r.continue() : r.abort());
  await ctx.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {
      get() { throw new Error('storage blocked'); }
    });
  });
  const sp = await ctx.newPage();
  const errs = [];
  sp.on('pageerror', e => errs.push(e.message));
  await sp.goto(URL_); await sp.waitForTimeout(900);
  ok(await sp.$$eval('#chart .blk', n => n.length) > 5, 'chart empty with storage blocked');
  eq(errs.length, 0, 'errors with storage blocked: ' + errs.join('; '));
  await ctx.close(); current = p;
});

await t('no uncaught page errors during the whole run', async () => {
  eq(errors.length, 0, errors.join(' | '));
});

await browser.close();
server.close();
console.log(`\n\n  browser: ${pass} passed, ${fail} failed`);
if (fail) { console.log('\n  FAILURES:'); fails.forEach(f => console.log('    ✗ ' + f)); process.exit(1); }
