// Which shape Watchlist and Portfolio take (round three). By default Watchlist holds the lists and the alerts as two
// views of one page, and #/portfolio is the reader's own books first. The owner's one setting,
// OPTIC_SEPARATE_ALERTS_AND_MODELS=on, shows #/alerts as its own page again and opens Optic's model books at
// #/portfolio, as before round three; /api/health reports which (app/investor.py), and this reads it once.
import * as api from './api.js';

let known = null;
/** True when the owner has asked for the old separate pages. Never throws: unknown reads as the default (one place). */
export async function separate() {
  if (known !== null) return known;
  try {
    const h = await api.get('/api/health', { ttl: 300000, timeout: 8000 });
    known = (((h || {}).modes || {}).investor_pages || {}).watchlist_and_alerts === 'separate pages';
  } catch (e) { known = false; }
  return known;
}
/** What the last read said, without asking (false until it has been read). */
export const separateNow = () => known === true;
