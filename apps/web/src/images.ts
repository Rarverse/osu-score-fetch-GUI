// Exports use the same-origin server cache; page artwork loads directly from osu!.
export function imageUrl(url: string | null): string {
  return url ? `/api/v1/images?url=${encodeURIComponent(url)}` : "";
}
