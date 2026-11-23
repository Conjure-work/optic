// Chart, round three (2026-11-23): one, two or four charts at once, each with its own ticker, bar size and range; the
// reader's favourite bar sizes in a row above each chart; and drawings on one ticker redrawn live on every chart of
// that ticker in the layout.
//
// The first chart is the page's own (chart.js, with the tool rail, the menus and the dock). The others are drawn here,
// one compact chart each, with the same price chart (ui/pricechart.js). A layout is kept in this browser
// (optic.v2.chart.layout.v1); a signed-in reader can also name one and keep it on the account (app/chart_routes.py,
// at most 20). Below the 860 px breakpoint a phone shows one or two charts stacked: four postage stamps at 390 px are
// unreadable, so a saved four opens as its first two with a line saying so.
//
// Drawings stay in the browser per ticker (optic.chart.drawings.v2, shared with the classic app). A change on any
// chart is published on `bus` and every other chart of that ticker in the layout is redrawn in the same task, before
// the browser paints, so the copies never disagree for a frame.
import { $, html, render as draw } from '../core/dom.js';
import * as api from '../core/api.js';
import { isNum } from '../core/format.js';
import { createPriceChart } from '../ui/pricechart.js';

export const LAYOUT_KEY = 'optic.v2.chart.layout.v1';
export const INTERVALS_KEY = 'optic.v2.chart.intervals.v1';
export const COUNTS = [1, 2, 4];
export const PHONE_COUNTS = [1, 2];
// the page's bar sizes (chart.js INTERVALS) with the name a favourite is kept under (app/chart_routes.py)
export const IV = [
  { key: '1', fav: '1m', label: '1m', intraday: true, history: '5d' }, { key: '5', fav: '5m', label: '5m', intraday: true, history: '1mo' },
  { key: '15', fav: '15m', label: '15m', intraday: true, history: '60d' }, { key: '30', fav: '30m', label: '30m', intraday: true, history: '60d' },
  { key: '60', fav: '1h', label: '1h', intraday: true, history: '1y' }, { key: '240', fav: '4h', label: '4h', intraday: true, history: '2y' },
  { key: 'daily', fav: '1d', label: '1D' }, { key: 'weekly', fav: '1wk', label: '1W' },
];
export const RANGE_BARS = { daily: { '1M': 21, '3M': 63, '6M': 126, '1Y': 252, All: Infinity }, weekly: { '1M': 5, '3M': 13, '6M': 26, '1Y': 52, All: Infinity } };
export const DEFAULT_FAVS = ['5m', '1h', '1d'];
const SYM = /^[A-Z0-9.^=-]{1,12}$/;
const DRAW_KEY = 'optic.chart.drawings.v2';

/* ---------------- the layout ---------------- */
/** A layout as the page keeps it: {count, slots: [{symbol, interval, range}]}, one slot per chart, the first always
 *  the page's own ticker. Anything unreadable falls back to one chart. */
export function sanitizeLayout(v, sym, base = {}) {
  const count = v && COUNTS.includes(v.count) ? v.count : 1;
  const given = Array.isArray(v && v.slots) ? v.slots : [];
  const fill = ['SPY', 'QQQ', 'IWM', 'DIA'].filter((x) => x !== sym);
  const slots = [];
  for (let i = 0; i < count; i++) {
    const s = given[i] || {};
    const symbol = i === 0 ? sym : (SYM.test(String(s.symbol || '').toUpperCase()) ? String(s.symbol).toUpperCase() : fill[(i - 1) % fill.length]);
    const interval = IV.some((x) => x.key === s.interval) ? s.interval : (i === 0 && base.interval) || 'daily';
    const range = RANGE_BARS.daily[s.range] !== undefined ? s.range : (i === 0 && base.range) || '6M';
    slots.push({ symbol, interval, range });
  }
  return { count, slots };
}
/** What a screen of this width shows: below the breakpoint at most two, stacked, with the line that says so. */
export function forWidth(layout, phone) {
  if (!phone || layout.count < 4) return { count: layout.count, slots: layout.slots.slice(0, layout.count), note: '' };
  return { count: 2, slots: layout.slots.slice(0, 2), note: `This layout has ${layout.count} charts; a screen this narrow shows the first two, stacked. A wider window shows all ${layout.count}.` };
}
export function readLayout(sym, base) {
  try { return sanitizeLayout(JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null'), sym, base); } catch (e) { return sanitizeLayout(null, sym, base); }
}
export function saveLayout(layout) { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify({ count: layout.count, slots: layout.slots })); } catch (e) { /* private mode */ } }
/** The layout with `n` charts: the slots it had are kept, new ones filled. */
export const withCount = (layout, n, sym) => sanitizeLayout({ count: n, slots: layout.slots }, sym);

/* ---------------- favourite bar sizes ---------------- */
export const favToKey = (f) => (IV.find((x) => x.fav === f) || {}).key || null;
export const keyToFav = (k) => (IV.find((x) => x.key === k) || {}).fav || null;
export function cleanFavs(list) {
  if (!Array.isArray(list)) return null;
  return IV.map((x) => x.fav).filter((f) => list.includes(f));   // in the bar sizes' own order, each once
}
export function readFavs() {
  try { const v = cleanFavs(JSON.parse(localStorage.getItem(INTERVALS_KEY) || 'null')); return v && v.length ? v : DEFAULT_FAVS.slice(); } catch (e) { return DEFAULT_FAVS.slice(); }
}
export function browserChose() { try { return !!cleanFavs(JSON.parse(localStorage.getItem(INTERVALS_KEY) || 'null')); } catch (e) { return false; } }
export function saveFavs(list) { const v = cleanFavs(list) || []; try { localStorage.setItem(INTERVALS_KEY, JSON.stringify(v)); } catch (e) { /* private mode */ } return v; }
/** Signed in, the account's favourites win, as the level does (core/store.js); an account with none takes the ones
 *  this browser chose. Returns the favourites to show. */
export async function syncFavs(signedIn) {
  if (!signedIn) return readFavs();
  try {
    const acct = cleanFavs(((await api.get('/api/chart/intervals', { ttl: 0, force: true, timeout: 10000 })) || {}).intervals);
    if (acct && acct.length) { saveFavs(acct); return acct; }
    if (browserChose()) await api.put('/api/chart/intervals', { intervals: readFavs() }, { timeout: 10000 });
  } catch (e) { /* the browser's favourites stand; the next change sends them */ }
  return readFavs();
}
export async function pushFavs(list, signedIn) {
  const v = saveFavs(list);
  if (signedIn) { try { await api.put('/api/chart/intervals', { intervals: v }, { timeout: 10000 }); } catch (e) { return { ok: false, favs: v }; } }
  return { ok: true, favs: v };
}

/* ---------------- drawings across charts ---------------- */
export function createBus() {
  const subs = new Set();
  return {
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    /** A ticker's drawings changed on chart `from`: every other chart of that ticker hears it now, synchronously. */
    publish(sym, list, from) { subs.forEach((fn) => { try { fn(sym, list, from); } catch (e) { console.error(e); } }); },
    size: () => subs.size,
  };
}
export const bus = createBus();
export function readDrawings(sym) {
  try { const all = JSON.parse(localStorage.getItem(DRAW_KEY) || '{}'); return Array.isArray(all[sym]) ? all[sym].filter((d) => d && Array.isArray(d.points)) : []; } catch (e) { return []; }
}
export function writeDrawings(sym, list) {
  try { const all = JSON.parse(localStorage.getItem(DRAW_KEY) || '{}'); if (list.length) all[sym] = list; else delete all[sym]; localStorage.setItem(DRAW_KEY, JSON.stringify(all)); return true; } catch (e) { return false; }
}

/* ---------------- the controls ---------------- */
/** The control for how many charts: one, two or four (one or two on a phone). */
export function countControl(n, phone) {
  return html`<div class="seg ch-count-ctl" role="group" aria-label="Charts on screen">${(phone ? PHONE_COUNTS : COUNTS).map((c) => html`<button type="button" data-v2-ch-count="${c}" aria-pressed="${n === c}" title="${c === 1 ? 'One chart' : `${c} charts`}">${c}<span class="sr"> ${c === 1 ? 'chart' : 'charts'}</span></button>`)}</div>`;
}
/** The favourite bar sizes as one row of buttons, the current one pressed. `slot` names which chart they set. */
export function favRow(favs, current, slot = 0, label = 'Favourite bar sizes') {
  const list = (favs && favs.length ? favs : DEFAULT_FAVS).map(favToKey).filter(Boolean);
  return html`<div class="seg ch-favs" role="group" aria-label="${label}">${list.map((k) => { const iv = IV.find((x) => x.key === k); return html`<button type="button" data-v2-ch-fav="${k}" data-v2-ch-slot="${slot}" aria-pressed="${current === k}">${iv.label}</button>`; })}</div>`;
}
/** The menu that chooses the favourites, one box per bar size. */
export function favMenu(favs) {
  return html`<details class="menu ch-favmenu" data-ch-menu="favs"><summary class="btn btn-sm">Favourites</summary><div class="menu-body"><fieldset class="ch-favset"><legend class="menu-help">Bar sizes shown above each chart</legend>${IV.map((x) => html`<label class="check"><input type="checkbox" data-v2-ch-favset="${x.fav}" ${favs.includes(x.fav) ? 'checked' : ''}> <span>${x.label}</span></label>`)}</fieldset><p class="menu-help">Signed in, they follow your account to any browser.</p></div></details>`;
}
/** Saved layouts: save the one on screen under a name, open or delete a saved one; signed out, why not. */
export function layoutsMenu(signedIn, saved, err) {
  return html`<details class="menu ch-laymenu" data-ch-menu="layouts"><summary class="btn btn-sm">Layouts</summary><div class="menu-body">
    ${signedIn ? html`<form class="cluster" data-v2-ch-laysave><label class="field field-sm"><span class="sr">Name for this chart layout</span><input name="n" maxlength="40" placeholder="Name this layout" required></label><button type="submit" class="btn btn-sm">Save</button></form>
      ${err ? html`<p class="menu-help ch-cannot" role="alert">${err}</p>` : ''}
      ${saved && saved.length ? html`<ul class="cmp-list">${saved.map((l) => html`<li><button type="button" class="textlink" data-v2-ch-layopen="${l.name}">${l.name}</button><span class="t-muted">${l.count} chart${l.count === 1 ? '' : 's'}</span><button type="button" class="textlink" data-v2-ch-laydel="${l.name}" aria-label="Delete the layout ${l.name}">Delete</button></li>`)}</ul>` : html`<p class="menu-help">No saved layouts yet. An account keeps up to 20.</p>`}`
    : html`<p class="menu-help">This browser keeps the layout on screen. Sign in to name layouts and open them from any browser.</p>`}
  </div></details>`;
}

/* ---------------- the other charts ---------------- */
async function barsFor(slot) {
  const e = encodeURIComponent(slot.symbol), iv = IV.find((x) => x.key === slot.interval) || IV[6];
  if (iv.intraday) {
    const d = await api.get(`/api/intraday/${e}?range=${iv.key}&window=${iv.history}&session=regular`, { ttl: 60000, timeout: 45000 });
    if (!d || !d.available) throw new api.ApiError('notfound', 404, (d && d.reason) || `${iv.label} bars are not available for ${slot.symbol}.`);
    return { bars: d.times.map((t, i) => ({ t: Date.parse(t), o: d.opens[i], h: d.highs[i], l: d.lows[i], c: d.closes[i], v: d.volumes[i] })), note: '' };
  }
  const d = slot.interval === 'weekly' ? await api.get(`/api/weekly-bars/${e}?span=${slot.range === 'All' ? 'max' : '10y'}`, { ttl: 3600000, timeout: 45000 })
    : await api.get(`/api/daily-bars/${e}`, { ttl: 3600000, timeout: 60000 });
  if (!d || d.available === false || !(d.dates || []).length) throw new api.ApiError('notfound', 404, (d && d.reason) || `No bars for ${slot.symbol}.`);
  const note = slot.range === 'All' && d.history && d.history.sentence ? d.history.sentence : '';
  return { bars: d.dates.map((t, i) => ({ t: Date.parse(t), o: d.open[i], h: d.high[i], l: d.low[i], c: d.close[i], v: d.volume[i] })), note };
}
const clip = (bars) => bars.filter((b) => isNum(b.c) && isNum(b.t) && b.c > 0).map((b) => ({ t: b.t, o: isNum(b.o) ? b.o : b.c, h: isNum(b.h) ? b.h : b.c, l: isNum(b.l) ? b.l : b.c, c: b.c, v: b.v || 0 }));

/** One compact chart: its own ticker, bar size and range; drawings of its ticker kept in step through `bus`. */
export function createSlot(host, slot, index, { favs, height = 320, onChange, canWrite = () => true } = {}) {
  const S = { slot: Object.assign({}, slot), chart: null, bars: null, err: null, seq: 0, note: '' };
  const id = `slot${index}`;
  const unsub = bus.subscribe((sym, list, from) => { if (from !== id && sym === S.slot.symbol && S.chart) S.chart.set({ drawings: list }); });
  function head() {
    const s = S.slot, iv = IV.find((x) => x.key === s.interval) || IV[6];
    return html`<form class="chg-head" data-v2-chg-sym="${index}"><label class="field field-sm"><span class="sr">Ticker for chart ${index + 1}</span><input name="s" value="${s.symbol}" maxlength="12" autocomplete="off" autocapitalize="characters" spellcheck="false" data-v2-ta="submit"></label><button type="submit" class="btn btn-sm">Show</button></form>
      ${favRow(favs(), s.interval, index, `Favourite bar sizes, chart ${index + 1}`)}
      <label class="select"><span class="sr">Bar size, chart ${index + 1}</span><select data-v2-chg-iv="${index}">${IV.map((x) => html`<option value="${x.key}" ${x.key === s.interval ? 'selected' : ''}>${x.label}</option>`)}</select></label>
      ${iv.intraday ? '' : html`<label class="select"><span class="sr">Range, chart ${index + 1}</span><select data-v2-chg-range="${index}">${Object.keys(RANGE_BARS.daily).map((r) => html`<option value="${r}" ${s.range === r ? 'selected' : ''}>${r}</option>`)}</select></label>`}`;
  }
  function paint() {
    const s = S.slot;
    draw(host, html`<section class="chg-slot" aria-label="Chart ${index + 1}, ${s.symbol}" data-chg-slot="${index}" data-chg-sym="${s.symbol}"><div class="ctools chg-tools">${head()}</div><div class="chg-plot" id="chg-plot-${index}"></div><p class="asof chg-note" id="chg-note-${index}"></p></section>`);
    plot();
  }
  function plot() {
    const box = $(`#chg-plot-${index}`, host); if (!box) return;
    const n = $(`#chg-note-${index}`, host);
    if (S.err) { if (S.chart) { S.chart.destroy(); S.chart = null; } draw(box, html`<p class="chw-none" role="status">${api.explain(S.err, `${S.slot.symbol}'s bars`)} <button type="button" class="textlink" data-v2-chg-retry="${index}">Try again</button></p>`); if (n) n.textContent = ''; return; }
    if (!S.bars) { if (S.chart) { S.chart.destroy(); S.chart = null; } draw(box, html`<p class="chw-none" role="status">Loading ${S.slot.symbol}</p>`); return; }
    const iv = IV.find((x) => x.key === S.slot.interval) || IV[6];
    const r = iv.intraday ? Infinity : RANGE_BARS[S.slot.interval === 'weekly' ? 'weekly' : 'daily'][S.slot.range];
    box.innerHTML = '<div class="pc-host"></div>';
    if (S.chart) S.chart.destroy();
    S.chart = createPriceChart(box.lastChild, {
      bars: S.bars, intraday: !!iv.intraday, style: 'candles', snap: true, overlays: {}, panes: { volume: true }, levels: {}, events: [], filings: [],
      drawings: readDrawings(S.slot.symbol), tool: 'select', window: Number.isFinite(r) ? Math.min(r, S.bars.length) : S.bars.length,
      label: `${S.slot.symbol}, ${iv.label} bars, chart ${index + 1}`, title: { sym: S.slot.symbol, what: iv.label }, height, navigator: false,
      onDrawings: (list) => { if (canWrite()) writeDrawings(S.slot.symbol, list); bus.publish(S.slot.symbol, list, id); },
    });
    if (n) n.textContent = S.note || '';
  }
  async function load() {
    const my = ++S.seq; S.bars = null; S.err = null; plot();
    try { const r = await barsFor(S.slot); if (my !== S.seq) return; const b = clip(r.bars); if (b.length < 5) throw new api.ApiError('notfound', 404, 'Not enough bars to draw.'); S.bars = b; S.note = r.note; }
    catch (e) { if (my !== S.seq) return; S.err = e; }
    plot();
  }
  function set(next) { Object.assign(S.slot, next); paint(); load(); if (onChange) onChange(index, Object.assign({}, S.slot)); }
  paint(); load();
  return {
    set, reload: load, slot: () => Object.assign({}, S.slot), chart: () => S.chart, repaintHead: () => { const t = $('.chg-tools', host); if (t) draw(t, head()); },
    destroy() { unsub(); if (S.chart) { S.chart.destroy(); S.chart = null; } },
  };
}
