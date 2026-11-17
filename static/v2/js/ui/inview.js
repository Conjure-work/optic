// What the reader is looking at on a long page (Pass 2, 2026-11-17): the element marked data-v2-metric that the reader
// last pressed or focused, or else the one nearest the top of the screen. Milo is told its name, so "explain this
// chart" on Financials means the chart in view, not the page. Names only, never values.
const nameOf = (el) => (el.dataset.v2Metric || ((el.querySelector('h3, h2') || {}).textContent || '')).replace(/\s+/g, ' ').trim();

/** The metric's name: its data-v2-metric value, or else its own heading. Start watching `root`; `get()` answers the metric in view as {metric, el} or null; `stop()` ends it. */
export function watchInView(root) {
  let touched = null;
  const mark = (e) => { const el = e.target && e.target.closest && e.target.closest('[data-v2-metric]'); if (el && root.contains(el)) touched = el; };
  root.addEventListener('click', mark, true);
  root.addEventListener('focusin', mark, true);
  const onScreen = (el) => { const r = el.getBoundingClientRect(); return r.bottom > 80 && r.top < (window.innerHeight || 800) - 80; };
  return {
    get() {
      if (touched && touched.isConnected && onScreen(touched)) return { metric: nameOf(touched), el: touched };
      const els = [...root.querySelectorAll('[data-v2-metric]')].filter((e) => e.offsetParent !== null && onScreen(e));
      if (!els.length) return null;
      // the one whose top is nearest the top of the screen, below the sticky header
      els.sort((a, b) => Math.abs(a.getBoundingClientRect().top - 96) - Math.abs(b.getBoundingClientRect().top - 96));
      return { metric: nameOf(els[0]), el: els[0] };
    },
    stop() { root.removeEventListener('click', mark, true); root.removeEventListener('focusin', mark, true); },
  };
}
