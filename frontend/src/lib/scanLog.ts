import type { ScanLogEntry } from "../components/scan/ScanResultCard";

const STORAGE_KEY = "strand-sort:scan-log";

export function loadScanLog(): ScanLogEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ScanLogEntry[]) : [];
  } catch {
    return [];
  }
}

export function saveScanLog(log: ScanLogEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(log));
  } catch {
    // storage full/unavailable — fail silently, log just won't persist
  }
}

/**
 * Patches one entry directly in localStorage, independent of any mounted
 * ScanPage's React state. A scan keeps running server-side even if the user
 * navigates away before it finishes — if we only wrote the result via
 * ScanPage's own `setLog`, that update would land on an unmounted component
 * instance and silently no-op, stranding the entry at "pending" forever even
 * though the backend actually completed it. Called from the same place
 * `setLog` is (for the common case where the page is still mounted and needs
 * a live re-render), but this call is what makes the write durable either way.
 */
export function patchScanLogEntry(id: string, patch: Partial<ScanLogEntry>): void {
  const log = loadScanLog();
  saveScanLog(log.map((e) => (e.id === id ? { ...e, ...patch } : e)));
}
