// Reports, the owner's four pages: Problem Reports (/api/feedback), Claude
// usage (/api/ai/usage), Accounts (/api/admin/accounts) and Metrics
// (/api/admin/metrics, counted in app/metrics.py). Owner only: the
// group shows only when /api/auth/me says admin, each page checks again before
// and after it fetches, and the server enforces it on every request. Nothing
// here calls a model.
import { html, render as draw } from '../core/dom.js';
import * as api from '../core/api.js';
import * as store from '../core/store.js';
import { clean, shortDate, fullDate } from '../core/format.js';
import { stamp, dayTime } from '../core/prefs.js';
import { skeleton, failed, how } from '../ui/states.js';
import { toast } from '../ui/toast.js';
import { groupTabs } from './tabs.js';

const TITLES = { reports: 'Problem Reports', usage: 'Claude usage', accounts: 'Accounts', metrics: 'Metrics', ownerreport: 'Owner report' };
let view = 'reports', D = {}, live = true, mainEl = null, tab = 'open', armedAll = null, seq = 0, params = {};
const isOwner = () => !!(store.state.me && store.state.me.admin);
const count = (n) => Number(n || 0).toLocaleString('en-US');

function notOwner() {
  if (view === 'reports') {
    return store.signedIn()
      ? html`<p>These are for the owner of this site. This account is not the owner's, or its address has not been verified yet.</p>`
      : html`<p>These are for the owner of this site. Sign in with the owner's address to read them.</p><a class="btn btn-sm" href="#/signin">Sign in</a>`;
  }
  return html`<p>This is for the owner of this site. Sign in with the owner's address to read it.</p>${store.signedIn() ? '' : html`<a class="btn btn-sm" href="#/signin">Sign in</a>`}`;
}
// a refusal is 401 or 403; a 503 is the server unable to answer ("The accounts database is unavailable"), which read
// as "These are not yours to read" to the owner (BUG-194, Phase 11)
const refused = (e) => e && (e.status === 401 || e.status === 403);
function errorBlock(e, what) {
  if (refused(e)) return failed('This page', null, { title: view === 'reports' ? 'These are not yours to read' : 'This is not yours to read', body: clean(e.message) });
  return failed(what, e, { retry: 'load' });
}

/* ---------------- Problem Reports ---------------- */
function reports() {
  const d = D.d;
  const total = d ? d.total : 0, open = d ? d.open : 0, resolved = d ? d.resolved : 0;
  const rows = (d && d.reports) || [];
  const lead = tab === 'resolved'
    ? (!resolved ? 'Nothing resolved yet.' : rows.length < resolved ? `Showing the ${rows.length} most recently resolved of ${resolved}.` : '')
    : (!open && resolved ? 'Nothing open.' : !total ? 'No problem reports yet. When a reader uses Report a Problem, it lands here.' : rows.length < open ? `Showing the newest ${rows.length} of ${open}.` : '');
  return html`<div class="seg" role="group" aria-label="Which reports"><button type="button" data-v2-rp-tab="open" aria-pressed="${tab === 'open'}">Open ${open}</button><button type="button" data-v2-rp-tab="resolved" aria-pressed="${tab === 'resolved'}">Resolved ${resolved}</button></div>
    <div class="cluster rp-lead">${lead ? html`<p class="t-muted">${lead}</p>` : ''}${tab === 'open' && open ? html`<button type="button" class="btn btn-sm" data-v2-rp-all>${armedAll ? `Resolve all ${open}? Press again to confirm` : `Resolve all ${open}`}</button>` : ''}</div>
    ${d.delivery && d.delivery.available === false ? html`<p class="asof">Email delivery is off. ${clean(d.delivery.reason || 'Reports are stored here and not emailed.')}</p>` : ''}
    <ol class="rp-list">${rows.map((r) => html`<li class="rp ${r.resolved_at ? 'is-resolved' : ''}">
      <div class="split"><p class="t-label">Filed ${stamp(r.created_at)}, ${r.emailed ? 'emailed' : 'stored'}</p>
        <button type="button" class="btn btn-sm" data-v2-rp-resolve="${r.id}" data-v2-rp-to="${r.resolved_at ? '0' : '1'}">${r.resolved_at ? 'Reopen' : 'Mark resolved'}</button></div>
      <p class="rp-msg">${r.message}</p>
      <p class="t-muted">${r.reporter_email ? html`From <a href="mailto:${r.reporter_email}">${r.reporter_email}</a>` : 'No account: sent before reports needed one'}</p>
      <p class="asof">${[r.page ? `Page: ${r.page}` : '', r.reply_to ? `Reply to: ${r.reply_to}` : '', r.user_agent || ''].filter(Boolean).join('. ')}</p>
      ${r.resolved_at ? html`<p class="asof">Resolved ${stamp(r.resolved_at)}</p>` : ''}</li>`)}</ol>`;
}

/* ---------------- Claude usage ---------------- */
function usd(b) {
  if (!b) return 'n/a';
  const v = b.cost_usd;
  if (v === null || v === undefined) return 'no price';
  const s = v > 0 && v < 0.005 ? '<$0.01' : `$${v.toFixed(2)}`;
  return b.unpriced ? `${s} + unpriced` : s;
}
function usage() {
  const d = D.d;
  if (d.available === false) return html`<p>${clean(d.reason || 'The usage ledger could not be read.')}</p>`;
  const f = d.features || [], t = d.totals || {}, noKey = D.health && D.health.assistant && D.health.assistant.enabled === false;
  const lead = f.length ? `What the model has cost this deployment, by feature. Recorded since ${stamp(d.since)}.`
    : noKey ? 'No calls recorded. The assistant has no key, so nothing calls Claude and nothing is recorded until it has one.'
      : 'No calls recorded yet. Every call to Claude is recorded here from this deploy on.';
  const row = (label, x) => html`<td>${usd(x.today)}</td><td>${usd(x.week)}</td><td>${usd(x.month)}</td><td class="n">${count((x.month || {}).calls)}</td><td class="n">${count((x.month || {}).unused)}</td><td class="n">${count((x.month || {}).failed)}</td>`;
  return html`<p class="section-sub">${lead}</p>
    ${f.length ? html`<div class="tscroll"><table class="t usage-t"><caption class="sr">Cost by feature</caption><thead><tr><th scope="col">Feature</th><th scope="col">Today</th><th scope="col">7 days</th><th scope="col">30 days</th><th scope="col" class="n" title="Calls in the last 30 days">Calls</th><th scope="col" class="n" title="Answers written but thrown away, 30 days">Unused</th><th scope="col" class="n" title="Calls that failed, 30 days">Failed</th></tr></thead>
      <tbody>${f.map((x) => html`<tr><th scope="row">${x.label || x.feature}</th>${row(x.label, x)}</tr>`)}</tbody>
      <tfoot><tr><th scope="row">Total</th>${row('Total', t)}</tr></tfoot></table></div>` : ''}
    ${d.method ? html`<p class="asof">${clean(d.method)}</p>` : ''}
    ${(d.recent || []).length ? html`<h2 class="t-h2" style="margin-top:32px">Latest calls</h2><div class="tscroll"><table class="t"><thead><tr><th scope="col">When</th><th scope="col">Feature</th><th scope="col">Model</th><th scope="col" class="n">Input</th><th scope="col" class="n">Output</th><th scope="col" class="n">Cost</th><th scope="col">Result</th></tr></thead>
      <tbody>${d.recent.slice(0, 25).map((c) => html`<tr><td>${dayTime(c.at)}</td><td>${c.label || c.feature}</td><td>${c.model || ''}</td><td class="n">${count(c.input_tokens)}</td><td class="n">${count(c.output_tokens)}</td><td class="n">${c.cost_usd === null || c.cost_usd === undefined ? 'no price' : usd({ cost_usd: c.cost_usd })}</td>
        <td title="${c.note || ''}">${c.stop_reason === 'error' ? 'Failed' : c.used === false ? 'Thrown away' : 'Used'}</td></tr>`)}</tbody></table></div>` : ''}`;
}

/* ---------------- Accounts ---------------- */
function accounts() {
  const d = D.d, a = d.accounts || [];
  const lead = d.total ? `${d.total} account${d.total === 1 ? '' : 's'}. ${d.last_7_days} new in the last 7 days, ${d.last_30_days} in the last 30. ${d.verified} with a verified email.` : 'Nobody has made an account yet.';
  const when = (v, absent) => (v === undefined ? absent : v ? stamp(v) : 'Never');
  return html`<p class="section-sub">${lead}</p>
    ${a.length ? html`<div class="tscroll ac-scroll" tabindex="0" role="region" aria-label="Accounts table, scrolls sideways"><table class="t ac-t"><thead><tr><th scope="col">Person</th><th scope="col">Joined</th><th scope="col">Last active</th><th scope="col">Last sign-in</th><th scope="col">Signs in with</th><th scope="col">Status</th></tr></thead>
      <tbody>${a.map((x) => html`<tr><th scope="row"><b>${[x.first_name, x.last_name].filter(Boolean).join(' ') || '(no name)'}</b><br><small class="t-muted ac-mail">${x.email}</small></th>
        <td>${stamp(x.created_at)}</td><td>${when(x.last_active_at, 'Not recorded')}</td><td>${when(x.last_login_at, 'Never')}</td><td>${(x.methods || []).join(', ') || 'None'}</td>
        <td>${x.is_active === false ? 'Deactivated' : x.email_verified ? 'Verified' : 'Not verified'}</td></tr>`)}</tbody></table></div>` : ''}
    <p class="asof">Newest first. Last active is the last time the account used Optic; last sign-in is the last time it entered a password, passkey or provider. No passwords or tokens are shown or kept here.</p>`;
}

/* ---------------- Metrics ---------------- */
const pct = (v) => (v === null || v === undefined ? '' : `${Math.round(Number(v))}%`);
/* ---------------- the three signals and the front end (2026-11-09) ----------------
 * Raw counts of the owner's three signals (app/usage.py): a company opened from Home, a question to Milo, and visits
 * with returns within a week, signed-in and signed-out readers alike. Counts only; the reporting page is a later
 * round. And which front end the public gets, with the one setting that changes it (app/frontend.py). */
function frontEnd() {
  const f = (D.health || {}).frontend;
  if (!f) return html`<p class="asof" data-v2-frontend>The front end in use could not be read just now.</p>`;
  return html`<p class="asof" data-v2-frontend="${f.active}">Front end for the public: <b>${f.active === 'v2' ? 'the new design (v2)' : 'the classic app'}</b>. ${f.classic
    ? `Classic is on (${f.setting}=on); remove the setting or set it to off, and restart, to serve the new design to everyone.`
    : `Classic is off. To turn it back on, set ${f.setting}=on and restart.`}</p>`;
}
function signals() {
  const g = D.signals;
  if (!g) return '';
  if (g.available === false) return html`<section class="section" aria-labelledby="sg-h"><h2 class="t-h2" id="sg-h">Your three signals</h2><p>${clean(g.reason || 'The usage records could not be read.')}</p></section>`;
  const w = g.windows || {}, cols = [['today', 'Today'], ['week', '7 days'], ['month', '30 days'], ['all', `Since ${g.since ? shortDate(g.since) : 'recording began'}`]];
  const cell = (k, f) => { const x = w[k] || {}; return f(x); };
  // with nobody a week old yet the figures are 0 of 0, which reads as a fault; one sentence says why there is no figure
  const back = g.returned_within_week || {};
  return html`<section class="section" aria-labelledby="sg-h"><h2 class="t-h2" id="sg-h">Your three signals</h2>
    <p class="section-sub">Raw counts, signed-in and signed-out readers together.${g.capture === false ? ' Recording is switched off (OPTIC_USAGE_CAPTURE=off).' : ''} Kept ${g.keep_days} days.</p>
    <div class="tscroll"><table class="t" data-v2-signals><caption class="sr">The three signals</caption>
      <thead><tr><th scope="col">Signal</th>${cols.map(([, l]) => html`<th scope="col" class="n">${l}</th>`)}</tr></thead>
      <tbody>
        <tr><th scope="row">Opened a stock from Home</th>${cols.map(([k]) => html`<td class="n">${cell(k, (x) => count((x.home_stock_open || {}).events))}</td>`)}</tr>
        <tr><th scope="row">Readers who did</th>${cols.map(([k]) => html`<td class="n">${cell(k, (x) => count((x.home_stock_open || {}).readers))}</td>`)}</tr>
        <tr><th scope="row">Asked Milo a question</th>${cols.map(([k]) => html`<td class="n">${cell(k, (x) => count((x.milo_question || {}).events))}</td>`)}</tr>
        <tr><th scope="row">Readers who did</th>${cols.map(([k]) => html`<td class="n">${cell(k, (x) => count((x.milo_question || {}).readers))}</td>`)}</tr>
        <tr><th scope="row">Visit days</th>${cols.map(([k]) => html`<td class="n">${cell(k, (x) => count((x.visit || {}).days))}</td>`)}</tr>
        <tr><th scope="row">Readers who visited</th>${cols.map(([k]) => html`<td class="n">${cell(k, (x) => count((x.visit || {}).readers))}</td>`)}</tr>
      </tbody></table></div>
    ${g.definition ? html`<p class="asof" data-v2-q-definition>${g.definition}</p>` : ''}
    ${g.readers_all_kinds_from ? html`<p class="asof" data-v2-readers-note>Readers who asked counts chat and deep research before ${fullDate(g.readers_all_kinds_from)} and every kind from then.</p>` : ''}
    ${g.owners_left_out ? html`<p class="asof" data-v2-signals-owner>Your own signed-in activity (your visits, the stocks you open from Home and your questions to Milo) is left out of these counts; what you do signed out cannot be told from a guest's and is counted.</p>` : ''}
    ${back.had_a_full_week ? html`<p data-v2-returned>Came back within a week of their first visit: <b>${count(back.readers)}</b> reader${back.readers === 1 ? '' : 's'}, of ${count(back.had_a_full_week)} whose first visit was at least a week ago.</p>`
    : html`<p data-v2-returned="none">Not enough history yet: the first readers have to be a week old before this can be counted.</p>`}
  </section>`;
}
function metrics() {
  const d = D.d, a = d.accounts || {}, weeks = d.weeks || [], cohorts = (d.retention || {}).cohorts || [];
  const q = d.questions || {}, kinds = q.by_kind || [], calls = d.model_calls || {}, since = d.tracking_since;
  const left = d.owners_left_out ? ` Your own account${d.owners_left_out === 1 ? ' is' : 's are'} left out of every count.` : '';
  const lead = a.total ? `${count(a.total)} account${a.total === 1 ? '' : 's'}: ${count(a.active_7_days)} used Optic in the last 7 days and ${count(a.active_30_days)} in the last 30.${left}`
    : `Nobody but you has made an account yet.${left}`;
  const wk = (w) => `${shortDate(w.week_start)}${w.partial ? ', so far' : ''}`;
  const active = (w) => (w.active_accounts === null || w.active_accounts === undefined ? html`<span class="t-muted">Not recorded</span>`
    : html`${count(w.active_accounts)}${w.active_from ? html` <small class="t-muted">from ${shortDate(w.active_from)}</small>` : ''}`);
  const shown = weeks.slice().reverse(), recent = cohorts.slice().reverse();
  const anyQ = kinds.some((k) => k.all);
  return html`${frontEnd()}${modesBlock()}<p class="section-sub">${lead}</p>
    ${signals()}
    <dl class="kv mt-kv"><div><dt>Accounts</dt><dd>${count(a.total)}</dd></div><div><dt>Active, 7 days</dt><dd>${count(a.active_7_days)}</dd></div><div><dt>Active, 30 days</dt><dd>${count(a.active_30_days)}</dd></div><div><dt>Verified email</dt><dd>${count(a.verified)}</dd></div></dl>

    <h2 class="t-h2 mt-h">Sign-ups and weekly active accounts</h2>
    <p class="asof">Weeks start on Monday (UTC). An active account opened Optic while signed in that week.${since ? ` Weekly actives are recorded from ${fullDate(since)}; earlier weeks were not kept.` : ''}</p>
    <div class="tscroll"><table class="t mt-t"><caption class="sr">Sign-ups and active accounts by week, newest first</caption><thead><tr><th scope="col">Week of</th><th scope="col" class="n">Sign-ups</th><th scope="col" class="n">Verified</th><th scope="col" class="n">Active accounts</th></tr></thead>
      <tbody>${shown.map((w) => html`<tr><th scope="row">${wk(w)}</th><td class="n">${count(w.signups)}</td><td class="n">${count(w.verified)}</td><td class="n">${active(w)}</td></tr>`)}</tbody></table></div>

    <h2 class="t-h2 mt-h">Came back after four weeks</h2>
    <p class="asof">For each sign-up week: of the accounts at least ${count((d.retention || {}).days || 28)} days old, how many used Optic again ${count((d.retention || {}).days || 28)} days or more after signing up.</p>
    <div class="tscroll"><table class="t mt-t"><caption class="sr">Four-week retention by sign-up week, newest first</caption><thead><tr><th scope="col">Week of</th><th scope="col" class="n">Sign-ups</th><th scope="col" class="n">Old enough</th><th scope="col" class="n">Came back</th></tr></thead>
      <tbody>${recent.map((c) => html`<tr><th scope="row">${shortDate(c.week_start)}</th><td class="n">${count(c.signups)}</td><td class="n">${count(c.measurable)}</td><td class="n">${c.measurable ? html`${count(c.retained)} <small class="t-muted mt-new">(${pct(c.retained_pct)})</small>` : c.signups ? html`<span class="t-muted mt-new">Too new</span>` : ''}</td></tr>`)}</tbody></table></div>

    <h2 class="t-h2 mt-h">Questions to Milo</h2>
    <p class="asof">${q.definition ? html`<span data-v2-q-definition>${q.definition}</span>` : ''}${since ? ` Counted from ${fullDate(since)}.` : ''} In the last 7 days, ${count(q.askers_7_days)} account${q.askers_7_days === 1 ? '' : 's'} asked, and guests asked ${count(q.guest_questions_7_days)}.${q.owner_questions_left_out ? ` Your own ${q.owner_questions_left_out === 1 ? 'question is' : `${count(q.owner_questions_left_out)} questions are`} left out.` : ''}</p>
    ${anyQ ? html`<div class="tscroll"><table class="t mt-t"><caption class="sr">Questions to Milo by where they were asked</caption><thead><tr><th scope="col">Asked through</th><th scope="col" class="n">7 days</th><th scope="col" class="n">30 days</th><th scope="col" class="n">Since counting began</th></tr></thead>
      <tbody>${kinds.map((k) => html`<tr><th scope="row">${k.label}</th><td class="n">${count(k.last_7_days)}</td><td class="n">${count(k.last_30_days)}</td><td class="n">${count(k.all)}</td></tr>`)}${q.total ? html`<tr data-v2-q-total><th scope="row">${q.total.label || 'All questions'}</th><td class="n">${count(q.total.last_7_days)}</td><td class="n">${count(q.total.last_30_days)}</td><td class="n">${count(q.total.all)}</td></tr>` : ''}</tbody></table></div>` : html`<p>No questions counted yet.</p>`}

    ${calls.available === false ? html`<p class="asof">${clean(calls.reason || 'The usage ledger could not be read.')}</p>` : (calls.features || []).length ? html`<h3 class="t-h3 mt-h3">Model calls by feature</h3>
      <p class="asof">Calls to Claude, not questions: one Milo answer can take several, and the Read and the desk write on a schedule. These include your own use. Costs are on Claude usage.</p>
      <div class="tscroll"><table class="t mt-t"><caption class="sr">Model calls by feature</caption><thead><tr><th scope="col">Feature</th><th scope="col" class="n">7 days</th><th scope="col" class="n">30 days</th></tr></thead>
        <tbody>${calls.features.map((f) => html`<tr><th scope="row">${f.label}</th><td class="n">${count(f.last_7_days)}</td><td class="n">${count(f.last_30_days)}</td></tr>`)}</tbody></table></div>` : ''}

    <h2 class="t-h2 mt-h">Plans</h2>
    <div class="tscroll"><table class="t mt-t"><caption class="sr">Accounts by plan</caption><thead><tr><th scope="col">Plan</th><th scope="col" class="n">Accounts</th></tr></thead>
      <tbody>${(d.plans || []).map((p) => html`<tr><th scope="row">${p.label}</th><td class="n">${count(p.accounts)}</td></tr>`)}</tbody></table></div>
    ${how(html`<p>Everything here is counted from Optic's own database. Nothing is sent to an analytics service, and nothing records which pages were viewed or what was asked.</p>
      <p>An account counts as active on a day it loaded Optic while signed in, or signed in. Visitors who never sign in are not counted, except as guest questions to Milo.</p>
      <p>The plan is the one Optic's limits read: a lapsed subscription counts as Free.</p>`)}
    <p class="asof">Counted ${stamp(d.generated_at)}.</p>`;
}

/* ---------------- the modes round three adds (app/health_extra.py), as /api/health reports them ---------------- */
// Billing, the legal text, alert delivery, the chart feed's history limit, Milo's off-topic set and which pages Watchlist
// and Portfolio are: each module reports its own mode, and this lists whatever is registered, so a mode added later
// shows here without a change to this page.
const MODE_NAMES = { billing: 'Billing', legal_text: 'Terms and privacy text', alert_delivery: 'Alert delivery', chart_history: 'Chart history',
  milo_offtopic: "Milo's off-topic set", investor_pages: 'Watchlist and Portfolio pages' };
const words = (k) => MODE_NAMES[k] || capWords(k);
const capWords = (k) => String(k).replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
function modeValue(v) {
  if (v === null || v === undefined) return html`<span class="t-muted">Not reported</span>`;
  if (Array.isArray(v)) return v.length ? v.map((x) => clean(String(x))).join(', ') : html`<span class="t-muted">none</span>`;
  if (typeof v === 'object') return html`<dl class="mt-modes-in">${Object.entries(v).map(([k, x]) => html`<div><dt>${capWords(k)}</dt><dd>${modeValue(x)}</dd></div>`)}</dl>`;
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  return clean(String(v));
}
function modesBlock() {
  const m = (D.health || {}).modes;
  if (!m) return html`<p class="asof" data-v2-modes="none">The site's modes could not be read just now.</p>`;
  const keys = Object.keys(m);
  if (!keys.length) return '';
  return html`<section class="section" aria-labelledby="md-h" data-v2-modes><h2 class="t-h2" id="md-h">How this site is set</h2>
    <p class="section-sub">Each line is reported by the part of Optic that decides it, the same as /api/health says.</p>
    <dl class="kv mt-modes">${keys.map((k) => html`<div data-v2-mode="${k}"><dt>${words(k)}</dt><dd>${modeValue(m[k])}</dd></div>`)}</dl></section>`;
}

/* ---------------- the owner report: what people open, which level they use, and the three signals ---------------- */
// Counts and weekly series only, never a part of a whole: on the handful of readers a new site has, a figure
// over a small number reads as more than it is (refinement A8). The group in the address (owner_kind, owner_id) is
// passed to the server, which today reads everyone and says so; the organization round reads one group with it.
const EVENT_NAMES = { home_stock_open: 'Opened a stock from Home', milo_question: 'Asked Milo a question', visit: 'Visited (first visit of a day)' };
const LEVEL_NAMES = { beginner: 'Beginner', intermediate: 'Intermediate', advanced: 'Advanced', 'not recorded': 'Not recorded' };
function ownerReport() {
  const d = D.d || {}, m = d.last_30_days || {}, weeks = (d.weeks || []).slice().reverse(), g = d.group || {};
  const sig = (x, e) => ((x.signals || {})[e] || {});
  const lv = (x) => (x.levels || []).map((l) => `${LEVEL_NAMES[l.level] || l.level} ${count(l.events)}`).join(', ') || 'none';
  return html`<p class="section-sub">Counted from Optic's own database: the three events recorded since round one, the screen each happened on and the reader's level at the time.${d.owners_left_out ? ' Your own signed-in activity is left out.' : ''}</p>
    <p class="asof" data-v2-or-group="${g.applied || 'everyone'}">Group: <b>everyone</b>.${g.note ? ` ${clean(g.note)}` : ''}</p>
    <section class="section" aria-labelledby="or-30"><h2 class="t-h2" id="or-30">The last 30 days</h2>
      <div class="tscroll" tabindex="0" aria-label="The three signals over the last 30 days"><table class="t mt-t" data-v2-or-signals><caption class="sr">The three signals over the last 30 days</caption>
        <thead><tr><th scope="col">Signal</th><th scope="col" class="n">Events</th><th scope="col" class="n">Readers</th></tr></thead>
        <tbody>${Object.keys(EVENT_NAMES).map((e) => html`<tr><th scope="row">${EVENT_NAMES[e]}</th><td class="n">${count(sig(m, e).events)}</td><td class="n">${count(sig(m, e).readers)}</td></tr>`)}
          <tr><th scope="row">Came back within a week of a first visit</th><td class="n">${count((m.came_back || {}).readers)}</td><td class="n">of ${count((m.came_back || {}).had_a_full_week)} a week old</td></tr></tbody></table></div>
      <h3 class="t-h3 mt-h3">Which level readers use</h3>
      <div class="tscroll" tabindex="0" aria-label="Events by level over the last 30 days"><table class="t mt-t" data-v2-or-levels><caption class="sr">Events by level over the last 30 days</caption>
        <thead><tr><th scope="col">Level</th><th scope="col" class="n">Events</th></tr></thead>
        <tbody>${(m.levels || []).length ? m.levels.map((l) => html`<tr><th scope="row">${LEVEL_NAMES[l.level] || l.level}</th><td class="n">${count(l.events)}</td></tr>`) : html`<tr><td colspan="2">Nothing recorded yet.</td></tr>`}</tbody></table></div>
      <h3 class="t-h3 mt-h3">What people open</h3>
      <div class="tscroll" tabindex="0" aria-label="Screens where the events happened over the last 30 days"><table class="t mt-t" data-v2-or-screens><caption class="sr">Screens where the events happened over the last 30 days</caption>
        <thead><tr><th scope="col">Screen</th><th scope="col">Event</th><th scope="col" class="n">Events</th></tr></thead>
        <tbody>${(m.screens || []).length ? m.screens.map((x) => html`<tr><th scope="row">${clean(x.screen)}</th><td>${EVENT_NAMES[x.event] || x.event}</td><td class="n">${count(x.events)}</td></tr>`) : html`<tr><td colspan="3">Nothing recorded yet.</td></tr>`}</tbody></table></div>
      ${(m.symbols || []).length ? html`<p data-v2-or-symbols>Stocks opened from Home most: ${m.symbols.map((x) => `${x.symbol} ${count(x.opens)}`).join(', ')}.</p>` : ''}
    </section>
    <section class="section" aria-labelledby="or-wk"><h2 class="t-h2" id="or-wk">Week by week</h2>
      <p class="asof">Weeks start on Monday (UTC), newest first. "Came back" counts readers whose first visit fell in that week and who visited again within seven days.</p>
      <div class="tscroll" tabindex="0" aria-label="The three signals and levels by week"><table class="t mt-t" data-v2-or-weeks><caption class="sr">The three signals and levels by week, newest first</caption>
        <thead><tr><th scope="col">Week of</th><th scope="col" class="n">Stocks opened from Home</th><th scope="col" class="n">Milo questions</th><th scope="col" class="n">Visit days</th><th scope="col" class="n">Came back</th><th scope="col">Levels</th></tr></thead>
        <tbody>${weeks.map((w) => html`<tr><th scope="row">${shortDate(w.week)}</th><td class="n">${count(sig(w, 'home_stock_open').events)}</td><td class="n">${count(sig(w, 'milo_question').events)}</td><td class="n">${count(sig(w, 'visit').events)}</td><td class="n">${count((w.came_back || {}).readers)} of ${count((w.came_back || {}).had_a_full_week)}</td><td>${lv(w)}</td></tr>`)}</tbody></table></div></section>
    ${how(html`<p>${clean(d.what_is_counted || '')}</p><p>The group in the address is for the organization round: it is read by the server and, until groups exist, every count is everyone's.</p>`)}
    <p class="asof">Counted ${stamp(d.generated_at)}.</p>`;
}
/* ---------------- end of the owner report ---------------- */

/* ---------------- page ---------------- */
function paint() {
  if (!live) return;
  const what = { reports: 'The reports', usage: 'The usage ledger', accounts: 'The accounts', metrics: 'The metrics', ownerreport: 'The owner report' }[view];
  const body = !isOwner() ? notOwner() : D.err ? errorBlock(D.err, what) : !D.d ? skeleton('rows', 5, 'Loading')
    : view === 'reports' ? reports() : view === 'usage' ? usage() : view === 'metrics' ? metrics() : view === 'ownerreport' ? ownerReport() : accounts();
  draw(mainEl, html`<header class="page-head"><h1 class="t-display-m">${TITLES[view]}</h1>${isOwner() ? groupTabs('reports', view) : ''}</header>
    <section class="section first" aria-label="${TITLES[view]}">${body}</section>`);
}

async function load() {
  const my = ++seq; D.err = null;
  if (!isOwner()) { paint(); return; }
  if (!D.d) paint();
  try {
    let d;
    if (view === 'reports') d = await api.get(`/api/feedback?limit=50&status=${tab}`, { force: true, timeout: 20000 });
    else if (view === 'usage') { [d, D.health] = await Promise.all([api.get('/api/ai/usage', { force: true }), api.get('/api/health', { ttl: 60000 }).catch(() => null)]); }
    else if (view === 'metrics') { [d, D.signals, D.health] = await Promise.all([api.get('/api/admin/metrics', { force: true }), api.get('/api/admin/usage-signals', { force: true }).catch((e) => ({ available: false, reason: e.message })), api.get('/api/health', { ttl: 0, force: true }).catch(() => null)]); }
    else if (view === 'ownerreport') {
      const q = new URLSearchParams(); ['owner_kind', 'owner_id'].forEach((k) => { if (params[k]) q.set(k, params[k]); });
      d = await api.get(`/api/admin/owner-report${q.toString() ? `?${q}` : ''}`, { force: true, timeout: 20000 });
    } else d = await api.get('/api/admin/accounts', { force: true });
    if (my !== seq || !live || !isOwner()) return;
    D.d = d;
  } catch (e) { if (my !== seq) return; D.err = e; D.d = null; }
  paint();
}

export async function render(main, route) {
  live = true; mainEl = main; view = route.view; D = {}; armedAll = null; params = route.params || {};
  document.title = `${TITLES[view]}, Optic`;
  main.addEventListener('click', async (e) => {
    const t = (s) => e.target.closest(s); let b;
    if ((b = t('[data-v2-rp-tab]'))) { tab = b.dataset.v2RpTab; armedAll = null; D.d = null; load(); return; }
    if ((b = t('[data-v2-rp-resolve]'))) {
      b.disabled = true;
      try { await api.post(`/api/feedback/${encodeURIComponent(b.dataset.v2RpResolve)}/resolve`, { resolved: b.dataset.v2RpTo === '1' }); toast(b.dataset.v2RpTo === '1' ? 'Marked resolved.' : 'Reopened.'); }
      catch (err) { toast(`That did not go through: ${api.explain(err, 'The change')}`); }
      await load(); return;
    }
    if (t('[data-v2-rp-all]')) {
      if (!armedAll) { armedAll = setTimeout(() => { armedAll = null; paint(); }, 5000); paint(); const again = mainEl.querySelector('[data-v2-rp-all]'); if (again) again.focus(); return; }
      clearTimeout(armedAll); armedAll = null;
      try { const r = await api.post('/api/feedback/resolve-all', {}); toast(`Resolved ${r.resolved}.`); } catch (err) { toast(`That did not go through: ${api.explain(err, 'The change')}`); }
      load();
    }
  });
  load();
}
export function dispose() { live = false; clearTimeout(armedAll); }
export const retry = { load: () => load() };
// sign-in or sign-out redraws: the owner check runs again
export function onAuth() { D = {}; load(); }
