import type { ExpiryStatus } from "./types";

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Unknown";
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/**
 * Tone + label for the expiry badge, driven entirely by the backend's
 * expiry_status — deliberately NOT recomputed client-side. This used to be
 * a separate client-side day-count check with its own threshold (30 days),
 * which had quietly drifted from the backend's own near-expiry window (7
 * days) — two sources of truth for the same fact, silently disagreeing.
 * expiry_status is recomputed fresh by the backend on every read, so it's
 * the one place this should be decided.
 */
export function expiryBadgeContent(
  status: ExpiryStatus | null | undefined,
  expirationDate: string | null | undefined
): { tone: "neutral" | "saffron" | "danger"; label: string } {
  const dateText = formatDate(expirationDate);
  if (status === "expired") return { tone: "danger", label: `Expired ${dateText}` };
  if (status === "near_expiry") return { tone: "saffron", label: `Expires soon: ${dateText}` };
  return { tone: "neutral", label: `Expires ${dateText}` };
}

/** Soonest-expiring first; items with no date sink to the bottom. */
export function byExpirationDateAscending<T extends { expiration_date: string | null }>(a: T, b: T): number {
  return (a.expiration_date ?? "9999").localeCompare(b.expiration_date ?? "9999");
}

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return null;
  return Math.ceil((parsed.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
}

export function titleCase(s: string): string {
  return s
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w[0]!.toUpperCase() + w.slice(1))
    .join(" ");
}
