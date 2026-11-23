// The three kinds of alert gathered in one shape (round three: watchlists and alerts in one place).
//   yours      the conditions the reader set (watches) and what fired from them
//   optic      Optic's book: the scheduled scan's alerts, the same for every reader
//   brokerage  situations in the reader's linked brokerage account
// The three stores stay as they are (app/account.py watches, app/alerts.py, app/brokerage/alerts.py); this only
// reads them and gives every item the same fields, so the Watchlist's rows and its Alerts view draw them one way.
import * as api from './api.js';
import * as store from './store.js';

export const KINDS = [['yours', 'Yours'], ['optic', "Optic's book"], ['brokerage', 'Your brokerage']];
export const KIND_LABEL = Object.fromEntries(KINDS);

const sym = (s) => store.canon(String(s || '').toUpperCase());

/** Every item in one shape: { kind, symbol, title, at, fired, active }. Pure, so a test can run it in JavaScriptCore. */
export function normalise({ watches = [], hits = [], book = [], brokerage = [] } = {}) {
  const out = [];
  watches.forEach((w) => out.push({ kind: 'yours', symbol: sym(w.symbol), title: String(w.condition || w.label || w.kind || 'An alert you set'),
    at: w.last_met_at || w.created_at || null, fired: false, active: w.active !== false && w.active !== 0, id: `w:${w.id || out.length}` }));
  hits.forEach((h) => out.push({ kind: 'yours', symbol: sym(h.symbol), title: String(h.title || h.condition || 'Your alert fired'),
    at: h.created_at || null, fired: true, active: true, id: `h:${h.id || out.length}` }));
  book.forEach((a) => out.push({ kind: 'optic', symbol: sym(a.ticker || a.symbol), title: String(a.title || a.kind_label || 'From the book'),
    at: a.created_at || null, fired: true, active: true, id: `o:${a.id || out.length}` }));
  brokerage.forEach((a) => out.push({ kind: 'brokerage', symbol: sym(a.symbol || a.ticker), title: String(a.title || a.headline || a.summary || a.kind || 'About your holdings'),
    at: a.created_at || null, fired: true, active: true, id: `b:${a.id || out.length}` }));
  return out;
}

/** Per symbol: how many of each kind, and how many fired today. */
export function bySymbol(items, today = new Date().toISOString().slice(0, 10)) {
  const m = {};
  items.forEach((x) => {
    if (!x.symbol) return;
    const o = m[x.symbol] || (m[x.symbol] = { yours: 0, optic: 0, brokerage: 0, fired: 0 });
    if (x.kind === 'yours' && !x.fired) { if (x.active) o.yours += 1; } else if (x.kind !== 'yours') o[x.kind] += 1;
    if (x.fired && x.at && String(x.at).slice(0, 10) === today) o.fired += 1;
  });
  return m;
}

/** Newest first, fired items before standing ones; standing conditions last. */
export function ordered(items) {
  return items.slice().sort((a, b) => (b.fired ? 1 : 0) - (a.fired ? 1 : 0) || String(b.at || '').localeCompare(String(a.at || '')));
}

/** Read the three stores. A store that cannot be read is named in `missing`, never silently left out. */
export async function gather({ watches, hits, book } = {}) {
  const missing = [];
  const signed = store.signedIn();
  const jobs = [
    watches ? Promise.resolve(watches) : (signed ? api.get('/api/watches', { ttl: 30000 }).then((r) => (r || {}).watches || []) : Promise.resolve(localWatches())).catch(() => { missing.push('yours'); return []; }),
    hits ? Promise.resolve(hits) : (signed ? api.get('/api/watches/hits?limit=60', { ttl: 30000 }).then((r) => (r || {}).hits || []) : Promise.resolve([])).catch(() => []),
    book ? Promise.resolve(book) : api.get('/api/alerts?limit=60', { ttl: 60000 }).then((r) => (r || {}).alerts || []).catch(() => { missing.push('optic'); return []; }),
    // only a signed-in reader can have a linked brokerage; a refusal (none linked, brokerage off) is not a failure
    signed ? api.get('/api/brokerage/workspace/alerts', { ttl: 60000 }).then((r) => (r || {}).alerts || []).catch(() => []) : Promise.resolve([]),
  ];
  const [w, h, b, k] = await Promise.all(jobs);
  return { items: normalise({ watches: w, hits: h, book: b, brokerage: k }), missing };
}
function localWatches() { try { const v = JSON.parse(localStorage.getItem('optic.watches.v1') || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
