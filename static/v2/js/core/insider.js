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
