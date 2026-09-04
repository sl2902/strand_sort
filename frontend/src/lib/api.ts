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

// ---- Intake ----

export function intakeImage(files: File[] | Blob[], filenamePrefix = "photo"): Promise<IntakeResponse> {
  const form = new FormData();
  files.forEach((file, i) => {
    const name = file instanceof File ? file.name : `${filenamePrefix}-${i}.jpg`;
    form.append("files", file, name);
  });
  return request<IntakeResponse>("/intake", { method: "POST", body: form });
}

export function intakeVideo(file: File | Blob, filename = "clip.webm"): Promise<IntakeResponse> {
  const form = new FormData();
  form.append("file", file, filename);
  return request<IntakeResponse>("/intake/video", { method: "POST", body: form });
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
