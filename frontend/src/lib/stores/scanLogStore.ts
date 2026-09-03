import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { ScanLogEntry } from "../../components/scan/ScanResultCard";

// New key, distinct from the old raw-array `localStorage` format this
// replaces (see lib/scanLog.ts, removed) — zustand's persist middleware
// wraps state as `{state, version}`, not a bare array, so reusing the old
// key would fail to parse on first load. A one-time reset of any pre-existing
// session log is an acceptable trade-off for a dev-tool feature like this.
const STORAGE_KEY = "strand-sort:scan-log-store";

interface ScanLogState {
  entries: ScanLogEntry[];
  addEntry: (entry: ScanLogEntry) => void;
  updateEntry: (id: string, patch: Partial<ScanLogEntry>) => void;
  deleteEntry: (id: string) => void;
  clear: () => void;
}

/**
 * Single source of truth for the scan log — a module-level store, not tied
 * to ScanPage's component lifecycle. That's what makes it work for both
 * cases at once:
 *   - Still mounted when a scan resolves: any component subscribed via
 *     useScanLogStore() re-renders automatically (that's the reactivity
 *     useState + a manual localStorage patch couldn't give us — nothing
 *     told the mounted component to re-read).
 *   - Unmounted before a scan resolves: these actions are plain functions
 *     bound to this module-level store, not to any component instance, so
 *     calling updateEntry(...) from a promise that resolves after ScanPage
 *     unmounted still updates real, persisted state — no more no-op setState
 *     on a dead component.
 */
export const useScanLogStore = create<ScanLogState>()(
  persist(
    (set) => ({
      entries: [],
      addEntry: (entry) => set((state) => ({ entries: [entry, ...state.entries] })),
      updateEntry: (id, patch) =>
        set((state) => ({
          entries: state.entries.map((e) => (e.id === id ? { ...e, ...patch } : e)),
        })),
      deleteEntry: (id) => set((state) => ({ entries: state.entries.filter((e) => e.id !== id) })),
      clear: () => set({ entries: [] }),
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({ entries: state.entries }),
    }
  )
);
