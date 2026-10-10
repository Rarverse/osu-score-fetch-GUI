import { errorMessage, t } from "./i18n";
import type { ErrorResponse, Ruleset, ScoresResponse } from "./types";

interface CachedScores {
  data: ScoresResponse;
  expiresAt: number;
}

const cache = new Map<string, CachedScores>();

function cacheKey(username: string, mode: Ruleset, limit: number): string {
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
  mode: Ruleset,
  signal: AbortSignal,
) {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  const key = cacheKey(username, mode, limit);
  for (const [storedKey, entry] of cache) {
    if (entry.expiresAt <= Date.now()) cache.delete(storedKey);
  }
  const cached = cache.get(key);
  if (cached) return { data: cached.data, cache: "MEMORY" };
  const response = await fetch(
    `/api/v1/players/${encodeURIComponent(username)}/scores?type=best&limit=${limit}&mode=${mode}`,
    { signal },
  );
  if (!response.ok) {
    const body = (await response
      .json()
      .catch(() => null)) as ErrorResponse | null;
    const header = response.headers.get("Retry-After");
    const seconds = Number(header);
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
