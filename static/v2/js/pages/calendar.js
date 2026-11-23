// Markets, Calendar (round three): the session clock, the economic releases and the earnings week in one place, in the
// reader's own time zone (Settings, Time zone). Sessions come from /api/markets/calendar (app/session.py: holidays and
// 1:00 pm closes, which it already models); releases from the same answer (app/events.py, best effort, and named when
// it could not be read); the week's earnings from /api/earnings-week. Futures holidays are not modelled, and the page
// says so. "What moved today" is the Read page, linked from here. No model call.
import { html, render as draw } from '../core/dom.js';
import * as api from '../core/api.js';
import { clean, num } from '../core/format.js';
import { zone, zoneAbbrev } from '../core/prefs.js';
import { skeleton, failed } from '../ui/states.js';
import { provideContext } from '../ui/milo.js';
import { sectionHead } from './tabs.js';

let S = {}, live = true, mainEl = null;

/** A New York instant as a clock time in the reader's zone: "9:30 am". */
export function localTime(iso, z) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: z }).toLowerCase(); } catch (e) { return ''; }
}
/** One line for a day's session, in the reader's zone. */
export function sessionLine(d, z) {
  if (d.status === 'weekend') return 'Closed, weekend';
  if (d.status === 'holiday') return `Closed, ${d.name}`;
  const span = `${localTime(d.opens, z)} to ${localTime(d.closes, z)}`;
  return d.status === 'early_close' ? `Early close: ${span} (${d.name})` : `Open ${span}`;
}
const dayWords = (iso) => { try { return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' }); } catch (e) { return iso; } };

function sessions() {
  const c = S.cal;
  if (S.calErr) return failed('The session calendar', S.calErr, { retry: 'calendar' });
  if (!c) return skeleton('rows', 5, 'Loading the sessions');
  const z = zone(), abbr = zoneAbbrev(z);
  return html`<p class="section-sub">US stock market sessions for the next two weeks, in your time zone (${abbr}). Holidays and 1:00 pm New York closes come from the exchange calendar's rules.</p>
    <div class="tscroll" tabindex="0" aria-label="Market sessions"><table class="t" data-v2-cal-sessions><caption class="sr">US stock market sessions, in your time zone</caption>
      <thead><tr><th scope="col">Day</th><th scope="col">Session</th></tr></thead>
      <tbody>${c.days.map((d) => html`<tr data-v2-cal-day="${d.status}"><th scope="row">${dayWords(d.date)}</th><td class="${d.status === 'holiday' || d.status === 'early_close' ? 'cal-note' : d.status === 'weekend' ? 't-muted' : ''}">${sessionLine(d, z)}</td></tr>`)}</tbody></table></div>
    <p class="asof" data-v2-cal-futures>${clean(c.futures_note)}</p>`;
}
function releases() {
  const r = (S.cal || {}).releases;
  if (!r) return S.calErr ? '' : skeleton('rows', 3, 'Loading the releases');
  if (!r.available) return html`<p class="stale" role="status" data-v2-cal-releases="unavailable">${clean(r.reason || 'The release calendar could not be read just now.')}</p>`;
  const z = zone();
  const ev = (r.events || []).slice(0, 12);
  if (!ev.length) return html`<p>No scheduled releases in the window.</p>`;
  return html`<ul class="cal-list" data-v2-cal-releases>${ev.map((e) => html`<li><b>${dayWords(String(e.at || '').slice(0, 10))}</b> ${e.all_day ? '' : html`<span class="t-muted">${localTime(e.at, z)}</span>`} ${clean(e.title || '')}${e.impact ? html` <span class="t-muted">, ${clean(e.impact)} impact</span>` : ''}</li>`)}</ul>`;
}
function earnings() {
  const d = S.earn;
  if (S.earnErr) return failed('The earnings week', S.earnErr, { retry: 'earnings' });
  if (!d) return skeleton('rows', 3, 'Loading the earnings week');
  if (d.building) return html`<p class="asof" role="status">${clean(d.reason || 'Gathering the report dates.')} The full list is on <a class="textlink" href="#/earnings">Earnings this week</a>.</p>`;
  if (d.available === false) return html`<p>${clean(d.reason || 'The earnings calendar is not available right now.')}</p>`;
  const days = (d.days || []).filter((x) => x.count);
  return html`<p class="section-sub">${clean(d.week_label || 'This week')}: ${num(d.total || 0, 0)} reporting. <a class="textlink" href="#/earnings">The full week</a>.</p>
    ${days.length ? html`<ul class="cal-list" data-v2-cal-earnings>${days.map((x) => html`<li><b>${x.day} ${x.day_number}</b> ${(x.rows || []).slice(0, 8).map((r) => r.ticker).join(', ')}${x.count > 8 ? `, and ${x.count - 8} more` : ''}</li>`)}</ul>` : html`<p>No reports among the names Optic checks this week.</p>`}`;
}
function paint() {
  if (!live || !mainEl) return;
  draw(mainEl, html`<header class="page-head">${sectionHead('market', 'calendar')}</header>
    <p class="section-sub cal-moved">What moved today, and why: <a class="textlink" href="#/read">the Read</a>.</p>
    <section class="section first" aria-labelledby="cal-s"><h2 class="t-h2" id="cal-s">Sessions</h2>${sessions()}</section>
    <section class="section" aria-labelledby="cal-r"><h2 class="t-h2" id="cal-r">Economic releases</h2>${releases()}</section>
    <section class="section" aria-labelledby="cal-e"><h2 class="t-h2" id="cal-e">Earnings this week</h2>${earnings()}</section>`);
}
async function loadCal() {
  S.cal = null; S.calErr = null;
  try { S.cal = await api.get('/api/markets/calendar?days=14', { ttl: 300000, timeout: 30000 }); } catch (e) { S.calErr = e; }
  paint();
}
async function loadEarn() {
  S.earn = null; S.earnErr = null;
  try { S.earn = await api.get('/api/earnings-week?offset=0&quick=1', { ttl: 600000, timeout: 30000 }); } catch (e) { S.earnErr = e; }
  paint();
}
export async function render(main) {
  live = true; mainEl = main; S = {};
  document.title = 'Market calendar, Optic';
  provideContext(() => ({ view: 'calendar', calendar: S.cal ? { days: S.cal.days.slice(0, 7).map((d) => ({ date: d.date, status: d.status, name: d.name || null })) } : null }));
  paint();
  await Promise.all([loadCal(), loadEarn()]);
}
export function dispose() { live = false; }
export const retry = { calendar: () => loadCal(), earnings: () => loadEarn() };
