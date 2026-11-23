// Milo on every screen (round three, 2026-11-23). A strip under the top bar on every v2 route: one line offering a
// question about what is on this screen, and a control that opens Milo beside the page or collapses it back to the
// strip. Opened, Milo is the panel docked beside the page (ui/milo.js, ui/drawer.js), which stays open from page to
// page and takes the page's figures, the chart's timeframe or the metric in view with the question, as Pass 2 does.
// On a phone it rises as a sheet. The strip lives outside #main, so a page repaint never removes it; the shell draws
// it once and app.js repaints it on every route (paint).
//
// No modal, nothing moves on its own: the offer is a button, the toggle says what it will do and carries
// aria-expanded, and under reduced motion nothing animates (the panel's own transitions are already 0 there).
import { html, render, $ } from '../core/dom.js';
import { icon } from './icons.js';
import { openMilo, isOpen, closeMilo } from './milo.js';
import { press } from './miloprompt.js';

// One offer per screen, naming what is on it. {S} is the company's ticker when the route has one.
export const OFFERS = {
  home: 'Explain what moved on Home today',
  overview: 'Explain why {S} is moving today',
  financials: "Explain the chart in view on {S}'s Financials",
  long: "Explain the chart in view on {S}'s Investing page",
  earnings: "Explain {S}'s latest report and the chart in view",
  chart: 'Read this {S} chart: its trend, levels and studies',
  swing: "Explain {S}'s options chain and expected move",
  news: "What changed in {S}'s latest news",
  sheet: "Summarise {S}'s research sheet",
  instrument: 'Explain how {S} has moved',
  investigate: 'Walk me through this investigation of {S}',
  stockgrid: "Explain the panels on {S}'s company grid",
  insiders: 'What changed in these insider filings',
  analysts: 'What changed in these rating changes',
  brief: "Explain today's Read and what moved",
  market: 'Explain the macro picture on this page',
  indices: 'Explain how the major indexes are trending',
  earningsweek: "Explain this week's earnings calendar",
  explore: 'Explain what is moving in these sectors and themes',
  scan: 'Explain what this screen found',
  compare: 'Compare the companies on screen',
  watchlist: 'What moved on my watchlist today?',
  alerts: 'Explain the alerts that fired',
  saved: 'Summarise my saved research',
  brokerage: 'Describe the holdings in my linked accounts',
  tracker: "Explain the positions in Optic's model portfolio",
  paper: 'Explain the positions in my Paper Desk',
  roth: "Explain this retirement plan's mix",
  dossierstart: 'How do I research a company in Optic?',
  settings: 'Explain what each of these settings changes',
  signin: 'What can Milo do for me?',
  terms: 'Summarise this page in plain words',
  privacy: 'Summarise this privacy page in plain words',
  reports: 'Summarise the reports on this page',
  usage: 'Explain what the model has cost',
  accounts: 'Summarise the sign-ups on this page',
  metrics: 'Explain the figures on this Metrics page',
  notfound: 'Help me find the company I was looking for',
  // the screens round three added beside this module (Investor mode)
  portfolio: 'Explain how diversified my books are',
  calendar: "Explain what this week's calendar holds for the market",
  ownerreport: 'Explain the signals on this owner report',
  welcome: 'Explain what each level changes in Optic',
};
const DEFAULT_OFFER = 'Explain what is on this page';

/** The offer for a route: the screen's sentence with its ticker, or the page's own when the screen names none. */
export function offerFor(route) {
  const r = route || {}, sym = r.symbol ? String(r.symbol).toUpperCase() : '';
  const base = OFFERS[r.view] || DEFAULT_OFFER;
  if (base.includes('{S}')) return sym ? base.replace(/\{S\}/g, sym) : DEFAULT_OFFER;
  return base;
}

let current = { view: 'home' };

function strip() { return document.getElementById('milo-inline'); }

/** Draw the strip for `route`. Called by app.js on every route and by the toggle. */
export function paint(route) {
  if (route) current = route;
  const host = strip(); if (!host) return;
  const open = isOpen();
  const offer = offerFor(current);
  render(host, html`<aside class="milo-strip" aria-label="Milo on this screen" data-v2-milo-strip data-state="${open ? 'open' : 'strip'}" data-v2-milo-screen="${current.view || ''}">
    <span class="milo-strip-k" aria-hidden="true">${icon('milo')}</span>
    <button type="button" class="milo-strip-offer" data-v2-milo-offer><span class="milo-strip-ask">Ask Milo:</span> <span class="milo-strip-q" data-v2-milo-offer-text>${offer}</span></button>
    <button type="button" class="btn btn-quiet btn-sm milo-strip-toggle" data-v2-milo-strip-toggle aria-expanded="${open ? 'true' : 'false'}">${open ? 'Collapse Milo' : 'Open Milo'}</button>
  </aside>`);
}

/** Wire the strip once (app.js, at boot). */
export function wire() {
  const host = strip(); if (!host) return;
  host.addEventListener('click', (e) => {
    const off = e.target.closest('[data-v2-milo-offer]');
    if (off) {
      const question = offerFor(current);
      press(() => ({ question, screen: current.view || 'page', symbol: current.symbol || '', about: null }), off);
      setTimeout(() => paint(), 60);
      return;
    }
    const tog = e.target.closest('[data-v2-milo-strip-toggle]');
    if (tog) {
      if (isOpen()) { closeMilo(); setTimeout(() => { paint(); const t = $('[data-v2-milo-strip-toggle]', host); if (t) t.focus(); }, 0); }
      else { openMilo({ opener: tog }); setTimeout(() => paint(), 60); }
    }
  });
  // the panel closed by its own button or Escape: the strip says so
  document.addEventListener('click', (e) => { if (e.target.closest && e.target.closest('[data-v2-close]')) setTimeout(() => paint(), 0); }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setTimeout(() => paint(), 0); }, true);
}
