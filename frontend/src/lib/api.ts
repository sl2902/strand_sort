import type {
  DonationItem,
  IntakeResponse,
  ReviewResolutionRequest,
  ReviewResolutionResponse,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Couldn't reach the backend at ${API_BASE_URL}. Is the API running?`,
      0
    );
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail ?? detail;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), response.status);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

// ---- App config ----

interface AppConfig {
  upload_mode: "local" | "presigned";
}

// Fetched once and cached for the page session — the backend's
// storage_backend is the single source of truth for which upload flow to
// use; duplicating that into a separate frontend env var would just be a
// second source of truth that can drift out of sync (the same class of
// bug as the earlier /api/v1 path mismatch).
let appConfigPromise: Promise<AppConfig> | null = null;

function getAppConfig(): Promise<AppConfig> {
  if (!appConfigPromise) {
    appConfigPromise = request<AppConfig>("/config");
  }
  return appConfigPromise;
}

// ---- Intake ----

interface PresignedUpload {
  s3_key: string;
  upload_url: string;
}

/**
 * Uploads files directly to S3 via presigned PUT URLs, bypassing this API
 * (and Lambda's 6MB synchronous payload limit) for the actual file bytes.
 * Returns the resulting S3 keys, which /intake and /intake/video accept in
 * place of the file bytes themselves. Only used when the backend's upload
 * mode is "presigned" (storage_backend=s3) — see intakeImage/intakeVideo.
 */
async function uploadToS3(
  items: { blob: File | Blob; filename: string }[],
  kind: "image" | "video"
): Promise<string[]> {
  const presigned = await request<PresignedUpload[]>("/uploads/presign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filenames: items.map((item) => item.filename), kind }),
  });

  await Promise.all(
    items.map((item, i) =>
      fetch(presigned[i].upload_url, {
        method: "PUT",
        body: item.blob,
        headers: { "Content-Type": item.blob.type || "application/octet-stream" },
      })
    )
  );

  return presigned.map((p) => p.s3_key);
}

export async function intakeImage(files: File[] | Blob[], filenamePrefix = "photo"): Promise<IntakeResponse> {
  const { upload_mode } = await getAppConfig();

  if (upload_mode === "local") {
    const form = new FormData();
    files.forEach((file, i) => {
      const name = file instanceof File ? file.name : `${filenamePrefix}-${i}.jpg`;
      form.append("files", file, name);
    });
    return request<IntakeResponse>("/intake/local", { method: "POST", body: form });
  }

  const items = files.map((file, i) => ({
    blob: file,
    filename: file instanceof File ? file.name : `${filenamePrefix}-${i}.jpg`,
  }));
  const s3Keys = await uploadToS3(items, "image");
  return request<IntakeResponse>("/intake", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ s3_keys: s3Keys }),
  });
}

export async function intakeVideo(file: File | Blob, filename = "clip.webm"): Promise<IntakeResponse> {
  const { upload_mode } = await getAppConfig();

  if (upload_mode === "local") {
    const form = new FormData();
    form.append("file", file, filename);
    return request<IntakeResponse>("/intake/video/local", { method: "POST", body: form });
  }

  const [s3Key] = await uploadToS3(
    [{ blob: file, filename: file instanceof File ? file.name : filename }],
    "video"
  );
  return request<IntakeResponse>("/intake/video", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ s3_key: s3Key }),
  });
}

// ---- Inventory ----

export function listInventory(name?: string): Promise<DonationItem[]> {
  const query = name ? `?name=${encodeURIComponent(name)}` : "";
  return request<DonationItem[]>(`/inventory${query}`);
}

export function getItem(itemId: string): Promise<DonationItem> {
  return request<DonationItem>(`/inventory/${encodeURIComponent(itemId)}`);
}

export function updateItem(itemId: string, updates: Record<string, unknown>): Promise<DonationItem> {
  return request<DonationItem>(`/inventory/${encodeURIComponent(itemId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

export function checkoutItem(itemId: string, quantity: number): Promise<DonationItem> {
  return request<DonationItem>(
    `/inventory/${encodeURIComponent(itemId)}/checkout?quantity=${encodeURIComponent(quantity)}`,
    { method: "POST" }
  );
}

/**
 * Explicit rejection of an expired item — the sanctioned path for removing
 * an item now that the Inventory UI no longer exposes a raw delete action.
 * The backend gates this on expiry_status itself (recomputed fresh, not
 * just hidden client-side), so this only succeeds for genuinely expired
 * items.
 */
export function rejectItem(itemId: string): Promise<{ status: string; item_id: string }> {
  return request<{ status: string; item_id: string }>(`/inventory/${encodeURIComponent(itemId)}/reject`, {
    method: "POST",
  });
}

/**
 * Raw delete — the backend endpoint was never removed (only Reject, gated
 * to expired items, is exposed in the real UI). Only wired up behind
 * import.meta.env.DEV, as a local dev convenience for clearing out test
 * data without waiting for something to expire — see InventoryItemCard/
 * InventoryItemPage.
 */
export function deleteItem(itemId: string): Promise<{ status: string; item_id: string }> {
  return request<{ status: string; item_id: string }>(`/inventory/${encodeURIComponent(itemId)}`, {
    method: "DELETE",
  });
}

// ---- Review queue ----

export function listPendingReviews(): Promise<DonationItem[]> {
  return request<DonationItem[]>("/review/pending");
}

export function resolveReview(
  itemId: string,
  body: ReviewResolutionRequest
): Promise<ReviewResolutionResponse> {
  return request<ReviewResolutionResponse>(`/review/resolve/${encodeURIComponent(itemId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * Backend image URLs come back two shapes: absolute presigned S3 URLs, or
 * paths relative to the API's own origin (local disk storage, served via
 * StaticFiles at /images). Normalize both to something an <img> can load
 * directly, regardless of which storage backend is active.
 */
export function resolveImageUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  return `${new URL(API_BASE_URL).origin}${url}`;
}

export { API_BASE_URL };
