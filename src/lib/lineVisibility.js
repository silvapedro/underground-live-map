import lineNames from "../data/line-names.json";

const STORAGE_KEY = "underground-live-map:visible-lines";

// Overground (6 lines) and Elizabeth line default to hidden -- the user asked for
// these off by default, toggleable back on via the line legend.
const DEFAULT_HIDDEN = new Set([
  "elizabeth", "liberty", "lioness", "mildmay", "suffragette", "weaver", "windrush",
]);

const ALL_LINE_IDS = Object.keys(lineNames);

function defaultVisible() {
  return new Set(ALL_LINE_IDS.filter((id) => !DEFAULT_HIDDEN.has(id)));
}

/** Load the persisted visible-lines set, falling back to the default if unset,
 * corrupt, or from localStorage being unavailable (e.g. private browsing). */
export function loadVisibleLines() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const stored = JSON.parse(raw);
      if (Array.isArray(stored)) {
        // Ignore stale line ids from an old build; keep only ones we still know about.
        return new Set(stored.filter((id) => ALL_LINE_IDS.includes(id)));
      }
    }
  } catch {
    // corrupt JSON or storage disabled -- fall through to the default
  }
  return defaultVisible();
}

export function saveVisibleLines(visibleLines) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify([...visibleLines]));
  } catch {
    // storage unavailable (private browsing, quota) -- toggle still works for this
    // session via React state, it just won't persist across reloads.
  }
}
