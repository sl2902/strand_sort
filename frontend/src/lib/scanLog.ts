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
