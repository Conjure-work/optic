// Portfolio, with one meaning (round three). #/portfolio is the reader's own books: a linked brokerage first, the
// Paper Desk second on the same page, never hidden, and Optic's three model books last, named as Optic's. A plain line
// says which books are the reader's. The diversification figure (app/analytics/portfolio_risk.py, the measure the
// model books already used) follows whichever book is in view. Retirement stays its own tool, linked from here.
//
// The owner's setting OPTIC_SEPARATE_ALERTS_AND_MODELS=on opens Optic's model books at #/portfolio again, as before
// round three (core/investorpages.js); the model books keep their own page at #/models either way.
import { html, render as draw } from '../core/dom.js';
import * as api from '../core/api.js';
import * as store from '../core/store.js';
import { holds } from '../core/device.js';
import { num, money, clean, isNum } from '../core/format.js';
import { skeleton, failed } from '../ui/states.js';
import { provideContext } from '../ui/milo.js';
import { sectionHead } from './tabs.js';
import { separate } from '../core/investorpages.js';

const PAPER_KEY = 'optic.paper.v1';
const MODEL_BOOKS = [['conservative', 'Conservative'], ['balanced', 'Balanced'], ['aggressive', 'Aggressive']];
let S = {}, live = true, mainEl = null, delegate = null;

/** The reader's Paper Desk, as this browser keeps it (pages/paper.js), or none. */
export function paperBook(user = store.state.user) {
  if (!holds(user)) return [];
  try { const raw = JSON.parse(localStorage.getItem(PAPER_KEY) || 'null'); return raw && Array.isArray(raw.open) ? raw.open : []; } catch (e) { return []; }
}
/** Which books are the reader's, in the order they are shown: brokerage first when one is linked, then the Paper Desk. */
export function readerBooks({ brokerageLinked, paperCount }) {
  const out = [];
  if (brokerageLinked) out.push('brokerage');
  out.push('paper');
  return { books: out, line: brokerageLinked
    ? `Your books: your linked brokerage, then your Paper Desk${paperCount ? ` (${paperCount} open)` : ''}. Optic's model portfolios are below, and they are Optic's, not yours.`
    : `Your book: your Paper Desk${paperCount ? `, ${paperCount} open` : ', empty so far'}. No brokerage is linked. Optic's model portfolios are below, and they are Optic's, not yours.` };
}
/** Positions in the shape the diversification read takes. */
export const asPositions = (rows, from) => rows.map((p) => (from === 'brokerage'
  ? { ticker: p.symbol, qty: p.quantity, entry_price: p.price, instrument: 'shares' }
  : { ticker: p.ticker, qty: p.qty, entry_price: p.entry_price, instrument: p.instrument === 'option' ? 'option' : 'shares', direction: p.direction, option_type: p.option_type, strike: p.strike, expiry: p.expiry }));

const BOOK_NAME = { brokerage: 'Your brokerage', paper: 'Your Paper Desk', conservative: "Optic's conservative model", balanced: "Optic's balanced model", aggressive: "Optic's aggressive model" };

function risk() {
  const r = S.risk[S.view];
  const name = BOOK_NAME[S.view];
  if (r === undefined) return skeleton('lines', 2, `Measuring ${name}`);
  if (!r || r.error) return failed(`${name}'s diversification`, (r || {}).error, { retry: 'risk' });
  if (!r.available) return html`<p data-v2-pf-div="none">${clean(r.reason || 'Not enough to measure.')}</p>`;
  const dr = r.diversification_ratio;
  return html`<dl class="kv" style="--kv:3" data-v2-pf-div="${S.view}">
    <div><dt>Diversification ratio</dt><dd>${dr === null || dr === undefined ? 'n/a' : num(dr, 2)}</dd><p class="kv-note">1.0 means nothing is cancelling</p></div>
    <div><dt>Effective positions</dt><dd>${isNum(r.effective_positions) ? num(r.effective_positions, 1) : 'n/a'}</dd><p class="kv-note">of ${num(r.names, 0)} held</p></div>
    <div><dt>Gross exposure</dt><dd>${isNum(r.gross_exposure) ? money(r.gross_exposure, 0) : 'n/a'}</dd></div></dl>
    ${r.verdict ? html`<p>${clean(r.verdict)}</p>` : ''}`;
}

function brokerageBlock() {
  if (!S.brokerage) return '';
  const b = S.brokerage;
  if (b.error) return failed('Your brokerage', b.error, { retry: 'brokerage' });
  const hs = (b.holdings || []).filter((h) => h.symbol).slice(0, 12);
  return html`<section class="section first" aria-labelledby="pf-bk"><h2 class="t-h2" id="pf-bk">Your brokerage</h2>
    <p class="section-sub">Read only, from the accounts you linked. The full view is on <a class="textlink" href="#/brokerage/overview">Brokerage</a>.</p>
    ${hs.length ? html`<div class="tscroll" tabindex="0" aria-label="Your brokerage holdings"><table class="t"><caption class="sr">Your brokerage holdings</caption><thead><tr><th scope="col">Holding</th><th scope="col" class="n">Quantity</th><th scope="col" class="n">Price</th></tr></thead>
      <tbody>${hs.map((h) => html`<tr><th scope="row"><a href="#/${encodeURIComponent(h.symbol)}">${h.symbol}</a></th><td class="n">${num(h.quantity, 2)}</td><td class="n">${isNum(h.price) ? money(h.price) : 'n/a'}</td></tr>`)}</tbody></table></div>`
    : html`<p>No holdings were read from the linked accounts yet.</p>`}</section>`;
}
function paperBlock(first) {
  const open = S.paper;
  return html`<section class="section ${first ? 'first' : ''}" aria-labelledby="pf-pd"><h2 class="t-h2" id="pf-pd">Your Paper Desk</h2>
    <p class="section-sub">Practice trades you enter yourself, kept in this browser. Open the <a class="textlink" href="#/paper">Paper Desk</a> to trade or close them.</p>
    ${open.length ? html`<div class="tscroll" tabindex="0" aria-label="Your Paper Desk positions"><table class="t"><caption class="sr">Your Paper Desk positions</caption><thead><tr><th scope="col">Position</th><th scope="col">Side</th><th scope="col" class="n">Entry</th></tr></thead>
      <tbody>${open.slice(0, 20).map((p) => html`<tr><th scope="row"><a href="#/${encodeURIComponent(p.ticker)}">${p.qty} ${p.ticker}${p.instrument === 'option' ? ` ${num(p.strike)} ${p.option_type}` : ''}</a></th><td>${p.direction === 'short' ? 'Short' : 'Long'}</td><td class="n">${num(p.entry_price)}</td></tr>`)}</tbody></table></div>`
    : html`<p data-v2-pf-paper="empty">Nothing open on your Paper Desk. <a class="textlink" href="#/paper">Open a practice trade</a>.</p>`}</section>`;
}
function modelsBlock() {
  return html`<section class="section" aria-labelledby="pf-md" data-v2-pf-models><h2 class="t-h2" id="pf-md">Optic's model portfolios</h2>
    <p class="section-sub">Not yours: three simulated accounts that trade Optic's own signals with pretend money, the same for every reader. Their full record is on <a class="textlink" href="#/models">Optic's model portfolios</a>.</p></section>`;
}
function picker() {
  const opts = [...S.books, ...MODEL_BOOKS.map(([k]) => k)];
  return html`<div class="chips chips-scroll" role="group" aria-label="Measure the diversification of">${opts.map((k) => html`<button type="button" class="chip" data-v2-pf-book="${k}" aria-pressed="${S.view === k}">${BOOK_NAME[k]}</button>`)}</div>`;
}

function paint() {
  if (!live || !mainEl) return;
  const f = document.activeElement, keep = f && mainEl.contains(f) && f.dataset ? f.dataset.v2PfBook : null;
  draw(mainEl, html`<header class="page-head">${sectionHead('portfolio', 'portfolio')}
      <p class="pf-whose" data-v2-pf-line>${S.line}</p></header>
    ${S.loading ? skeleton('rows', 3, 'Loading your books') : html`
      ${brokerageBlock()}${paperBlock(!S.brokerage)}
      <section class="section" aria-labelledby="pf-dv"><h2 class="t-h2" id="pf-dv">Diversification</h2>
        <p class="section-sub">How much the positions in one book move together, from six months of daily returns. Choose the book.</p>
        ${picker()}<div aria-live="polite">${risk()}</div></section>
      ${modelsBlock()}
      <p class="asof">Planning for retirement is its own tool: <a class="textlink" href="#/retirement">Retirement</a>.</p>`}`);
  if (keep) { const b = mainEl.querySelector(`[data-v2-pf-book="${keep}"]`); if (b) b.focus({ preventScroll: true }); }
}

async function loadRisk(view) {
  if (S.risk[view] !== undefined && S.risk[view] !== null && !(S.risk[view] || {}).error) return;
  S.risk[view] = undefined; paint();
  try {
    if (view === 'paper' || view === 'brokerage') {
      const rows = view === 'paper' ? S.paper : ((S.brokerage || {}).holdings || []);
      const positions = asPositions(rows, view);
      S.risk[view] = positions.length ? await api.post('/api/portfolio-risk/positions', { positions }, { timeout: 70000 })
        : { available: false, reason: view === 'paper' ? 'Nothing open on your Paper Desk to measure.' : 'No holdings to measure.' };
    } else S.risk[view] = await api.get(`/api/portfolio-risk?book=${encodeURIComponent(view)}`, { ttl: 120000, timeout: 60000 });
  } catch (e) { S.risk[view] = { error: e }; }
  if (live) paint();
}

async function load() {
  S.paper = paperBook();
  let linked = false;
  if (store.signedIn()) {
    try {
      const p = await api.get('/api/brokerage/portfolio', { ttl: 60000, timeout: 30000 });
      if (p && p.available) { linked = true; S.brokerage = p; }
    } catch (e) { /* no brokerage, or none switched on: the reader's book is the Paper Desk */ }
  }
  const rb = readerBooks({ brokerageLinked: linked, paperCount: S.paper.length });
  S.books = rb.books; S.line = rb.line; S.view = rb.books[0]; S.loading = false;
  if (!live) return;
  paint();
  loadRisk(S.view);
}

export async function render(main, route) {
  live = true; mainEl = main; delegate = null;
  if (await separate()) {
    // the owner's setting: #/portfolio opens Optic's model books, as before round three
    delegate = await import('./tracker.js');
    if (!live) return;
    return delegate.render(main, route);
  }
  S = { risk: {}, loading: true, books: ['paper'], view: 'paper', paper: [], line: 'Loading your books.' };
  document.title = 'Portfolio, Optic';
  provideContext(() => ({ view: 'portfolio', portfolio: { books: S.books, in_view: S.view, paper_open: (S.paper || []).length } }));
  main.addEventListener('click', (e) => {
    const b = e.target.closest('[data-v2-pf-book]');
    if (b && !delegate) { S.view = b.dataset.v2PfBook; paint(); loadRisk(S.view); }
  });
  paint();
  await load();
}
export function dispose() { live = false; if (delegate && delegate.dispose) delegate.dispose(); }
export const retry = {
  risk: () => { S.risk[S.view] = null; loadRisk(S.view); },
  brokerage: () => load(),
  load: () => delegate && delegate.retry && delegate.retry.load ? delegate.retry.load() : load(),
};
export function onAuth() { if (live && !delegate) load(); }
