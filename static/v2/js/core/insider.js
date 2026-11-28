// One reading of the six-month insider block for every surface (audit 2026-11-27, F01). Financials, Overview, the
// Home Ownership panel and the chart's Insiders widget all read the same `company.ownership` through this function,
// so they cannot disagree for a symbol, and a summary that was not read is never worded as "neutral", "even" or
// "no net buying or selling". The server decides the state (fundamentals.analyse_ownership); this words it.
import { num, signed, fullDate, isNum } from './format.js';

const noun = (n, one, many) => (n === 1 ? one : many);

/** @returns {{ state: 'ok'|'unavailable', signal: string, headline: string, line: string, short: string,
 *             counts: object, window: string, types: string, excluded: string }} */
export function insiderRead(ow) {
  const o = ow || {}, i6 = o.insider_6m || {};
  // an older cached payload has no state: the signal says it
  const state = o.insider_state || (o.insider_signal === 'unavailable' || i6.basis === 'unavailable' ? 'unavailable' : 'ok');
  const since = i6.since ? fullDate(i6.since) : '', until = i6.until ? fullDate(i6.until) : '';
  const window = since && until ? `${since} to ${until}` : 'the last six months';
  const span = since && until ? `from ${since} to ${until}` : 'over six months';
  const types = i6.types || 'Open-market purchases and sales, Form 4 codes P and S';
  const excluded = i6.excluded || 'awards, grants, gifts and option exercises';
  const counts = { purchases: isNum(i6.purchase_count) ? i6.purchase_count : null, sales: isNum(i6.sale_count) ? i6.sale_count : null,
    purchaseShares: isNum(i6.purchase_shares) ? i6.purchase_shares : null, saleShares: isNum(i6.sale_shares) ? i6.sale_shares : null,
    net: isNum(i6.net_shares) ? i6.net_shares : null, other: isNum(i6.other_count) ? i6.other_count : null };
  const base = { state, window, types, excluded, counts };
  if (state === 'unavailable') {
    const h = `Insider transactions for the six months${until ? ` to ${until}` : ''} are unavailable right now. That is not the same as no activity.`;
    return { ...base, signal: 'unavailable', headline: h, line: h, short: 'Unavailable' };
  }
  const open = i6.basis === 'open_market';
  const other = open && counts.other ? ` ${counts.other} ${noun(counts.other, 'award, grant or exercise', 'awards, grants and exercises')} not counted.` : '';
  const tally = `${num(counts.purchases, 0)} ${noun(counts.purchases, 'purchase', 'purchases')} and ${num(counts.sales, 0)} ${noun(counts.sales, 'sale', 'sales')}, net ${signed(counts.net, 0, '')} shares.`;
  if (open && !counts.purchases && !counts.sales) {
    const h = `No open-market purchases or sales by insiders ${span}.${other}`;
    return { ...base, signal: 'neutral', headline: h, line: h, short: 'None' };
  }
  // a payload with a signal but no counts (an older cached one) keeps the direction it was given
  const net = counts.net !== null ? counts.net : o.insider_signal === 'buying' ? 1 : o.insider_signal === 'selling' ? -1 : 0;
  const signal = net > 0 ? 'buying' : net < 0 ? 'selling' : 'neutral';
  if (net === 0) {
    const h = `Open-market purchases and sales by insiders offset ${span}: ${tally}${other}`;
    return { ...base, signal, headline: h, line: h, short: 'Even' };
  }
  const dirn = net > 0 ? 'Net buying' : 'Net selling', headline = `Insiders ${net > 0 ? 'bought' : 'sold'}, net, ${span}.`;
  return { ...base, signal, short: net > 0 ? 'Buying' : 'Selling', headline,
    line: counts.net === null ? headline : `${dirn} on the open market ${span}: ${tally}${other}${open ? '' : ' As Yahoo Finance tallies them, awards included.'}` };
}

// The full insider history (Financials, 2, 5 or 10 years; audit 2026-11-27, F01 class). The server decides one state for
// the period (insider_fill.history: reading, complete, partial, unavailable); this words it. "No open-market purchases
// or sales" is only ever said for a complete read: an empty table from a feed that failed, or from filings that were
// not all read, is unavailable or partial and says which dates are covered.
/** @returns {{ state: 'reading'|'complete'|'partial'|'unavailable', line: string, coverage: string, poll: boolean }} */
export function insiderHistoryRead(h, opts) {
  const hh = h || {}, cov = hh.coverage || {}, rows = hh.rows || [];
  const sym = String(hh.ticker || '').toUpperCase();
  const buys = rows.filter((r) => r.action === 'purchase').length, sells = rows.length - buys;
  // an older cached payload has no state: its counters say it
  let state = cov.state || (cov.sec_unread > 0 ? 'reading' : cov.complete === false ? (rows.length ? 'partial' : 'unavailable') : 'complete');
  const covered = cov.covered_from || null;
  // the last poll round came back still reading: say what is on hand rather than "still being read" for ever
  if (state === 'reading' && opts && opts.gaveUp) state = rows.length || covered ? 'partial' : 'unavailable';
  const S = fullDate(hh.since), C = covered ? fullDate(covered) : '';
  const T = fullDate(cov.covered_to || new Date().toISOString().slice(0, 10));
  const count = `${num(buys, 0)} open-market ${noun(buys, 'purchase', 'purchases')} and ${num(sells, 0)} ${noun(sells, 'sale', 'sales')}`;
  let line;
  if (state === 'complete') {
    if (rows.length) line = `${count} from ${S} to ${T}.`;
    else if (!(cov.sec_filings > 0) && !(cov.yahoo_rows > 0)) line = `No Form 4 filings by ${sym}'s insiders are on file with the SEC from ${S} to ${T}, so there are no open-market purchases or sales to list.`;
    else line = `No open-market purchases or sales by insiders from ${S} to ${T}. Every Form 4 filed in the period was read.`;
  } else if (state === 'reading') {
    line = rows.length ? `${count} found so far, since ${S}.` : `Insider trades since ${S} are still being read. Nothing is shown as "none" until the read finishes.`;
  } else if (state === 'partial') {
    if (rows.length) line = covered ? `${count} found so far. This list is partial: it covers ${C} to ${T}, not the full period from ${S}.` : `${count} found so far. This list is partial.`;
    else line = covered ? `Insider trades are only partly read: no open-market purchases or sales from ${C} to ${T}, and the period from ${S} to ${C} is unavailable right now. That is not the same as no activity.`
      : `Insider trades are only partly read for the period from ${S}. That is not the same as no activity.`;
  } else {
    line = `Insider trades from ${S} to ${T} are unavailable right now. That is not the same as no activity.`;
  }
  // the line under the table: Yahoo's part, then the SEC's by state, then what is never counted
  const yrows = cov.yahoo_rows || 0;
  const yahoo = yrows ? `Yahoo Finance lists its latest ${num(yrows, 0)} rows${cov.yahoo_from ? `, back to ${fullDate(cov.yahoo_from)}` : ''}.` : 'Yahoo Finance returned no insider rows this time.';
  const secRows = cov.sec_rows || 0, failed = cov.sec_failed || 0;
  const hadStretch = cov.listed !== undefined;
  let sec;
  if (state === 'complete') {
    sec = hadStretch ? `${yrows ? 'Before that, ' : ''}${num(secRows, 0)} trades come from Form 4 filings read from SEC EDGAR. Complete for the period.` : 'Complete for the period.';
  } else if (state === 'reading') {
    sec = cov.sec_unread > 0 ? `${num(cov.sec_unread, 0)} filings are still being read; this table fills in as they are.` : "The SEC's list of Form 4 filings is being read; this table fills in as it is.";
  } else if (cov.why === 'filings_unreadable' || failed > 0) {
    sec = `${num(failed, 0)} Form 4 ${noun(failed, 'filing', 'filings')} in the period could not be read, so trades in them are missing.`;
  } else if (cov.why === 'not_a_filer') {
    sec = `${sym} is not in the SEC's company directory, so there are no Form 4 filings to read.`;
  } else if (cov.sec_unread > 0) {
    sec = `${num(cov.sec_unread, 0)} Form 4 ${noun(cov.sec_unread, 'filing', 'filings')} in the period have not been read yet, so trades in them are missing.`;
  } else {
    sec = covered ? `The SEC's filing list could not be reached this time, so trades before ${C} are not shown.` : "The SEC's filing list could not be reached this time, so the period is not covered.";
  }
  const coverage = `${yahoo} ${sec} Awards, option exercises, tax withholding and gifts are not trades and are left out.`;
  return { state, line, coverage, poll: state === 'reading' };
}
