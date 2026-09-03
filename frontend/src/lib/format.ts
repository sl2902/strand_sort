export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "Unknown";
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export type ExpiryUrgency = "expired" | "soon" | "ok" | "unknown";

export function expiryUrgency(iso: string | null | undefined): ExpiryUrgency {
  if (!iso) return "unknown";
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return "unknown";
  const daysLeft = (parsed.getTime() - Date.now()) / (1000 * 60 * 60 * 24);
  if (daysLeft < 0) return "expired";
  if (daysLeft <= 30) return "soon";
  return "ok";
}

export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const parsed = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return null;
  return Math.ceil((parsed.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
}

export type ScanOutcome = "committed" | "flagged" | "unknown";

/**
 * /intake and /intake/video only return the agent's free-text summary — there's
 * no structured "status" field in the API contract. This is a light heuristic
 * over that text purely to pick an icon/tone; the summary text itself (shown
 * alongside) is always the source of truth for the volunteer.
 */
export function classifyScanResult(text: string): ScanOutcome {
  const lower = text.toLowerCase();
  if (/(flag|review)/.test(lower)) return "flagged";
  if (/(committ|regist|added|updated)/.test(lower)) return "committed";
  return "unknown";
}

export function titleCase(s: string): string {
  return s
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => w[0]!.toUpperCase() + w.slice(1))
    .join(" ");
}
