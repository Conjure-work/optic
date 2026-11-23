// The sign-up questions (round three): six optional questions that suggest how Optic should explain things, with one
// sentence of why. Skip is as large as Continue. The suggestion is written to the account only when the reader accepts
// it, and the level stays changeable in Settings and on Home. The answers are scored by the server and forgotten:
// only the suggested level, the outcome and that the questions were shown are kept (app/investor.py).
//
// Offered once to every new account, however it was made: straight after the sign-up form (pages/signin.js sends the
// reader here), and on the first signed-in visit of an account made with Google, Apple or a passkey, as a band above
// the page that can be answered or dismissed (offer(), called by app.js after sign-in). No dialog, no modal.
import { $, html, render as draw } from '../core/dom.js';
import * as api from '../core/api.js';
import * as store from '../core/store.js';
import * as prefs from '../core/prefs.js';
import { failed, skeleton } from '../ui/states.js';
import { toast } from '../ui/toast.js';

const LEVEL_NAME = { beginner: 'Beginner', intermediate: 'Intermediate', advanced: 'Advanced' };
let S = {}, live = true, mainEl = null;

const safeNext = (n) => (typeof n === 'string' && /^#\/[^\s]*$/.test(n) && !/^#\/welcome/.test(n) ? n : '#/');

function questionsForm() {
  return html`<form class="lq-form stack" data-v2-lq-form novalidate>
    ${S.questions.map((q, i) => html`<fieldset class="lq-q"><legend><span class="t-muted">${i + 1} of ${S.questions.length}.</span> ${q.text}</legend>
      <div class="lq-choices">${q.choices.map((c) => html`<label class="check"><input type="radio" name="${q.id}" value="${c.id}" ${S.answers[q.id] === c.id ? 'checked' : ''}> <span>${c.label}</span></label>`)}</div></fieldset>`)}
    <p class="form-error" role="alert">${S.error || ''}</p>
    <div class="lq-acts"><button type="submit" class="btn btn-primary lq-btn">Continue</button><button type="button" class="btn lq-btn" data-v2-lq-skip>Skip</button></div>
  </form>`;
}
function suggestion() {
  const s = S.suggestion;
  if (!s.suggested) {
    return html`<div class="lq-result" data-v2-lq-result="none"><p>Nothing was answered, so there is nothing to suggest. Your level stays ${LEVEL_NAME[prefs.knowledge()] || 'as it is'}.</p>
      <div class="lq-acts"><button type="button" class="btn btn-primary lq-btn" data-v2-lq-skip>Continue to Optic</button></div></div>`;
  }
  return html`<div class="lq-result" data-v2-lq-result="${s.suggested}"><h2 class="t-h2" tabindex="-1" id="lq-sug">Suggested level: ${LEVEL_NAME[s.suggested]}</h2>
    <p data-v2-lq-why>${s.why}</p>
    <p class="asof">You can change it at any time in Settings, or with the level control on Home.</p>
    <div class="lq-acts"><button type="button" class="btn btn-primary lq-btn" data-v2-lq-accept>Use ${LEVEL_NAME[s.suggested]}</button><button type="button" class="btn lq-btn" data-v2-lq-skip>Keep ${LEVEL_NAME[prefs.knowledge()] || 'my level'}</button></div></div>`;
}
function paint() {
  if (!live || !mainEl) return;
  draw(mainEl, html`<header class="page-head"><h1 class="t-display-m">How should Optic explain things?</h1>
      <p class="section-sub">Six optional questions. Answer any of them and Optic suggests a level, or skip; nothing changes until you choose. Your answers are not kept.</p></header>
    <section class="section first" aria-label="The questions">${S.err ? failed('The questions', S.err, { retry: 'load' }) : !S.questions ? skeleton('lines', 4, 'Loading the questions')
      : S.suggestion ? suggestion() : questionsForm()}</section>`);
}
async function finish(outcome) {
  try {
    const r = await api.post('/api/account/level-questions/decide', { outcome, suggested: (S.suggestion || {}).suggested || null });
    if (outcome === 'accepted' && r.knowledge_level) { prefs.setKnowledge(r.knowledge_level, { quiet: true }); toast(`Optic will explain things at ${LEVEL_NAME[r.knowledge_level]}.`); }
  } catch (e) { /* the level is not changed; the reader carries on */ }
  location.hash = S.next;
}
async function load() {
  S.err = null;
  if (!store.signedIn()) { location.hash = '#/signin'; return; }
  try {
    const r = await api.get('/api/account/level-questions', { ttl: 0, force: true });
    S.questions = r.questions || [];
    api.post('/api/account/level-questions/shown', {}).catch(() => {});
  } catch (e) { S.err = e; }
  paint();
}
export async function render(main, route) {
  live = true; mainEl = main; S = { answers: {}, next: safeNext((route.params || {}).next) };
  document.title = 'How should Optic explain things?, Optic';
  hideOffer();
  main.addEventListener('change', (e) => { if (e.target.matches('[data-v2-lq-form] input[type=radio]')) S.answers[e.target.name] = e.target.value; });
  main.addEventListener('submit', async (e) => {
    if (!e.target.closest('[data-v2-lq-form]')) return;
    e.preventDefault();
    try { S.suggestion = await api.post('/api/account/level-questions/suggest', { answers: S.answers }); S.error = ''; }
    catch (x) { S.error = api.explain(x, 'The suggestion'); }
    paint();
    const h = $('#lq-sug', mainEl) || $('[data-v2-lq-result] button', mainEl); if (h) h.focus();
  });
  main.addEventListener('click', (e) => {
    if (e.target.closest('[data-v2-lq-skip]')) { finish('skipped'); return; }
    if (e.target.closest('[data-v2-lq-accept]')) finish('accepted');
  });
  paint();
  await load();
}
export function dispose() { live = false; }
export const retry = { load: () => load() };

/* ---------------- the band, for an account made without the sign-up form ---------------- */
let band = null;
function hideOffer() { if (band) { band.remove(); band = null; } }
/** After a sign-in: if this account has never been shown the questions, a band above the page offers them once. */
export async function offer() {
  if (!store.signedIn() || band || /^#\/(welcome|signin)/.test(location.hash)) return;
  let r;
  try { r = await api.get('/api/account/level-questions', { ttl: 0, force: true }); } catch (e) { return; }
  if (!r || !r.offer || band) return;
  const main = document.getElementById('main'); if (!main) return;
  band = document.createElement('section');
  band.className = 'lq-offer'; band.setAttribute('aria-label', 'Set how Optic explains things'); band.dataset.v2LqOffer = '';
  draw(band, html`<p>Six optional questions can suggest how Optic explains things to you.</p>
    <div class="lq-acts"><a class="btn btn-sm lq-btn" href="#/welcome?next=${encodeURIComponent(location.hash || '#/')}" data-v2-lq-answer>Answer them</a><button type="button" class="btn btn-sm lq-btn" data-v2-lq-dismiss>Not now</button></div>`);
  main.before(band);
  // shown once: the band is the offer, so it is recorded as shown now and not offered again
  api.post('/api/account/level-questions/shown', {}).catch(() => {});
  band.addEventListener('click', (e) => {
    if (e.target.closest('[data-v2-lq-dismiss]')) { api.post('/api/account/level-questions/decide', { outcome: 'skipped' }).catch(() => {}); hideOffer(); const m = document.getElementById('main'); if (m) m.focus(); }
    if (e.target.closest('[data-v2-lq-answer]')) setTimeout(hideOffer, 0);
  });
}
export { hideOffer };
