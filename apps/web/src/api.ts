import { errorMessage, t } from "./i18n";
import type { ErrorResponse, QueryMode, ScoresResponse } from "./types";

interface CachedScores {
  data: ScoresResponse;
  expiresAt: number;
}

const cache = new Map<string, CachedScores>();
const VISITOR_STORAGE_KEY = "rarsu-visitor-id";
let memoryVisitorId = "";

function readStoredVisitorId(): string {
  if (memoryVisitorId) return memoryVisitorId;
  try {
    const stored = localStorage.getItem(VISITOR_STORAGE_KEY);
    if (stored && /^[0-9a-f-]{36}$/i.test(stored)) return stored;
  } catch {
    return "";
  }
  return "";
}

function visitorId(): string {
  const existing = readStoredVisitorId();
  if (existing) return existing;
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
  const created = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  memoryVisitorId = created;
  try {
    localStorage.setItem(VISITOR_STORAGE_KEY, created);
  } catch {
    // Private mode can reject storage. The page still sends this in-memory id.
  }
  return created;
}

function cacheKey(username: string, mode: QueryMode, limit: number): string {
  const name = username.trim().toLowerCase();
  const normalized = /^\d+$/.test(name) ? name.replace(/^0+(?=\d)/, "") : name;
  return JSON.stringify([normalized, mode, limit]);
}

export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public status: number,
    public retryAfter: number,
  ) {
    super(message);
  }

  get isBusy() {
    return (
      this.status === 503 &&
      ["SERVER_BUSY", "UPSTREAM_BUSY"].includes(this.code)
    );
  }
}

export function waitForRetry(
  milliseconds: number,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", abort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, milliseconds);
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
  });
}

export async function getScores(
  username: string,
  limit: number,
  mode: QueryMode,
  signal: AbortSignal,
  credentials?: { clientId: string; clientSecret: string },
) {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  const key = cacheKey(username, mode, limit);
  for (const [storedKey, entry] of cache) {
    if (entry.expiresAt <= Date.now()) cache.delete(storedKey);
  }
  const cached = cache.get(key);
  if (cached) return { data: cached.data, cache: "MEMORY" };
  const headers = new Headers();
  headers.set("X-Visitor-Id", visitorId());
  if (credentials) {
    headers.set("X-Osu-Client-Id", credentials.clientId);
    headers.set("X-Osu-Client-Secret", credentials.clientSecret);
  }
  const response = await fetch(
    `/api/v1/players/${encodeURIComponent(username)}/scores?type=best&limit=${limit}${mode === "auto" ? "" : `&mode=${mode}`}`,
    { signal, headers },
  );
  if (!response.ok) {
    const body = (await response
      .json()
      .catch(() => null)) as ErrorResponse | null;
    const header = response.headers.get("Retry-After");
    const seconds =
      header && /^\d+$/.test(header.trim())
        ? Number(header)
        : (Date.parse(header || "") - Date.now()) / 1000;
    const retryAfter =
      Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : 5;
    throw new ApiError(
      errorMessage(body?.error?.code || "UNKNOWN_ERROR") +
        (header ? ` ${t("retryAfter", { seconds: retryAfter })}` : ""),
      body?.error?.code || "UNKNOWN_ERROR",
      response.status,
      retryAfter,
    );
  }
  const data = (await response.json()) as ScoresResponse;
  const ttl = Number(response.headers.get("X-Cache-TTL"));
  if (Number.isFinite(ttl) && ttl > 0 && !signal.aborted) {
    const entry = { data, expiresAt: Date.now() + Math.min(60, ttl) * 1000 };
    for (const alias of [
      username,
      data.player.username,
      String(data.player.user_id),
    ]) {
      cache.set(cacheKey(alias, mode, limit), entry);
      cache.set(cacheKey(alias, data.mode, limit), entry);
    }
    while (cache.size > 50) {
      const oldest = cache.keys().next().value;
      if (oldest !== undefined) cache.delete(oldest);
    }
  }
  return {
    data,
    cache: response.headers.get("X-Cache") || "UNKNOWN",
  };
}
