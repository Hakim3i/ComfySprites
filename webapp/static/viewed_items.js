/** Persist which gallery / lab outputs the user has opened in preview (localStorage). */

const VIEWED_STORAGE_KEY = 'coomfy:viewed-items';
const VIEWED_MAX = 5000;

function loadViewedIds() {
  try {
    const raw = localStorage.getItem(VIEWED_STORAGE_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr.filter(Boolean) : []);
  } catch {
    return new Set();
  }
}

function saveViewedIds(set) {
  try {
    const arr = [...set];
    const capped = arr.length > VIEWED_MAX ? arr.slice(-VIEWED_MAX) : arr;
    localStorage.setItem(VIEWED_STORAGE_KEY, JSON.stringify(capped));
  } catch {
    /* storage full or disabled */
  }
}

function createViewedTracker() {
  const viewed = loadViewedIds();
  return {
    isViewed(id) {
      return Boolean(id) && viewed.has(String(id));
    },
    markViewed(id) {
      const key = id == null ? '' : String(id).trim();
      if (!key) return;
      if (viewed.has(key)) return;
      viewed.add(key);
      saveViewedIds(viewed);
    },
  };
}

window.coomfyViewedTracker = function coomfyViewedTracker() {
  if (!window._coomfyViewedTracker) {
    window._coomfyViewedTracker = createViewedTracker();
  }
  return window._coomfyViewedTracker;
};
