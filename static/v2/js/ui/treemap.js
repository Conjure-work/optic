// Round three (2026-11-23): the sector treemap and the holdings donut, held from Pass 2.
//
// The sector treemap is the eleven sector funds laid out by the server (/api/stockmap, app/analytics/stockmaps.py),
// each tile sized by its weight and coloured by today's move. Weight: the free feed reports no index weights, so the
// tiles are sized by the money that trades through each fund a day (price times average volume), the nearest stand-in
// it has; the caption says so. Exact index weights need a licensed constituent file, which this round does not add.
// Every figure has a text alternative: the picture is one image with a summary, and the full table is under it.
//
// The holdings donut is a reader's own book by value, largest first, the rest as Other, for a reader with no linked
// brokerage (the Paper Desk, optic.paper.v1, kept in the browser). Its legend states every share as text.
import { html, raw, render as draw } from '../core/dom.js';
import * as api from '../core/api.js';
import { num, signed, compact, isNum, esc, clean } from '../core/format.js';
import { donut } from './glance.js';

export const TEMPLATE = 'sector-today';
const SIZE_WORDS = 'Each tile is sized by the money traded through the sector\'s fund a day, the free feed\'s nearest stand-in for its weight in the market; exact index weights need a licensed constituent file.';

/** The tiles as one SVG picture. Pure: the layout in percent from the server, `w` pixels wide. */
export function treemapSVG(map, w = 640) {
  const lay = (map && map.layout) || [];
  if (!lay.length) return '';
  const W = Math.max(280, Math.round(w)), H = Math.round(W * (W < 600 ? 0.9 : 0.45));
  const k = Math.max(...lay.map((c) => c.x + c.w)) > 1.5 ? 100 : 1;
  const col = ((map.template || {}).color) || 'chg_1d', dom = map.colour_domain || {};
  const m = Math.max(Math.abs(dom.min || 0), Math.abs(dom.max || 0)) || 1;
  const tone = (v) => { if (!isNum(v)) return 'var(--c-sunk)'; const t = Math.max(-1, Math.min(1, v / m)); return t >= 0 ? `color-mix(in srgb, var(--c-pos) ${Math.round(15 + 55 * t)}%, var(--c-plane))` : `color-mix(in srgb, var(--c-neg) ${Math.round(15 + 55 * -t)}%, var(--c-plane))`; };
  const cells = lay.map((c) => {
    const v = (c.values || {})[col], x = (c.x / k) * W, y = (c.y / k) * H, ww = (c.w / k) * W, hh = (c.h / k) * H;
    return `<g class="tile"><rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(0, ww - 2).toFixed(1)}" height="${Math.max(0, hh - 2).toFixed(1)}" rx="3" style="fill:${tone(v)}"/>${ww > 56 && hh > 30 ? `<text x="${(x + 8).toFixed(1)}" y="${(y + 20).toFixed(1)}" class="tile-t">${esc(c.name || c.symbol)}</text><text x="${(x + 8).toFixed(1)}" y="${(y + 38).toFixed(1)}" class="tile-v">${esc(signed(v))}</text>` : ''}</g>`;
  }).join('');
  return `<svg class="smap" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(summary(map))}">${cells}</svg>`;
}
/** One sentence for the picture: the largest tiles and today's moves. */
export function summary(map) {
  const rows = ((map && map.layout) || []).slice(0, 4);
  const col = ((map && map.template) || {}).color || 'chg_1d';
  if (!rows.length) return 'No sector map.';
  return `Sector funds sized by daily dollar volume, coloured by today's move. Largest: ${rows.map((c) => `${c.name || c.symbol} ${signed((c.values || {})[col])}`).join(', ')}. The full table follows.`;
}
/** The text alternative: every fund with its weight stand-in and today's move. */
export function table(map) {
  const rows = (map && map.rows) || [];
  const col = ((map && map.template) || {}).color || 'chg_1d', size = ((map && map.template) || {}).size || 'dollar_volume';
  return html`<details class="more-inline"><summary>The sector map as a table</summary><div class="tscroll" tabindex="0" role="region" aria-label="The sector map as a table"><table class="t"><caption class="sr">Sector funds, money traded a day and today's move</caption><thead><tr><th scope="col">Sector</th><th scope="col" class="num">Traded a day</th><th scope="col" class="num">Today</th></tr></thead>
    <tbody>${rows.map((r) => html`<tr><td>${r.name || r.symbol} <span class="t-muted">${r.symbol}</span></td><td class="num">${isNum((r.values || {})[size]) ? `$${compact(r.values[size])}` : 'n/a'}</td><td class="num">${signed((r.values || {})[col])}</td></tr>`)}</tbody></table></div></details>`;
}

/** The sector treemap as a figure: the picture, the table and the source; `map` undefined while it loads, `err` a
 *  failed load. Drawn whole, so a page that redraws itself draws it again with the same answer. */
export function sectorFigure(map, err, w = 640, heading = 'Sectors by weight, today', H = null) {
  const head = H || html`<p class="t-label">${heading}</p>`;
  if (map === undefined && !err) return html`<figure class="fv smap-fig" data-v2-treemap><figcaption>${head}</figcaption><p class="asof" role="status">Loading the sector map.</p></figure>`;
  if (err || !map || !(map.layout || []).length) return html`<figure class="fv smap-fig" data-v2-treemap><figcaption>${head}</figcaption><p class="asof">${err ? api.explain(err, 'The sector map') : clean((map && map.error) || 'The sector map has no figures right now.')}</p></figure>`;
  return html`<figure class="fv smap-fig" data-v2-treemap><figcaption>${head}<p class="fv-unit">${SIZE_WORDS} Colour is today's move.</p></figcaption>
    ${raw(treemapSVG(map, w))}${table(map)}
    <p class="asof">Source: Yahoo Finance's delayed quotes for the eleven sector funds.${(map.dropped || []).length ? ` Left out for missing data: ${map.dropped.map((d) => d.symbol || d).join(', ')}.` : ''}</p></figure>`;
}
export const loadSectorMap = () => api.get(`/api/stockmap?template=${TEMPLATE}`, { ttl: 600000, timeout: 60000 });
/** The sector treemap into `host` (the Portfolio page's call): loads the map, then draws the figure. */
export async function renderSectorTreemap(host, { heading = 'Sectors by weight, today' } = {}) {
  if (!host) return;
  draw(host, sectorFigure(undefined, null, 0, heading));
  let map = null, err = null;
  try { map = await loadSectorMap(); } catch (e) { err = e; }
  if (!host.isConnected) return;
  draw(host, sectorFigure(map, err, Math.max(280, host.clientWidth || 640), heading));
}

/* ---------------- the holdings donut ---------------- */
/** A book's value by name, largest first, beyond `top` names gathered as Other. Each position {ticker, qty, price}. */
export function holdingsParts(positions, top = 4) {
  const by = {};
  (positions || []).forEach((p) => {
    const sym = String(p.ticker || p.symbol || '').toUpperCase(), v = Number(p.qty) * Number(p.price) * (p.instrument === 'option' ? 100 : 1);
    if (sym && isNum(v) && v > 0) by[sym] = (by[sym] || 0) + v;
  });
  const all = Object.entries(by).map(([label, v]) => ({ label, v })).sort((a, b) => b.v - a.v);
  const head = all.slice(0, top), rest = all.slice(top).reduce((a, p) => a + p.v, 0);
  return rest > 0 ? [...head, { label: 'Other', v: rest }] : head;
}
/** The donut of a book, or a plain line when there is not enough in it to draw one. */
export function holdingsDonut(positions, { label = 'Your Paper Desk by value', note = '' } = {}) {
  const parts = holdingsParts(positions);
  const total = parts.reduce((a, p) => a + p.v, 0);
  if (parts.length < 2) return html`<p class="asof">${parts.length ? `One name, ${parts[0].label}, is the whole book.` : 'No open positions to draw.'}</p>`;
  // the total in the caption, not in the ring's middle: text laid over the ring has no background a contrast check can
  // read, and axe failed it on the Portfolio layout (round three)
  return html`<figure class="fv dn-fig-wrap" data-v2-donut><figcaption><p class="t-label">${label}, $${compact(total)} in all</p>${note ? html`<p class="fv-unit">${note}</p>` : ''}</figcaption>
    ${donut(parts, { label: `${label}: ${parts.map((p) => `${p.label} ${Math.round((p.v / total) * 100)}%`).join(', ')}` })}</figure>`;
}
/** The Paper Desk book kept in this browser (pages/paper.js, optic.paper.v1), priced at each position's entry. */
export function paperBook() {
  try { const b = JSON.parse(localStorage.getItem('optic.paper.v1') || 'null'); return b && Array.isArray(b.open) ? b.open.map((p) => ({ ticker: p.ticker, qty: p.qty, price: p.entry_price, instrument: p.instrument })) : []; } catch (e) { return []; }
}
