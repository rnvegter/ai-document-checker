// Check history, kept in this browser only (localStorage).
// Storage can be missing or full (private windows, quotas), so every
// access is guarded and the app keeps working without it.

const KEY = "aichecker.history.v1";
const MAX_ENTRIES = 200;

function read(storage) {
  try {
    const list = JSON.parse(storage.getItem(KEY) || "[]");
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function write(storage, list) {
  // Drop the oldest entries until the list fits in the quota.
  let items = list.slice(0, MAX_ENTRIES);
  while (items.length) {
    try {
      storage.setItem(KEY, JSON.stringify(items));
      return true;
    } catch {
      items = items.slice(0, -1);
    }
  }
  try {
    storage.removeItem(KEY);
  } catch {}
  return list.length === 0;
}

export function titleFor(text) {
  const line = text.trim().split("\n").find((l) => l.trim()) || "Untitled";
  const clean = line.replace(/^#+\s*/, "").trim();
  return clean.length > 70 ? `${clean.slice(0, 67).trimEnd()}…` : clean;
}

export function createHistory(storage = globalThis.localStorage) {
  const store = storage || { getItem: () => null, setItem: () => {}, removeItem: () => {} };
  return {
    list: () => read(store).sort((a, b) => b.updated - a.updated),
    get: (id) => read(store).find((e) => e.id === id) || null,
    save(entry) {
      const now = Date.now();
      const list = read(store);
      const existing = entry.id && list.find((e) => e.id === entry.id);
      const saved = {
        ...existing,
        ...entry,
        id: entry.id || `${now.toString(36)}${Math.random().toString(36).slice(2, 7)}`,
        title: entry.title || titleFor(entry.text || ""),
        created: existing ? existing.created : now,
        updated: now,
      };
      const rest = list.filter((e) => e.id !== saved.id);
      write(store, [saved, ...rest]);
      return saved;
    },
    remove(id) {
      write(store, read(store).filter((e) => e.id !== id));
    },
    clear() {
      write(store, []);
    },
    exportJson: () => JSON.stringify(read(store), null, 2),
  };
}
