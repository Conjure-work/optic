// Chart, the Options widget in the dock (round three, 2026-11-23): Options inside Charting. Five views of the same
// ticker beside the chart, from the Options tab's own builders (options-panels.js) and the same endpoints:
//   Readings  what the options price (P.pricing), from the ticker payload the chart page has already loaded
//   Chain     calls or puts at the nearest expiry, nearest the money, from /api/options/{T}/research
//   Builder   a template (long call, long put, bull call spread, bear put spread) built from that expiry's quotes by
//             nearest delta, as the Options tab's builder picks them, and priced by POST /api/options/{T}/analyze
//   Gamma     dealer positioning (P.gex), from the ticker payload
//   Flow      the day's options activity (P.flow), from the ticker payload
// None calls a model. The full Options tab is one link away from each view for everything the dock leaves out.
import { html } from '../core/dom.js';
import * as api from '../core/api.js';
import { num, money, clean, shortDate, isNum } from '../core/format.js';
import { mountCharts } from '../ui/chart.js';
import * as P from './options-panels.js';

export const VIEWS = [['readings', 'Readings'], ['chain', 'Chain'], ['builder', 'Builder'], ['gamma', 'Gamma'], ['flow', 'Flow']];
export const TEMPLATES = [['long_call', 'Long call'], ['long_put', 'Long put'], ['bull_call', 'Bull call spread'], ['bear_put', 'Bear put spread']];
let O = { sym: null, view: 'readings', side: 'call', chain: {}, rows: {}, b: null };
function forSym(sym) { if (O.sym !== sym) O = { sym, view: O.view, side: 'call', chain: {}, rows: {}, b: null }; return O; }

const usable = (r) => isNum(r.mid) && isNum(r.delta) && ((r.liquidity || {}).grade !== 'not_tradable');
/** The quoted contract nearest a delta's size, within 0.15 of it (the Options tab's rule, options.js nearest). */
export function nearest(list, target) {
  const best = (list || []).filter(usable).reduce((b, r) => (!b || Math.abs(Math.abs(r.delta) - target) < Math.abs(Math.abs(b.delta) - target) ? r : b), null);
  return best && Math.abs(Math.abs(best.delta) - target) <= 0.15 ? best : null;
}
/** A template's legs from one expiry's calls and puts, or null when the quotes cannot make it in order. */
export function legsFor(id, calls, puts) {
  const L = (r, side) => (r ? { type: r.type || (calls.includes(r) ? 'call' : 'put'), side, qty: 1, strike: r.strike, expiry: r.expiry } : null);
  const c = (t) => nearest(calls, t), p = (t) => nearest(puts, t);
  let legs = [];
  if (id === 'long_call') legs = [L(c(0.5), 'long')];
  else if (id === 'long_put') legs = [L(p(0.5), 'long')];
  else if (id === 'bull_call') legs = [L(c(0.5), 'long'), L(c(0.3), 'short')];
  else if (id === 'bear_put') legs = [L(p(0.5), 'long'), L(p(0.3), 'short')];
  if (!legs.length || legs.some((l) => !l)) return null;
  if (id === 'bull_call' && !(legs[0].strike < legs[1].strike)) return null;
  if (id === 'bear_put' && !(legs[0].strike > legs[1].strike)) return null;
  return legs;
}

async function chainRows(sym, side, expiry, wide) {
  const key = `${side}|${expiry || ''}|${wide ? 'all' : 'near'}`;
  if (O.rows[key]) return O.rows[key];
  const q = `side=${side}&delta_lo=${wide ? 0 : 0.15}&delta_hi=${wide ? 1 : 0.85}${expiry ? `&expiry=${expiry}` : ''}`;
  const d = await api.get(`/api/options/${encodeURIComponent(sym)}/research?${q}`, { ttl: 120000, timeout: 60000 });
  O.rows[key] = d;
  return d;
}
/** Start what the open view needs. `repaint` redraws the widget once an answer lands. */
export function need(sym, repaint) {
  const o = forSym(sym);
  if (o.view === 'chain' && !o.chain[o.side] && !o.chain[o.side + 'Busy']) {
    o.chain[o.side + 'Busy'] = true;
    chainRows(sym, o.side).then((d) => { o.chain[o.side] = d; }, (e) => { o.chain[o.side] = { error: e }; }).finally(() => { o.chain[o.side + 'Busy'] = false; if (O === o) repaint(); });
  }
}
async function build(sym, id, repaint) {
  const o = forSym(sym);
  o.b = { tpl: id, busy: true };
  repaint();
  try {
    const first = await chainRows(sym, 'call');
    const exp = first.expiry;
    if (!exp) throw new Error('The contracts for an expiry have not loaded yet, so there is nothing to build from.');
    const calls = ((await chainRows(sym, 'call', exp, true)).table || {}).rows || [], puts = ((await chainRows(sym, 'put', exp, true)).table || {}).rows || [];
    const legs = legsFor(id, calls.map((r) => Object.assign({ type: 'call' }, r)), puts.map((r) => Object.assign({ type: 'put' }, r)));
    if (!legs) throw new Error('This expiry has no tradable quoted contract near the deltas the template needs, in the order it needs.');
    const a = await api.post(`/api/options/${encodeURIComponent(sym)}/analyze`, { legs, slippage: 0, fee_per_contract: 0 }, { timeout: 45000 });
    if (O !== o) return;
    o.b = { tpl: id, legs, analysis: a, expiry: exp };
  } catch (e) { if (O !== o) return; o.b = { tpl: id, error: e.message || api.explain(e, 'The position') }; }
  repaint();
}

const legWords = (l) => `${l.side === 'long' ? 'Buy' : 'Sell'} ${l.qty} ${num(l.strike, l.strike % 1 ? 2 : 0)} ${l.type} ${shortDate(l.expiry)}`;
const paid = (v) => (isNum(v) ? `${money(Math.abs(v), 2)} ${v >= 0 ? 'paid' : 'received'}` : 'n/a');
const full = (sym) => html`<a class="textlink chw-more" href="#/${encodeURIComponent(sym)}/options">Options for ${sym} in full</a>`;

function chainView(sym, o) {
  const d = o.chain[o.side];
  const seg = html`<div class="seg" role="group" aria-label="Side">${[['call', 'Calls'], ['put', 'Puts']].map(([k, l]) => html`<button type="button" data-chw-optside="${k}" aria-pressed="${o.side === k}">${l}</button>`)}</div>`;
  if (!d) return html`${seg}<p class="chw-none" role="status">Loading the ${o.side}s.</p>`;
  if (d.error) return html`${seg}<p class="chw-none">${api.explain(d.error, 'The chain')}</p>${full(sym)}`;
  const rows = ((d.table || {}).rows || []).slice().sort((a, b) => Math.abs(Math.abs(a.delta || 0) - 0.5) - Math.abs(Math.abs(b.delta || 0) - 0.5)).slice(0, 10).sort((a, b) => a.strike - b.strike);
  if (!rows.length) return html`${seg}<p class="chw-none">${clean(d.unusable || `No ${o.side}s with a two-sided quote near the money at this expiry.`)}</p>${full(sym)}`;
  return html`${seg}<div class="tscroll"><table class="t chw-table"><caption class="sr">${sym} ${o.side}s expiring ${d.expiry}, nearest the money</caption><thead><tr><th scope="col">Strike</th><th scope="col" class="num">Mid</th><th scope="col" class="num">Delta</th><th scope="col" class="num">Open int.</th></tr></thead>
    <tbody>${rows.map((r) => html`<tr><td>${num(r.strike, r.strike % 1 ? 2 : 0)}</td><td class="num">${num(r.mid)}</td><td class="num">${num(r.delta, 2)}</td><td class="num">${isNum(r.open_interest) ? num(r.open_interest, 0) : 'n/a'}</td></tr>`)}</tbody></table></div>
    <p class="chw-fine">${d.expiry ? `Expiry ${shortDate(d.expiry)}. ` : ''}Mid is halfway between the bid and the ask; you usually pay more.</p>${full(sym)}`;
}
function builderView(sym, o) {
  const b = o.b || {};
  const tpls = html`<div class="cluster" role="group" aria-label="Templates">${TEMPLATES.map(([k, l]) => html`<button type="button" class="btn btn-sm" data-chw-opttpl="${k}" aria-pressed="${b.tpl === k}">${l}</button>`)}</div>`;
  if (!b.tpl) return html`${tpls}<p class="chw-fine">A template fills the legs from the nearest expiry's quotes by delta, then the server prices the position at the mid. The full builder, with your own legs, slippage and fees, is on the Options tab.</p>${full(sym)}`;
  if (b.busy) return html`${tpls}<p class="chw-none" role="status">Pricing the position.</p>`;
  if (b.error) return html`${tpls}<p class="chw-none" role="alert">${clean(b.error)}</p>${full(sym)}`;
  const a = b.analysis || {}, en = a.entry || {};
  const mp = a.max_profit_unbounded ? 'No cap' : money(a.max_profit, 2), ml = a.max_loss_unbounded ? 'No limit' : a.cannot_lose_at_quotes ? 'Nothing, at these quotes' : money(-a.max_loss, 2);
  return html`${tpls}<p>${b.legs.map(legWords).join('; ')}.</p>
    <dl class="chw-rows"><div><dt>Entry at the mid</dt><dd>${paid(en.mid)}</dd></div><div><dt>Most it can make at expiry</dt><dd class="up">${mp}</dd></div><div><dt>Most it can lose at expiry</dt><dd class="down">${ml}</dd></div><div><dt>Breakeven at expiry</dt><dd>${(a.breakevens_at_expiry || []).length ? a.breakevens_at_expiry.map((x) => num(x)).join(' and ') : 'None in range'}</dd></div></dl>
    <p class="chw-fine">From the mid, not a fill; model output for research, not a recommendation to trade.</p>${full(sym)}`;
}
/** The widget's body for `sym`, the ticker payload `t` (null while it loads; `wait` is what to show then). */
export function body(sym, t, wait) {
  const o = forSym(sym);
  const seg = html`<div class="seg chw-optviews" role="group" aria-label="Options views">${VIEWS.map(([k, l]) => html`<button type="button" data-chw-optview="${k}" aria-pressed="${o.view === k}">${l}</button>`)}</div>`;
  if (o.view === 'chain') return html`${seg}${chainView(sym, o)}`;
  if (o.view === 'builder') return html`${seg}${builderView(sym, o)}`;
  if (!t) return html`${seg}${wait}`;
  if (o.view === 'gamma') return html`${seg}<div class="chw-opt">${P.gex(t, sym)}</div>${full(sym)}`;
  if (o.view === 'flow') return html`${seg}<div class="chw-opt">${P.flow(t, sym)}</div>${full(sym)}`;
  return html`${seg}<div class="chw-opt">${P.pricing(t, sym)}</div>${full(sym)}`;
}
/** After the body is drawn: its charts. */
export function after(el, sym, t) {
  if (!t || !el) return;
  const o = forSym(sym);
  const makers = o.view === 'gamma' ? P.gexCharts(t) : o.view === 'flow' ? P.flowCharts(t) : o.view === 'readings' ? P.pricingCharts(t) : {};
  try { mountCharts(el, makers); } catch (e) { /* a chart that cannot draw leaves its figures */ }
}
/** Clicks inside the widget; true when handled. */
export function onClick(e, sym, repaint) {
  const b = e.target.closest('[data-chw-optview],[data-chw-optside],[data-chw-opttpl]');
  if (!b) return false;
  const o = forSym(sym);
  if (b.dataset.chwOptview) { o.view = b.dataset.chwOptview; need(sym, repaint); repaint(); return true; }
  if (b.dataset.chwOptside) { o.side = b.dataset.chwOptside; need(sym, repaint); repaint(); return true; }
  if (b.dataset.chwOpttpl) { build(sym, b.dataset.chwOpttpl, repaint); return true; }
  return false;
}
export const view = (sym) => forSym(sym).view;
