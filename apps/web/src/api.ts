import type { ErrorResponse, Ruleset, ScoresResponse } from "./types";

export async function getScores(
  username: string,
  limit: number,
  mode: Ruleset,
  signal: AbortSignal,
) {
  const response = await fetch(
    `/api/v1/players/${encodeURIComponent(username)}/scores?type=best&limit=${limit}&mode=${mode}`,
    { signal },
  );
  if (!response.ok) {
    const body = (await response
      .json()
      .catch(() => null)) as ErrorResponse | null;
    const retryAfter = response.headers.get("Retry-After");
    throw new Error(
      (body?.error?.message || "查询失败，请稍后重试。") +
        (retryAfter ? ` ${retryAfter} 秒后可再次查询。` : ""),
    );
  }
  return {
    data: (await response.json()) as ScoresResponse,
    cache: response.headers.get("X-Cache") || "UNKNOWN",
  };
}
